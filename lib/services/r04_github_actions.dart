/// R04 GitHub Actions source-native discovery. This API discovers *archives*;
/// neither a GitHub archive SHA-256 nor a successful workflow run proves an APK
/// signing certificate, installed package, or build attestation.
library;

import 'dart:convert';

import 'package:http/http.dart' show Response;

part 'r04_actions_history_catalog.dart';

typedef R04Request = Future<Response> Function(Uri uri);

class R04ActionsFailure implements Exception {
  const R04ActionsFailure(this.reason, {this.statusCode});
  final String reason;
  final int? statusCode;
  @override
  String toString() => 'R04 Actions: $reason';
}

class R04ActionsArchive {
  const R04ActionsArchive({
    required this.artifactId,
    required this.runId,
    required this.runAttempt,
    required this.workflowId,
    required this.commitSha,
    required this.branch,
    required this.name,
    required this.sizeBytes,
    required this.archiveUrl,
    required this.createdAt,
    required this.expiresAt,
    this.archiveSha256,
  });

  final int artifactId;
  final int runId;
  final int runAttempt;
  final int workflowId;
  final String commitSha;
  final String branch;
  final String name;
  final int sizeBytes;
  final Uri archiveUrl;
  final DateTime createdAt;
  final DateTime expiresAt;
  /// Hash of the GitHub artifact ZIP, NOT the contained APK or its signature.
  final String? archiveSha256;

  String get fileName => '$name.zip';
}

class R04ActionsSelection {
  const R04ActionsSelection({
    required this.archive,
    required this.workflowName,
    required this.runNumber,
    required this.runDate,
  });
  final R04ActionsArchive archive;
  final String workflowName;
  final int runNumber;
  final DateTime runDate;

  String get version =>
      'actions-${archive.runId}-a${archive.runAttempt}-${archive.commitSha.substring(0, 12)}';
}

/// Refuse cross-repository API pagination links, unbounded pages and malformed
/// metadata. Only latest *successful completed* run of the selected branch is
/// considered an automatic update source.
class R04GitHubActionsCatalog {
  R04GitHubActionsCatalog({
    required this.repoApi,
    required this.request,
    DateTime Function()? now,
    this.maximumPages = 20,
  }) : now = now ?? DateTime.now {
    if (repoApi.scheme != 'https' || repoApi.host != 'api.github.com' ||
        !RegExp(r'^/repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')
            .hasMatch(repoApi.path) ||
        repoApi.hasQuery || repoApi.hasFragment || maximumPages < 1 ||
        maximumPages > 40) {
      throw const R04ActionsFailure('invalid canonical GitHub repository API URL');
    }
  }

  final Uri repoApi;
  final R04Request request;
  final DateTime Function() now;
  final int maximumPages;
  static const int maxArchiveBytes = 1024 * 1024 * 1024;

  Future<Map<String, dynamic>> _fetchObject(Uri uri) async {
    if (uri.scheme != 'https' || uri.host != repoApi.host ||
        !(uri.path == repoApi.path || uri.path.startsWith('${repoApi.path}/'))) {
      throw const R04ActionsFailure('cross-origin or out-of-repository API request refused');
    }
    final response = await request(uri);
    if (response.statusCode != 200) {
      final code = response.statusCode;
      if (code == 401 || code == 403 || code == 429 ||
          response.headers['x-ratelimit-remaining'] == '0') {
        throw R04ActionsFailure('authentication or API rate limit', statusCode: code);
      }
      throw R04ActionsFailure('GitHub API request failed', statusCode: code);
    }
    if (response.bodyBytes.length > 8 * 1024 * 1024) {
      throw const R04ActionsFailure('oversized API response');
    }
    try {
      final decoded = jsonDecode(response.body);
      if (decoded is Map<String, dynamic>) return decoded;
    } catch (_) {
      // Malformed JSON cannot become a successful build candidate.
    }
    throw const R04ActionsFailure('invalid GitHub API JSON');
  }

  Future<List<Map<String, dynamic>>> _list(String path, String field,
      [Map<String, String> filters = const {}]) async {
    final seenIds = <int>{};
    final collected = <Map<String, dynamic>>[];
    for (var page = 1; page <= maximumPages; page++) {
      final uri = repoApi.replace(
        path: '${repoApi.path}$path',
        queryParameters: <String, String>{
          ...filters, 'per_page': '100', 'page': '$page',
        },
      );
      final result = await _fetchObject(uri);
      final raw = result[field];
      if (raw is! List) {
        throw R04ActionsFailure('missing $field collection');
      }
      for (final value in raw) {
        if (value is! Map<String, dynamic>) {
          throw const R04ActionsFailure('invalid collection entry');
        }
        final id = value['id'];
        if (id is! int || id <= 0) {
          throw const R04ActionsFailure('invalid collection identity');
        }
        if (seenIds.add(id)) collected.add(value);
      }
      if (raw.length < 100) return collected;
      // Never pretend a partial inventory is complete. Pagination is bounded,
      // and GitHub filters/ordering may otherwise silently hide older entries.
      if (page == maximumPages) {
        throw const R04ActionsFailure('pagination exceeded safe page budget');
      }
    }
    throw const R04ActionsFailure('pagination incomplete');
  }

  static String? _string(Object? value) =>
      value is String && value.trim().isNotEmpty ? value : null;

  static int? _positiveInt(Object? value) =>
      value is int && value > 0 ? value : null;

  static DateTime? _date(Object? value) =>
      value is String ? DateTime.tryParse(value)?.toUtc() : null;

  static String? _sha(Object? value) {
    final v = _string(value);
    return v != null && RegExp(r'^[a-fA-F0-9]{40}$').hasMatch(v)
        ? v.toLowerCase() : null;
  }

  static String? _artifactDigest(Object? value) {
    final v = _string(value);
    if (v == null) return null;
    final match = RegExp(r'^sha256:([a-fA-F0-9]{64})$').firstMatch(v);
    return match?.group(1)?.toLowerCase();
  }

  static bool isCandidateName(String name) {
    if (name.isEmpty || name.length > 140 ||
        name.contains('/') || name.contains('\\') ||
        name.contains('..') || name.startsWith('.') ||
        RegExp(r'[\x00-\x1f\x7f]').hasMatch(name)) {
      return false;
    }
    final lower = name.toLowerCase();
    if (RegExp(r'(^|[-_. ])(logs?|reports?|coverage|screenshots?|source|symbols?|mapping|test-results?|lint|trace|debug-symbols)([-_. ]|$)')
        .hasMatch(lower)) {
      return false;
    }
    // This is only a *candidate* filter, not an APK proof. The bounded R01/R02
    // archive inspector still needs to find valid signed Android packages.
    return RegExp(r'(^|[-_. ])(apk|apks|xapk|android|installer|universal)([-_. ]|$)')
        .hasMatch(lower) ||
        lower.endsWith('.apk') || lower.endsWith('.apks') ||
        lower.endsWith('.xapk') || lower.endsWith('.apkm');
  }

  Future<R04ActionsSelection> latest({
    String? workflow,
    String? branch,
    String? runId,
    String? runAttempt,
    String? commitSha,
    String? artifactId,
    String? artifactNamePattern,
  }) async {
    final repo = await _fetchObject(repoApi);
    final defaultBranch = _string(repo['default_branch']);
    if (defaultBranch == null) {
      throw const R04ActionsFailure('repository has no default branch');
    }
    final chosenBranch = branch?.trim().isNotEmpty == true
        ? branch!.trim() : defaultBranch;
    if (chosenBranch.length > 240 || chosenBranch.contains('..') ||
        RegExp(r'[\x00-\x20\x7f]').hasMatch(chosenBranch)) {
      throw const R04ActionsFailure('invalid selected branch');
    }
    final workflows = await _list('/actions/workflows', 'workflows');
    final validWorkflows = <int, String>{};
    for (final w in workflows) {
      final id = _positiveInt(w['id']);
      final name = _string(w['name']);
      if (id != null && name != null && w['state'] == 'active') {
        validWorkflows[id] = name;
      }
    }
    int? chosenWorkflow;
    if (workflow?.trim().isNotEmpty == true) {
      final requested = workflow!.trim();
      chosenWorkflow = int.tryParse(requested);
      if (chosenWorkflow == null) {
        final matches = validWorkflows.entries
            .where((e) => e.value == requested).toList();
        if (matches.length != 1) {
          throw const R04ActionsFailure('workflow name missing or ambiguous; select an ID');
        }
        chosenWorkflow = matches.single.key;
      }
      if (!validWorkflows.containsKey(chosenWorkflow)) {
        throw const R04ActionsFailure('unknown or inactive workflow');
      }
    }
    int? chosenRunId;
    if (runId?.trim().isNotEmpty == true) {
      chosenRunId = int.tryParse(runId!.trim());
      if (chosenRunId == null || chosenRunId <= 0) {
        throw const R04ActionsFailure('invalid manually selected run ID');
      }
    }
    int? selectedArtifactId;
    if (artifactId?.trim().isNotEmpty == true) {
      selectedArtifactId = int.tryParse(artifactId!.trim());
      if (selectedArtifactId == null || selectedArtifactId <= 0) {
        throw const R04ActionsFailure('invalid selected artifact ID');
      }
    }
    RegExp? filter;
    if (artifactNamePattern?.trim().isNotEmpty == true) {
      if (artifactNamePattern!.length > 120) {
        throw const R04ActionsFailure('artifact filter too long');
      }
      try { filter = RegExp(artifactNamePattern); }
      on FormatException { throw const R04ActionsFailure('invalid artifact filter'); }
    }
    final runs = await _list('/actions/runs', 'workflow_runs',
        {'branch': chosenBranch, 'status': 'success'});
    final goodRuns = runs.where((r) =>
        r['status'] == 'completed' && r['conclusion'] == 'success' &&
        r['head_branch'] == chosenBranch &&
        _sha(r['head_sha']) != null &&
        _positiveInt(r['run_attempt']) != null &&
        _positiveInt(r['workflow_id']) != null &&
        validWorkflows.containsKey(r['workflow_id']) &&
        (chosenWorkflow == null || r['workflow_id'] == chosenWorkflow) &&
        (chosenRunId == null || r['id'] == chosenRunId) &&
        _date(r['created_at']) != null &&
        _positiveInt(r['run_number']) != null).toList();
    goodRuns.sort((a, b) =>
        _date(b['created_at'])!.compareTo(_date(a['created_at'])!));
    if (goodRuns.isEmpty) {
      throw const R04ActionsFailure('no successful completed run for selected workflow/branch');
    }
    final selected = goodRuns.first;
    final selectedRunId = _positiveInt(selected['id'])!;
    final attempt = _positiveInt(selected['run_attempt'])!;
    final sha = _sha(selected['head_sha'])!;
    if (runAttempt?.trim().isNotEmpty == true &&
        int.tryParse(runAttempt!.trim()) != attempt) {
      throw const R04ActionsFailure('run attempt changed after manual selection');
    }
    if (commitSha?.trim().isNotEmpty == true &&
        _sha(commitSha!.trim()) != sha) {
      throw const R04ActionsFailure('commit SHA changed after manual selection');
    }
    final workflowId = _positiveInt(selected['workflow_id'])!;
    final artifacts = await _list('/actions/runs/$selectedRunId/artifacts', 'artifacts');
    final matches = <R04ActionsArchive>[];
    final current = now().toUtc();
    for (final raw in artifacts) {
      if (raw['expired'] != false) continue;
      final id = _positiveInt(raw['id']);
      final name = _string(raw['name']);
      final size = _positiveInt(raw['size_in_bytes']);
      final created = _date(raw['created_at']);
      final expires = _date(raw['expires_at']);
      if (id == null || name == null || size == null ||
          size > maxArchiveBytes || created == null || expires == null ||
          !expires.isAfter(current) || !isCandidateName(name) ||
          (selectedArtifactId != null && id != selectedArtifactId) ||
          (filter != null && !filter.hasMatch(name))) {
        continue;
      }
      // GitHub's archive_download_url is untrusted metadata: synthesize the
      // canonical in-repository API URL from the validated numeric ID.
      // An artifact belongs to one run/revision. Refuse inconsistent API
      // identity rather than treating a renamed/replaced ZIP as trusted.
      final boundRun = raw['workflow_run'];
      if (boundRun is Map &&
          (boundRun['id'] != selectedRunId || boundRun['head_sha'] != sha)) {
        throw const R04ActionsFailure('artifact run/commit provenance changed');
      }
      matches.add(R04ActionsArchive(
        artifactId: id, runId: selectedRunId, runAttempt: attempt,
        workflowId: workflowId, commitSha: sha, branch: chosenBranch,
        name: name, sizeBytes: size, createdAt: created, expiresAt: expires,
        archiveUrl: repoApi.replace(path: '${repoApi.path}/actions/artifacts/$id/zip'),
        archiveSha256: _artifactDigest(raw['digest']),
      ));
    }
    if (matches.isEmpty) {
      throw const R04ActionsFailure('latest successful run contains no eligible Android archive');
    }
    if (matches.length > 1) {
      throw const R04ActionsFailure(
        'multiple Android archives: supply an exact artifact-name filter');
    }
    return R04ActionsSelection(
      archive: matches.single,
      workflowName: validWorkflows[workflowId]!,
      runNumber: _positiveInt(selected['run_number'])!,
      runDate: _date(selected['created_at'])!,
    );
  }
}
