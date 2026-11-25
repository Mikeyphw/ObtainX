import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' show Response;
import 'package:obtainium/services/r04_github_actions.dart';
import 'package:obtainium/widgets/r04_actions_history_dialog.dart';

const commit = 'aabbccddeeff00112233445566778899aabbccdd';
const digest = 'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
final utc = DateTime.utc(2026, 11, 15);

Map<String, dynamic> run(int id, {String status = 'completed',
  String conclusion = 'success', String branch = 'main', int attempt = 1,
  String sha = commit}) => {
  'id': id, 'workflow_id': 7, 'head_branch': branch,
  'run_attempt': attempt, 'run_number': id, 'head_sha': sha,
  'created_at': '2026-11-15T08:00:00Z', 'status': status,
  'conclusion': conclusion,
};

Map<String, dynamic> artifact(int id, {String name = 'android-apk',
  String? checksum = digest, bool expired = false}) => {
  'id': id, 'name': name, 'size_in_bytes': 1024,
  'expired': expired, 'digest': checksum,
  'created_at': '2026-11-15T08:01:00Z',
  'expires_at': '2026-11-18T08:00:00Z',
  'workflow_run': {'id': 12, 'head_sha': commit},
};

class MockActions {
  List<Map<String, dynamic>> runs = [run(12)];
  List<Map<String, dynamic>> artifacts = [artifact(41)];
  bool unauthorised = false;
  int calls = 0;

  Future<Response> request(Uri uri) async {
    calls++;
    if (unauthorised) return Response('{}', 401);
    if (uri.path == '/repos/o/r') {
      return Response(jsonEncode({'default_branch': 'main'}), 200);
    }
    final page = int.parse(uri.queryParameters['page'] ?? '1');
    List<Map<String, dynamic>> paged(List<Map<String, dynamic>> entries) =>
        entries.skip((page - 1) * 100).take(100).toList();
    if (uri.path.endsWith('/actions/workflows')) {
      return Response(jsonEncode({'workflows': paged([
        {'id': 7, 'name': 'Build Android', 'state': 'active'},
      ])}), 200);
    }
    if (uri.path.endsWith('/actions/runs')) {
      return Response(jsonEncode({'workflow_runs': paged(runs)}), 200);
    }
    if (uri.path.endsWith('/actions/runs/12/artifacts')) {
      return Response(jsonEncode({'artifacts': paged(artifacts)}), 200);
    }
    return Response('{}', 404);
  }

  R04GitHubActionsCatalog catalog() => R04GitHubActionsCatalog(
    repoApi: Uri.parse('https://api.github.com/repos/o/r'),
    request: request, now: () => utc,
  );
}

void main() {
  test('manual history is read-only and offers exact run/attempt/artifact ID', () async {
    final mock = MockActions();
    final rows = await mock.catalog().history();
    expect(rows, hasLength(1));
    expect(rows.single.canSelect, isTrue);
    expect(rows.single.artifactId, 41);
    expect(rows.single.runId, 12);
    expect(rows.single.runAttempt, 1);
    expect(rows.single.commitSha, commit);
    expect(rows.single.archiveSha256, isNotNull);
  });

  test('failed and in-progress runs are visible but never selectable', () async {
    final mock = MockActions();
    mock.runs = [run(12, conclusion: 'failure'),
      run(13, status: 'in_progress', conclusion: 'success')];
    final rows = await mock.catalog().history();
    expect(rows, hasLength(2));
    expect(rows.every((row) => !row.canSelect), isTrue);
  });

  test('expired, unverified and forged-run artifacts cannot be chosen', () async {
    final mock = MockActions();
    mock.artifacts = [artifact(41, expired: true), artifact(42, checksum: null)];
    var rows = await mock.catalog().history();
    expect(rows.every((row) => !row.canSelect), isTrue);
    mock.artifacts = [artifact(41)];
    mock.artifacts.first['workflow_run'] = {'id': 13, 'head_sha': commit};
    rows = await mock.catalog().history();
    expect(rows.single.canSelect, isFalse);
  });

  test('duplicate archive names are resolved by artifact ID, never by name alone', () async {
    final mock = MockActions();
    mock.artifacts = [artifact(41), artifact(42)];
    final rows = await mock.catalog().history();
    expect(rows.where((row) => row.canSelect), hasLength(2));
    await expectLater(mock.catalog().latest(), throwsA(isA<R04ActionsFailure>()));
    final exact = await mock.catalog().latest(artifactId: '42', runId: '12',
      runAttempt: '1', commitSha: commit);
    expect(exact.archive.artifactId, 42);
    await expectLater(mock.catalog().latest(artifactId: '999'),
      throwsA(isA<R04ActionsFailure>()));
  });

  test('changed attempt, SHA and branch fail closed after manual selection', () async {
    final mock = MockActions();
    await expectLater(mock.catalog().latest(runId: '12', runAttempt: '2'),
      throwsA(isA<R04ActionsFailure>()));
    await expectLater(mock.catalog().latest(runId: '12', commitSha:
      '11223344556677889900aabbccddeeff11223344'),
      throwsA(isA<R04ActionsFailure>()));
    await expectLater(mock.catalog().latest(branch: 'other'),
      throwsA(isA<R04ActionsFailure>()));
  });

  test('API authentication errors never turn into selectable history', () async {
    final mock = MockActions()..unauthorised = true;
    await expectLater(mock.catalog().history(),
      throwsA(isA<R04ActionsFailure>().having((e) => e.statusCode, 'status', 401)));
  });

  testWidgets('manual browser labels non-installable entries and selects only valid',
      (tester) async {
    R04ActionsHistoryItem? chosen;
    final mock = MockActions();
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: Builder(
      builder: (context) => FilledButton(onPressed: () async {
        chosen = await showDialog<R04ActionsHistoryItem>(context: context,
          builder: (_) => R04ActionsHistoryDialog(
            initialRepositoryUrl: 'https://github.com/o/r',
            now: () => utc,
            loadHistory: (repo, branch, workflow) => mock.catalog().history(
              branch: branch, workflow: workflow),
          ));
      }, child: const Text('Open browser')),
    ))));
    await tester.tap(find.text('Open browser'));
    await tester.pumpAndSettle();
    expect(find.text('Manual GitHub Actions history'), findsOneWidget);
    await tester.tap(find.text('Browse runs'));
    await tester.pumpAndSettle();
    expect(find.text('Select'), findsOneWidget);
    await tester.tap(find.text('Select'));
    await tester.pumpAndSettle();
    expect(chosen?.artifactId, 41);
  });

  testWidgets('R09 history cannot select an expired artifact or stale branch', (tester) async {
    final mock = MockActions();
    var clock = utc;
    R04ActionsHistoryItem? chosen;
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: Builder(
      builder: (context) => FilledButton(onPressed: () async {
        chosen = await showDialog<R04ActionsHistoryItem>(context: context,
          builder: (_) => R04ActionsHistoryDialog(
            initialRepositoryUrl: 'https://github.com/o/r',
            now: () => clock,
            loadHistory: (repo, branch, workflow) => mock.catalog().history(
              branch: branch, workflow: workflow),
          ));
      }, child: const Text('Open browser')),
    ))));
    await tester.tap(find.text('Open browser'));
    await tester.pumpAndSettle();
    expect(tester.widget<TextField>(find.byType(TextField).first).readOnly, isTrue);
    await tester.tap(find.text('Browse runs'));
    await tester.pumpAndSettle();
    expect(find.text('Select'), findsOneWidget);
    clock = DateTime.utc(2026, 11, 19);
    await tester.tap(find.text('Select'));
    await tester.pumpAndSettle();
    expect(chosen, isNull);
    expect(find.text('Select'), findsNothing);
    clock = utc;
    await tester.tap(find.text('Browse runs'));
    await tester.pumpAndSettle();
    expect(find.text('Select'), findsOneWidget);
    await tester.enterText(find.byType(TextField).at(1), 'different');
    await tester.pumpAndSettle();
    expect(find.text('Select'), findsNothing);
    expect(chosen, isNull);
    await tester.tap(find.text('Close'));
    await tester.pumpAndSettle();
  });

}
