import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/services/r05_operation_journal.dart';
import 'package:obtainium/services/r05_operation_receipt.dart';
import 'package:obtainium/services/r07_process_owner.dart';

void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
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
    await data.create(recursive: true);
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
  test('large terminal archive cannot suppress new or unresolved operations', () async {
    final root = await Directory('${temp.path}/r05-install-operations').create();
    const channel = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
    const other = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
    final created = DateTime.utc(2026, 1);
    for (var i = 0; i < 520; i++) {
      final id = 'r05_history_${i.toString().padLeft(8, '0')}';
      final item = R05OperationReceipt.start(id: id, listingKey: 'store:com.example',
        packageId: 'com.example', backend: 'external', kind: 'apk', fileNames: const ['base.apk'],
        channelFingerprint: i.isEven ? channel : other, releaseFingerprint: channel,
        now: created).transition(R05InstallStage.failed, now: created);
      await File('${root.path}/$id.json').writeAsString(item.encode());
    }
    await File('${root.path}/.r05_history_00000000-aaaaaaaaaaaaaaaaaaaaaaaa.tmp').writeAsString('staging');
    await journal.recoverInterrupted();
    final pending = await start();
    final preview = await journal.previewTerminalBefore(DateTime.utc(2026, 2), channel: channel);
    expect(preview.entries.length, 260);
    expect(await journal.pruneTerminalBefore(preview.cutoff, channel: channel, preview: preview), 260);
    expect((await journal.list()).length, 261);
    expect((await journal.uniqueUnresolved(pending.listingKey))?.id, pending.id);
    final corrupt = File('${temp.path}/r05-install-operations.history/r05_corrupt_00000001.json');
    await corrupt.writeAsString('{');
    final activity = await journal.readForActivity();
    expect(activity.unreadableCount, 1);
    expect(activity.receipts.any((item) => item.id == pending.id), isTrue);
    await expectLater(journal.previewTerminalBefore(DateTime.utc(2026, 2)), throwsFormatException);
    expect(await corrupt.readAsString(), '{');
  });

  test('live process owner is not marked interrupted by another journal', () async {
    final owner = await R07ProcessOwner.capture();
    final receipt = await journal.begin(listingKey: 'store:com.example', packageId: 'com.example',
      backend: 'external', kind: 'apk', fileNames: const ['base.apk'], processOwner: owner.encode());
    final reopened = R05OperationJournal(testingRoot: temp);
    await reopened.recoverInterrupted();
    expect((await reopened.list()).single.id, receipt.id);
    expect((await reopened.list()).single.stage, R05InstallStage.pending);
  });

  test('concurrent exact retention preview cannot delete another channel or unknown history', () async {
    const channel = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
    const other = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
    Future<R05OperationReceipt> failed(String? selected) async {
      final receipt = await journal.begin(listingKey: 'store:com.example', packageId: 'com.example',
        backend: 'external', kind: 'apk', fileNames: const ['base.apk'], channelFingerprint: selected);
      return journal.transition(receipt.id, R05InstallStage.failed);
    }
    final first = await failed(channel);
    final second = await failed(other);
    final unknown = await failed(null);
    final cutoff = DateTime.now().add(const Duration(days: 1));
    final preview = await journal.previewTerminalBefore(cutoff, channel: channel);
    expect(preview.entries.keys, [first.id]);
    final outcomes = await Future.wait([for (final owner in [journal, R05OperationJournal(testingRoot: temp)])
      () async {
        try { return await owner.pruneTerminalBefore(cutoff, channel: channel, preview: preview); }
        catch (_) { return -1; }
      }(),
    ]);
    expect(outcomes.toSet(), {1, -1});
    expect((await journal.list()).map((row) => row.id).toSet(), {second.id, unknown.id});
    expect((await journal.previewTerminalBefore(cutoff)).entries.keys, [second.id]);
  });

  test('retry retains exact immutable parent and refuses stale channel', () async {
    const channel = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
    const other = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
    Future<R05OperationReceipt> begin(String selected, {String? parent}) => journal.begin(
      listingKey: 'store:com.example', packageId: 'com.example', backend: 'external',
      kind: 'apk', fileNames: const ['base.apk'], channelFingerprint: selected,
      releaseFingerprint: channel, parentAttemptId: parent);
    final parent = await begin(channel);
    await journal.transition(parent.id, R05InstallStage.failed);
    await expectLater(begin(other, parent: parent.id), throwsStateError);
    final retry = await begin(channel, parent: parent.id);
    expect(retry.parentAttemptId, parent.id);
    expect(retry.id, isNot(parent.id));
    final preview = await journal.previewTerminalBefore(DateTime.now().add(const Duration(days: 1)), channel: channel);
    expect(preview.entries.containsKey(parent.id), isFalse);
  });

}
