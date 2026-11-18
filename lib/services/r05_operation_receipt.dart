/// R05 install attempt: source-bound evidence, not an installer success guess.
/// No signed storage URL, token, raw file path, or private certificate bytes are persisted.
library;

import 'dart:convert';

const String r05ExtraApprovalPreference = 'r05ExtraApprovalBeforeHandoff';

enum R05InstallStage {
  pending, awaitingApproval, handedOff, confirmed, failed, cancelled, unknown,
}

const _r05MaxText = 256;
final _r05Hex64 = RegExp(r'^[a-f0-9]{64}$');
final _r05Sha40 = RegExp(r'^[a-f0-9]{40}$');
final _r05Id = RegExp(r'^[A-Za-z0-9_-]{16,90}$');

String? _r05Text(Object? value, {int max = _r05MaxText}) {
  if (value == null) return null;
  if (value is! String || value.length > max || value.contains(RegExp(r'[\r\n\x00-\x1f]'))) {
    throw const FormatException('Invalid operation receipt text');
  }
  return value;
}

String? _r05Digest(Object? value) {
  final v = _r05Text(value);
  if (v != null && !_r05Hex64.hasMatch(v)) throw const FormatException('Invalid SHA-256');
  return v;
}

int? _r05Positive(Object? value) {
  if (value == null) return null;
  if (value is! int || value < 1) throw const FormatException('Invalid positive identifier');
  return value;
}

/// Independent Android package/version evidence; never a timer or an installer launch.
class R05AndroidEvidence {
  const R05AndroidEvidence({
    required this.packageName,
    required this.exactAttemptMatches,
    this.versionCode,
    this.installedSignerSha256,
  });
  final String packageName;
  final int? versionCode;
  final String? installedSignerSha256;
  final bool exactAttemptMatches;
}

class R05OperationReceipt {
  const R05OperationReceipt({
    required this.id,
    required this.listingKey,
    required this.packageId,
    required this.stage,
    required this.createdUtc,
    required this.updatedUtc,
    required this.revision,
    required this.backend,
    required this.fileNames,
    required this.kind,
    this.sourceHost,
    this.sourceBranch,
    this.workflow,
    this.runId,
    this.runAttempt,
    this.commitSha,
    this.artifactId,
    this.downloadSha256,
    this.archiveSignerSha256,
    this.installedSignerSha256,
    this.androidCode,
    this.expectedVersionCode,
    this.androidVersionCode,
    this.verifiedUtc,
    this.reason,
  });

  final String id, listingKey, packageId, backend, kind;
  final R05InstallStage stage;
  final DateTime createdUtc, updatedUtc;
  final int revision;
  final List<String> fileNames;
  final String? sourceHost, sourceBranch, workflow, commitSha, downloadSha256;
  final String? archiveSignerSha256, installedSignerSha256, reason;
  final int? runId, runAttempt, artifactId, androidCode, expectedVersionCode, androidVersionCode;
  final DateTime? verifiedUtc;

  static R05OperationReceipt start({
    required String id,
    required String listingKey,
    required String packageId,
    required String backend,
    required String kind,
    required List<String> fileNames,
    String? sourceHost,
    String? sourceBranch,
    String? workflow,
    int? runId,
    int? runAttempt,
    String? commitSha,
    int? artifactId,
    int? expectedVersionCode,
    String? downloadSha256,
    String? archiveSignerSha256,
    DateTime? now,
  }) {
    final time = (now ?? DateTime.now()).toUtc();
    final item = R05OperationReceipt(
      id: id, listingKey: listingKey, packageId: packageId,
      backend: backend, kind: kind, fileNames: List.unmodifiable(fileNames),
      stage: R05InstallStage.pending, revision: 0,
      createdUtc: time, updatedUtc: time,
      sourceHost: sourceHost, sourceBranch: sourceBranch, workflow: workflow,
      runId: runId, runAttempt: runAttempt, commitSha: commitSha,
      artifactId: artifactId, expectedVersionCode: expectedVersionCode, downloadSha256: downloadSha256,
      archiveSignerSha256: archiveSignerSha256,
    );
    return R05OperationReceipt.fromJson(item.toJson());
  }

  static const _next = <R05InstallStage, Set<R05InstallStage>>{
    R05InstallStage.pending: {R05InstallStage.awaitingApproval, R05InstallStage.handedOff,
      R05InstallStage.confirmed, R05InstallStage.failed, R05InstallStage.cancelled, R05InstallStage.unknown},
    R05InstallStage.awaitingApproval: {R05InstallStage.handedOff,
      R05InstallStage.confirmed, R05InstallStage.failed, R05InstallStage.cancelled, R05InstallStage.unknown},
    R05InstallStage.handedOff: {R05InstallStage.confirmed, R05InstallStage.failed, R05InstallStage.unknown},
    R05InstallStage.unknown: {R05InstallStage.confirmed, R05InstallStage.failed},
    R05InstallStage.confirmed: {}, R05InstallStage.failed: {}, R05InstallStage.cancelled: {},
  };

  R05OperationReceipt transition(R05InstallStage next, {
    R05AndroidEvidence? evidence,
    int? androidCode,
    String? reason,
    DateTime? now,
  }) {
    if (!_next[stage]!.contains(next)) {
      throw StateError('R05 illegal install state transition: $stage to $next');
    }
    final time = (now ?? DateTime.now()).toUtc();
    if (time.isBefore(updatedUtc)) throw StateError('R05 nonmonotonic event timestamp');
    if (next == R05InstallStage.confirmed &&
        (evidence == null || !evidence.exactAttemptMatches ||
         evidence.packageName != packageId ||
         (archiveSignerSha256 != null &&
          evidence.installedSignerSha256 != archiveSignerSha256) ||
         (expectedVersionCode != null && evidence.versionCode != expectedVersionCode) ||
         (evidence.versionCode != null && evidence.versionCode! < 0))) {
      throw StateError('R05 confirmation needs independent matching Android evidence');
    }
    return R05OperationReceipt.fromJson({
      ...toJson(), 'stage': next.name, 'revision': revision + 1,
      'updatedUtc': time.toIso8601String(),
      'verifiedUtc': next == R05InstallStage.confirmed ? time.toIso8601String() : null,
      'androidCode': androidCode,
      'androidVersionCode': evidence?.versionCode,
      'installedSignerSha256': evidence?.installedSignerSha256,
      'reason': reason,
    });
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
    'schema': 1, 'id': id, 'listingKey': listingKey, 'packageId': packageId,
    'stage': stage.name, 'createdUtc': createdUtc.toIso8601String(),
    'updatedUtc': updatedUtc.toIso8601String(), 'revision': revision,
    'backend': backend, 'kind': kind, 'fileNames': fileNames,
    'sourceHost': sourceHost, 'sourceBranch': sourceBranch,
    'workflow': workflow, 'runId': runId, 'runAttempt': runAttempt,
    'commitSha': commitSha, 'artifactId': artifactId,
    'downloadSha256': downloadSha256, 'archiveSignerSha256': archiveSignerSha256,
    'installedSignerSha256': installedSignerSha256,
    'androidCode': androidCode, 'expectedVersionCode': expectedVersionCode, 'androidVersionCode': androidVersionCode,
    'verifiedUtc': verifiedUtc?.toIso8601String(), 'reason': reason,
  };

  factory R05OperationReceipt.fromJson(Map<String, dynamic> raw) {
    const keys = <String>{'schema','id','listingKey','packageId','stage','createdUtc',
      'updatedUtc','revision','backend','kind','fileNames','sourceHost','sourceBranch',
      'workflow','runId','runAttempt','commitSha','artifactId','downloadSha256',
      'archiveSignerSha256','installedSignerSha256','androidCode','expectedVersionCode','androidVersionCode',
      'verifiedUtc','reason'};
    if (raw.keys.toSet().difference(keys).isNotEmpty ||
        keys.difference(raw.keys.toSet()).isNotEmpty || raw['schema'] != 1) {
      throw const FormatException('Unrecognized R05 receipt schema');
    }
    final id = _r05Text(raw['id']);
    final listing = _r05Text(raw['listingKey']);
    final package = _r05Text(raw['packageId']);
    final backend = _r05Text(raw['backend']);
    final kind = _r05Text(raw['kind']);
    if (id == null || !_r05Id.hasMatch(id) || listing == null || listing.isEmpty ||
        package == null || package.isEmpty || backend == null || backend.isEmpty ||
        kind == null || kind.isEmpty || raw['revision'] is! int || raw['revision'] < 0) {
      throw const FormatException('Invalid R05 receipt identity');
    }
    final stage = R05InstallStage.values.where((v) => v.name == raw['stage']).toList();
    final files = raw['fileNames'];
    if (stage.length != 1 || files is! List || files.length > 96 ||
        files.any((v) => v is! String || v.isEmpty || v.length > 180 ||
            v.contains('/') || v.contains('\\') || v == '.' || v == '..')) {
      throw const FormatException('Invalid R05 receipt stage or filenames');
    }
    DateTime date(String key) {
      final val = _r05Text(raw[key], max: 48);
      if (val == null) throw const FormatException('Missing timestamp');
      final dt = DateTime.tryParse(val);
      if (dt == null || !val.endsWith('Z')) throw const FormatException('Invalid UTC timestamp');
      return dt.toUtc();
    }
    final created = date('createdUtc'), updated = date('updatedUtc');
    final verified = raw['verifiedUtc'] == null ? null : date('verifiedUtc');
    if (updated.isBefore(created) ||
        ((stage.single == R05InstallStage.confirmed) != (verified != null)) ||
        (verified != null && verified.isBefore(created))) {
      throw const FormatException('Inconsistent R05 verification timestamps');
    }
    final sha = _r05Text(raw['commitSha'], max: 40);
    if (sha != null && !_r05Sha40.hasMatch(sha)) throw const FormatException('Invalid source commit');
    final code = raw['androidCode'];
    final version = raw['androidVersionCode'];
    final expectedVersion = raw['expectedVersionCode'];
    if ((code != null && code is! int) ||
        (expectedVersion != null && (expectedVersion is! int || expectedVersion < 0)) ||
        (version != null && (version is! int || version < 0))) {
      throw const FormatException('Invalid Android result');
    }
    final sourceHost = _r05Text(raw['sourceHost']);
    if (sourceHost != null && (sourceHost.contains('@') || sourceHost.contains('/') || sourceHost.contains('?'))) {
      throw const FormatException('Unsafe source host');
    }
    return R05OperationReceipt(
      id: id, listingKey: listing, packageId: package, stage: stage.single,
      createdUtc: created, updatedUtc: updated, revision: raw['revision'] as int,
      backend: backend, kind: kind, fileNames: List<String>.unmodifiable(files.cast<String>()),
      sourceHost: sourceHost, sourceBranch: _r05Text(raw['sourceBranch']),
      workflow: _r05Text(raw['workflow']), runId: _r05Positive(raw['runId']),
      runAttempt: _r05Positive(raw['runAttempt']), commitSha: sha,
      artifactId: _r05Positive(raw['artifactId']),
      downloadSha256: _r05Digest(raw['downloadSha256']),
      archiveSignerSha256: _r05Digest(raw['archiveSignerSha256']),
      installedSignerSha256: _r05Digest(raw['installedSignerSha256']),
      androidCode: code as int?, expectedVersionCode: expectedVersion as int?,
      androidVersionCode: version as int?,
      verifiedUtc: verified, reason: _r05Text(raw['reason']),
    );
  }

  String encode() => jsonEncode(toJson());
  static R05OperationReceipt decode(String json) {
    final v = jsonDecode(json);
    if (v is! Map<String, dynamic>) throw const FormatException('Invalid R05 receipt JSON');
    return R05OperationReceipt.fromJson(v);
  }
}
