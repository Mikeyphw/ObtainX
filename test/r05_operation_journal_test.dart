import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/services/r05_operation_journal.dart';
import 'package:obtainium/services/r05_operation_receipt.dart';

void main() {
  late Directory temp;
  late R05OperationJournal journal;
  setUp(() async {
    temp = await Directory.systemTemp.createTemp('r05-journal-test-');
    journal = R05OperationJournal(testingRoot: temp);
  });
  tearDown(() async { if (await temp.exists()) await temp.delete(recursive: true); });

  Future<R05OperationReceipt> start() => journal.begin(
    listingKey: 'store:com.example', packageId: 'com.example',
    backend: 'external', kind: 'bundle', fileNames: <String>['bundle.apkm'],
    downloadSha256: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  );

  test('one atomic persisted receipt per attempt survives process recreation', () async {
    final record = await start();
    final reopened = R05OperationJournal(testingRoot: temp);
    final all = await reopened.list();
    expect(all.single.id, record.id);
    expect(all.single.stage, R05InstallStage.pending);
    await reopened.transition(record.id, R05InstallStage.handedOff);
    expect((await journal.list()).single.stage, R05InstallStage.handedOff);
  });
  test('startup converts interrupted pending into unknown, not success or cancel', () async {
    await start();
    final resumed = R05OperationJournal(testingRoot: temp);
    await resumed.recoverInterruptedOnce();
    expect((await resumed.list()).single.stage, R05InstallStage.unknown);
  });
  test('approval remains recoverable across process restart', () async {
    final record = await start();
    await journal.transition(record.id, R05InstallStage.awaitingApproval);
    final resumed = R05OperationJournal(testingRoot: temp);
    await resumed.recoverInterruptedOnce();
    expect((await resumed.list()).single.stage, R05InstallStage.awaitingApproval);
  });
  test('parallel starts are serialized and have distinct IDs', () async {
    final tasks = await Future.wait(List<Future<R05OperationReceipt>>.generate(8, (_) => start()));
    expect(tasks.map((r) => r.id).toSet().length, 8);
    expect((await journal.list()).length, 8);
  });
  test('duplicate unresolved attempts are never attributed to one broadcast', () async {
    final first = await start();
    expect((await journal.uniqueUnresolved('store:com.example'))?.id, first.id);
    final second = await start();
    expect(await journal.uniqueUnresolved('store:com.example'), isNull);
    await journal.transition(first.id, R05InstallStage.failed);
    expect((await journal.uniqueUnresolved('store:com.example'))?.id, second.id);
  });
  test('unknown journal file and symlink are refused, not deleted', () async {
    final data = Directory('${temp.path}/r05-install-operations');
    await data.create();
    final suspect = File('${data.path}/run-v3-catalog.json');
    await suspect.writeAsString('{}');
    await expectLater(journal.list(), throwsFormatException);
    expect(await suspect.exists(), true);
    await suspect.delete();
    await File('${temp.path}/target').writeAsString('private');
    await Link('${data.path}/r05_11111111_123456789abcdef0.json')
        .create('${temp.path}/target');
    await expectLater(journal.list(), throwsFormatException);
  });
}
