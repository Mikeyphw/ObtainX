part of 'r04_github_actions.dart';

/// A row in the explicit, manual Actions history. Failed/in-progress runs and
/// artifacts without a validated digest are inspectable but NOT selectable.
class R04ActionsHistoryItem {
  const R04ActionsHistoryItem({
    required this.workflowId,
    required this.workflowName,
    required this.runId,
    required this.runAttempt,
    required this.branch,
    required this.commitSha,
    required this.createdAt,
    required this.status,
    required this.reason,
    this.artifactId,
    this.artifactName,
    this.archiveSha256,
    this.expiresAt,
    this.sizeBytes,
  });

  final int workflowId;
  final String workflowName;
  final int runId;
  final int runAttempt;
  final String branch;
  final String commitSha;
  final DateTime createdAt;
  final String status;
  final String reason;
  final int? artifactId;
  final String? artifactName;
  final String? archiveSha256;
  final DateTime? expiresAt;
  final int? sizeBytes;

  bool get canSelect => status == 'completed/success' &&
      reason == 'eligible' && artifactId != null && archiveSha256 != null;
}

extension R04ActionsManualHistory on R04GitHubActionsCatalog {
  /// Bounded read-only history. Never dispatches workflows or installs APKs.
  /// All listed runs belong to the explicit branch and a known active workflow.
  Future<List<R04ActionsHistoryItem>> history({
    String? branch,
    String? workflow,
    int maxRuns = 12,
  }) async {
    if (maxRuns < 1 || maxRuns > 30) {
      throw const R04ActionsFailure('history limit outside safe bounds');
    }
    final repo = await _fetchObject(repoApi);
    final defaultBranch = R04GitHubActionsCatalog._string(repo['default_branch']);
    if (defaultBranch == null) {
      throw const R04ActionsFailure('repository default branch unavailable');
    }
    final selectedBranch = branch?.trim().isNotEmpty == true
        ? branch!.trim() : defaultBranch;
    if (selectedBranch.length > 240 || selectedBranch.contains('..') ||
        RegExp(r'[\x00-\x20\x7f]').hasMatch(selectedBranch)) {
      throw const R04ActionsFailure('invalid history branch');
    }
    final workflows = await _list('/actions/workflows', 'workflows');
    final names = <int, String>{};
    for (final w in workflows) {
      final id = R04GitHubActionsCatalog._positiveInt(w['id']);
      final name = R04GitHubActionsCatalog._string(w['name']);
      if (id != null && name != null && w['state'] == 'active') {
        names[id] = name;
      }
    }
    int? workflowId;
    if (workflow?.trim().isNotEmpty == true) {
      final selector = workflow!.trim();
      workflowId = int.tryParse(selector);
      if (workflowId == null) {
        final candidates = names.entries.where((e) => e.value == selector).toList();
        if (candidates.length != 1) {
          throw const R04ActionsFailure('history workflow missing or ambiguous');
        }
        workflowId = candidates.single.key;
      }
      if (!names.containsKey(workflowId)) {
        throw const R04ActionsFailure('history workflow ID unknown');
      }
    }
    final rawRuns = await _list('/actions/runs', 'workflow_runs',
      {'branch': selectedBranch});
    final validRuns = rawRuns.where((run) =>
      R04GitHubActionsCatalog._positiveInt(run['id']) != null &&
      R04GitHubActionsCatalog._positiveInt(run['workflow_id']) != null &&
      names.containsKey(run['workflow_id']) &&
      (workflowId == null || run['workflow_id'] == workflowId) &&
      run['head_branch'] == selectedBranch &&
      R04GitHubActionsCatalog._sha(run['head_sha']) != null &&
      R04GitHubActionsCatalog._positiveInt(run['run_attempt']) != null &&
      R04GitHubActionsCatalog._date(run['created_at']) != null).toList();
    validRuns.sort((a, b) =>
      R04GitHubActionsCatalog._date(b['created_at'])!.compareTo(
        R04GitHubActionsCatalog._date(a['created_at'])!));
    final result = <R04ActionsHistoryItem>[];
    for (final run in validRuns.take(maxRuns)) {
      final id = R04GitHubActionsCatalog._positiveInt(run['id'])!;
      final attempt = R04GitHubActionsCatalog._positiveInt(run['run_attempt'])!;
      final workflowNumber = R04GitHubActionsCatalog._positiveInt(run['workflow_id'])!;
      final commit = R04GitHubActionsCatalog._sha(run['head_sha'])!;
      final date = R04GitHubActionsCatalog._date(run['created_at'])!;
      final status = '${run['status']}/${run['conclusion']}';
      R04ActionsHistoryItem row(String reason, {
        int? artifactId, String? artifactName, String? digest,
        DateTime? expires, int? bytes,
      }) => R04ActionsHistoryItem(
        workflowId: workflowNumber, workflowName: names[workflowNumber]!,
        runId: id, runAttempt: attempt, branch: selectedBranch,
        commitSha: commit, createdAt: date, status: status,
        reason: reason, artifactId: artifactId, artifactName: artifactName,
        archiveSha256: digest, expiresAt: expires, sizeBytes: bytes,
      );
      if (run['status'] != 'completed' || run['conclusion'] != 'success') {
        result.add(row('run not successful; not installable'));
        continue;
      }
      final artifacts = await _list('/actions/runs/$id/artifacts', 'artifacts');
      var candidates = 0;
      for (final raw in artifacts) {
        final artifactId = R04GitHubActionsCatalog._positiveInt(raw['id']);
        final artifactName = R04GitHubActionsCatalog._string(raw['name']);
        if (artifactId == null || artifactName == null ||
            !R04GitHubActionsCatalog.isCandidateName(artifactName)) {
          continue; // No logs, source bundles or malformed archive names.
        }
        candidates++;
        final bytes = R04GitHubActionsCatalog._positiveInt(raw['size_in_bytes']);
        final expires = R04GitHubActionsCatalog._date(raw['expires_at']);
        final digest = R04GitHubActionsCatalog._artifactDigest(raw['digest']);
        final owner = raw['workflow_run'];
        final isBound = owner is! Map ||
            (owner['id'] == id && owner['head_sha'] == commit);
        final eligible = raw['expired'] == false &&
            expires != null && expires.isAfter(now().toUtc()) &&
            bytes != null && bytes <= R04GitHubActionsCatalog.maxArchiveBytes &&
            digest != null && isBound;
        result.add(row(eligible ? 'eligible' : 'expired, changed or unverified artifact',
          artifactId: artifactId, artifactName: artifactName, digest: digest,
          expires: expires, bytes: bytes));
      }
      if (candidates == 0) {
        result.add(row('no installable Android archive in run'));
      }
    }
    return result;
  }
}
