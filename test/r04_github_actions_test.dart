import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' show Response;
import 'package:obtainium/services/r04_github_actions.dart';

const _sha = 'aabbccddeeff00112233445566778899aabbccdd';
const _otherSha = '11223344556677889900aabbccddeeff11223344';
final _time = DateTime.utc(2026, 11, 15);

Map<String, dynamic> _workflow(int id, {String name = 'Build APK', String state = 'active'}) =>
    {'id': id, 'name': name, 'state': state};
Map<String, dynamic> _run(int id, {int workflow = 7, String branch = 'main',
    String status = 'completed', String conclusion = 'success',
    String sha = _sha, int attempt = 1, String created = '2026-11-14T09:00:00Z'}) => {
  'id': id, 'workflow_id': workflow, 'head_branch': branch,
  'head_sha': sha, 'run_attempt': attempt, 'run_number': id,
  'status': status, 'conclusion': conclusion, 'created_at': created,
};
Map<String, dynamic> _artifact(int id, {String name = 'android-arm64-apk',
    bool expired = false, int size = 1024,
    String expires = '2026-11-18T00:00:00Z', String? digest}) => {
  'id': id, 'name': name, 'expired': expired, 'size_in_bytes': size,
  'created_at': '2026-11-14T09:05:00Z', 'expires_at': expires,
  'digest': digest,
  'archive_download_url': 'https://attacker.invalid/files/fake.zip',
};

class _GithubMock {
  final workflows = <Map<String, dynamic>>[_workflow(7)];
  final runs = <Map<String, dynamic>>[_run(12)];
  final artifacts = <Map<String, dynamic>>[_artifact(41)];
  final calls = <Uri>[];
  int? forcedStatus;
  bool badJson = false;
  bool missingCollection = false;
  bool externalBase = false;
  String defaultBranch = 'main';

  Future<Response> request(Uri uri) async {
    calls.add(uri);
    if (forcedStatus != null) return Response('{}', forcedStatus!);
    if (badJson) return Response('broken json', 200);
    final page = int.parse(uri.queryParameters['page'] ?? '1');
    final start = (page - 1) * 100;
    List<Map<String, dynamic>> batch(List<Map<String, dynamic>> list) =>
        start < list.length ? list.skip(start).take(100).toList() : [];
    if (uri.path == '/repos/o/r') {
      return Response(jsonEncode({'default_branch': defaultBranch}), 200);
    }
    if (uri.path.endsWith('/actions/workflows')) {
      return Response(jsonEncode(missingCollection ? {'wrong': []} :
          {'workflows': batch(workflows)}), 200);
    }
    if (uri.path.endsWith('/actions/runs')) {
      return Response(jsonEncode({'workflow_runs': batch(runs)}), 200);
    }
    if (uri.path.endsWith('/actions/runs/12/artifacts') ||
        uri.path.endsWith('/actions/runs/13/artifacts') ||
        uri.path.endsWith('/actions/runs/999/artifacts')) {
      return Response(jsonEncode({'artifacts': batch(artifacts)}), 200);
    }
    return Response('{}', 404);
  }

  R04GitHubActionsCatalog catalog({int maxPages = 20}) =>
      R04GitHubActionsCatalog(
        repoApi: Uri.parse(externalBase
          ? 'https://api.evil.invalid/repos/o/r'
          : 'https://api.github.com/repos/o/r'),
        request: request, now: () => _time,
        maximumPages: maxPages,
      );
}

void main() {
  test('latest successful completed default-branch archive and exact identities', () async {
    final mock = _GithubMock();
    final selected = await mock.catalog().latest();
    expect(selected.version, 'actions-12-a1-${_sha.substring(0, 12)}');
    expect(selected.archive.workflowId, 7);
    expect(selected.archive.runId, 12);
    expect(selected.archive.runAttempt, 1);
    expect(selected.archive.commitSha, _sha);
    expect(selected.archive.fileName, 'android-arm64-apk.zip');
    expect(selected.archive.archiveUrl.toString(),
      'https://api.github.com/repos/o/r/actions/artifacts/41/zip');
    expect(mock.calls.where((u) => u.path.endsWith('/actions/runs')).single
        .queryParameters['branch'], 'main');
  });

  test('artifact URL is constructed from validated identity, never provided URL', () async {
    final selected = await _GithubMock().catalog().latest();
    expect(selected.archive.archiveUrl.host, 'api.github.com');
    expect(selected.archive.archiveUrl.toString(), isNot(contains('attacker')));
  });

  test('user branch and workflow ID select only exact completed success', () async {
    final mock = _GithubMock();
    mock.workflows.add(_workflow(8, name: 'Publish'));
    mock.runs..clear()..addAll([
      _run(999, workflow: 7, branch: 'stable', created: '2026-11-15T08:00:00Z'),
      _run(13, workflow: 8, branch: 'stable', attempt: 3,
        created: '2026-11-14T10:00:00Z', sha: _otherSha),
      _run(12, workflow: 8, branch: 'main', created: '2026-11-15T09:00:00Z'),
      _run(14, workflow: 8, branch: 'stable', conclusion: 'failure',
        created: '2026-11-15T10:00:00Z'),
    ]);
    final selected = await mock.catalog().latest(workflow: '8', branch: 'stable');
    expect(selected.archive.runId, 13);
    expect(selected.archive.runAttempt, 3);
    expect(selected.archive.commitSha, _otherSha);
  });

  test('failure and in-progress run artifacts never become automatic updates', () async {
    final mock = _GithubMock();
    mock.runs..clear()..addAll([
      _run(12, conclusion: 'failure'),
      _run(13, status: 'in_progress', conclusion: 'success'),
    ]);
    await expectLater(mock.catalog().latest(), throwsA(isA<R04ActionsFailure>()));
  });

  test('missing or ambiguous workflow selector is refused', () async {
    final mock = _GithubMock();
    mock.workflows.add(_workflow(8));
    await expectLater(mock.catalog().latest(workflow: 'Build APK'),
        throwsA(isA<R04ActionsFailure>()));
    await expectLater(mock.catalog().latest(workflow: '999'),
        throwsA(isA<R04ActionsFailure>()));
    await expectLater(mock.catalog().latest(workflow: 'Build APK', branch: 'main'),
        throwsA(isA<R04ActionsFailure>()));
  });

  test('manual run ID remains confined to successful branch/workflow', () async {
    final mock = _GithubMock();
    mock.runs..clear()..addAll([
      _run(13, created: '2026-11-15T08:00:00Z'),
      _run(12, created: '2026-11-14T08:00:00Z'),
    ]);
    final selection = await mock.catalog().latest(runId: '12');
    expect(selection.archive.runId, 12);
    await expectLater(mock.catalog().latest(runId: 'bogus'),
      throwsA(isA<R04ActionsFailure>()));
    await expectLater(mock.catalog().latest(runId: '99'),
      throwsA(isA<R04ActionsFailure>()));
  });

  test('expired, oversized and non-Android artifacts cannot be selected', () async {
    final mock = _GithubMock();
    mock.artifacts..clear()..addAll([
      _artifact(41, expired: true),
      _artifact(42, size: R04GitHubActionsCatalog.maxArchiveBytes + 1),
      _artifact(43, name: 'build-log'),
      _artifact(44, name: 'source.zip'),
      _artifact(45, expires: '2026-11-14T00:00:00Z'),
      _artifact(46, name: '../android.apk'),
    ]);
    await expectLater(mock.catalog().latest(), throwsA(isA<R04ActionsFailure>()));
  });

  test('multiple Android archives require user artifact-name selector', () async {
    final mock = _GithubMock();
    mock.artifacts.add(_artifact(42, name: 'android-x86-apk'));
    await expectLater(mock.catalog().latest(), throwsA(isA<R04ActionsFailure>()));
    final selected = await mock.catalog().latest(artifactNamePattern: r'arm64');
    expect(selected.archive.artifactId, 41);
  });

  test('bad artifact-name filter and malicious branch are refused', () async {
    final mock = _GithubMock();
    await expectLater(mock.catalog().latest(artifactNamePattern: '['),
      throwsA(isA<R04ActionsFailure>()));
    await expectLater(mock.catalog().latest(branch: 'main\nAuthorization: x'),
      throwsA(isA<R04ActionsFailure>()));
  });

  test('archive SHA-256 is not an APK hash or signature attestation', () async {
    final mock = _GithubMock();
    final hex = List<String>.filled(64, 'a').join();
    mock.artifacts[0]['digest'] = 'sha256:$hex';
    final selection = await mock.catalog().latest();
    expect(selection.archive.archiveSha256, hex);
    mock.artifacts[0]['digest'] = 'md5:${List<String>.filled(32, 'a').join()}';
    expect((await mock.catalog().latest()).archive.archiveSha256, isNull);
  });

  test('malformed response, authentication and throttling refuse candidates', () async {
    final mock = _GithubMock();
    mock.badJson = true;
    await expectLater(mock.catalog().latest(), throwsA(isA<R04ActionsFailure>()));
    mock.badJson = false;
    for (final code in [401, 403, 429, 503]) {
      mock.forcedStatus = code;
      await expectLater(mock.catalog().latest(), throwsA(isA<R04ActionsFailure>()
        .having((e) => e.statusCode, 'status', code)));
    }
    mock.forcedStatus = null;
    mock.missingCollection = true;
    await expectLater(mock.catalog().latest(), throwsA(isA<R04ActionsFailure>()));
  });

  test('pagination searches across 100-workflow and 100-run boundaries', () async {
    final mock = _GithubMock();
    mock.workflows..clear()..addAll([
      for (var i = 1; i <= 100; i++) _workflow(i, name: 'Other-$i'),
      _workflow(201, name: 'Publish'),
    ]);
    mock.runs..clear()..addAll([
      for (var i = 1; i <= 100; i++)
        _run(i + 1000, workflow: 1, created: '2026-11-13T00:00:00Z'),
      _run(12, workflow: 201, created: '2026-11-14T10:00:00Z'),
    ]);
    final selected = await mock.catalog().latest(workflow: '201');
    expect(selected.archive.workflowId, 201);
    expect(mock.calls.where((c) => c.path.endsWith('/actions/workflows'))
        .map((c) => c.queryParameters['page']), contains('2'));
    expect(mock.calls.where((c) => c.path.endsWith('/actions/runs'))
        .map((c) => c.queryParameters['page']), contains('2'));
  });

  test('pagination is fail-closed at configured budget', () async {
    final mock = _GithubMock();
    mock.workflows..clear()..addAll([
      for (var i = 1; i <= 101; i++) _workflow(i),
    ]);
    await expectLater(mock.catalog(maxPages: 1).latest(),
        throwsA(isA<R04ActionsFailure>()));
  });

  test('cross-origin API URL is refused even before network use', () {
    final mock = _GithubMock()..externalBase = true;
    expect(() => mock.catalog(), throwsA(isA<R04ActionsFailure>()));
    expect(mock.calls, isEmpty);
  });
}
