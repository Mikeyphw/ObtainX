import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/services/r07_operation_timeline.dart';
import 'package:obtainium/services/r07_journal_guard.dart';
import 'package:obtainium/services/r07_process_owner.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  late Directory root;
  late R07OperationTimeline timeline;
  const channel = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
  const release = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
  const transfer = 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc';
  const attempt = 'r05_123456789abcdef0_123456789abcdef0';
  const intent = R07OperationIntent(kind: 'install', listingKey: 'source:one',
    packageId: 'com.example', channel: channel, release: release);
  setUp(() async {
    root = await Directory.systemTemp.createTemp('ox-gap03-timeline-');
    timeline = R07OperationTimeline(testingRoot: root);
  });
  tearDown(() async { await root.delete(recursive: true); });

  test('parallel first-open and bulk workers retain each exact timeline revision', () async {
    final intents = List.generate(12, (i) => R07OperationIntent(kind: 'check',
      listingKey: 'source:$i', packageId: 'com.example', channel: channel, release: release));
    final entries = await Future.wait(intents.map((value) async =>
      (await R07OperationTimeline(testingRoot: root).enqueue([value])).single));
    final entered = Completer<void>();
    var running = 0;
    await Future.wait(entries.map((entry) => R07OperationTimeline(testingRoot: root).run(
      entry, entry.intent, 'checking', () async {
        running++;
        if (running == 2) { entered.complete(); }
        await entered.future.timeout(const Duration(seconds: 5));
      }, successStage: 'checked')));
    expect(running, 12);
    for (final entry in entries) {
      final row = await timeline.read(entry.id);
      expect(row.stage, 'checked');
      expect(row.revision, 2);
      expect((await timeline.events(entry.id)).map((event) => event['revision']), [0, 1, 2]);
    }
  });

  Future<Database> openProbe(String path) => openDatabase(path, version: 1,
    singleInstance: false,
    onConfigure: (db) async { await db.rawQuery('PRAGMA busy_timeout=0'); },
    onCreate: (db, _) => db.execute('CREATE TABLE probe (id INTEGER PRIMARY KEY)'));

  test('independent SQLite writer retries acquisition without replaying callback', () async {
    final path = '${root.path}/contended.sqlite';
    final owner = await openProbe(path);
    final acquired = Completer<void>(), releaseOwner = Completer<void>();
    final holder = owner.transaction((txn) async {
      await txn.insert('probe', {'id': 1});
      acquired.complete();
      await releaseOwner.future;
    });
    await acquired.future;
    var opens = 0, callbacks = 0;
    final retried = Completer<void>();
    final contender = withR07SqliteTransaction(path, () async {
      if (++opens == 2) { retried.complete(); }
      return openProbe(path);
    }, (txn) async {
      callbacks++;
      await txn.insert('probe', {'id': 2});
    }, exclusive: true);
    try {
      await retried.future.timeout(const Duration(seconds: 3));
      expect(callbacks, 0);
    } finally {
      releaseOwner.complete();
      await holder;
      await owner.close();
      await contender;
    }
    expect(opens, greaterThanOrEqualTo(2));
    expect(callbacks, 1);
    final reopened = await openProbe(path);
    try {
      expect((await reopened.query('probe', orderBy: 'id')).map((row) => row['id']), [1, 2]);
    } finally { await reopened.close(); }
  });

  test('independent writer timeout never enters or cancels its owner', () async {
    final path = '${root.path}/deadline.sqlite';
    final owner = await openProbe(path);
    final acquired = Completer<void>(), releaseOwner = Completer<void>();
    final holder = owner.transaction((txn) async {
      await txn.insert('probe', {'id': 1});
      acquired.complete();
      await releaseOwner.future;
      await txn.insert('probe', {'id': 2});
    }, exclusive: true);
    await acquired.future;
    var callbacks = 0;
    try {
      await expectLater(withR07SqliteTransaction(path, () => openProbe(path), (txn) async {
        callbacks++;
      }, exclusive: true, acquisitionTimeout: const Duration(milliseconds: 180)),
        throwsA(isA<R07JournalBusy>()));
      expect(callbacks, 0);
    } finally {
      releaseOwner.complete();
      await holder;
      await owner.close();
    }
    final rows = await withR07SqliteTransaction(path, () => openProbe(path),
      (txn) => txn.query('probe', orderBy: 'id'));
    expect(rows.map((row) => row['id']), [1, 2]);
  });

  test('callback errors roll back and never replay, including SQLite busy', () async {
    final path = '${root.path}/rollback.sqlite';
    var callbacks = 0;
    for (final busy in [false, true]) {
      await expectLater(withR07SqliteTransaction(path, () => openProbe(path), (txn) async {
        callbacks++;
        await txn.insert('probe', {'id': 1});
        if (busy) { throw _CallbackBusy(); }
        await txn.insert('probe', {'id': 1}); // actual constraint violation
      }), throwsA(isA<DatabaseException>()));
      final rows = await withR07SqliteTransaction(path, () => openProbe(path),
        (txn) => txn.query('probe'));
      expect(rows, isEmpty);
    }
    expect(callbacks, 2);
  });

  test('local per-identity guard times out without affecting a different identity', () async {
    final directory = Directory('${root.path}/shared');
    final acquired = Completer<void>(), releaseOwner = Completer<void>();
    final owner = withR07JournalGuard(directory, 'one', () async {
      acquired.complete();
      await releaseOwner.future;
    });
    await acquired.future;
    var callbacks = 0;
    try {
      await expectLater(withR07JournalGuard(directory, 'one', () async {
        callbacks++;
      }, acquisitionTimeout: const Duration(milliseconds: 80)), throwsA(isA<R07JournalBusy>()));
      await withR07JournalGuard(directory, 'two', () async { callbacks++; });
      expect(callbacks, 1);
    } finally {
      releaseOwner.complete();
      await owner;
    }
    await withR07JournalGuard(directory, 'one', () async { callbacks++; });
    expect(callbacks, 2);
  });

  test('durable queue and actual stage events survive reopening', () async {
    final entry = (await timeline.enqueue([intent])).single;
    final reopened = R07OperationTimeline(testingRoot: root);
    expect((await reopened.read(entry.id)).stage, 'queued');
    await reopened.run(entry, intent, 'downloading', () async {
      await reopened.advance(entry.id, 'downloaded', transferId: transfer);
      await reopened.advance(entry.id, 'verifying');
      await reopened.advance(entry.id, 'extracting');
    }, successStage: 'ready');
    await reopened.observePreparation(entry.id, 'scanning');
    await reopened.observePreparation(entry.id, 'preparingInstall');
    await reopened.linkAttempt(entry.id, attempt, listingKey: intent.listingKey,
      packageId: intent.packageId, channel: channel, release: release);
    final result = await timeline.read(entry.id);
    expect(result.stage, 'installLinked'); // not a claimed install outcome
    expect(result.attemptId, attempt);
    expect(result.transferId, transfer);
    expect((await timeline.events(entry.id)).map((e) => e['stage']),
      ['queued', 'downloading', 'downloaded', 'verifying', 'extracting', 'ready',
       'scanning', 'preparingInstall', 'installLinked']);
    expect(() => timeline.advance(entry.id, 'confirmed'), throwsFormatException);
  });

  test('cancelled queued intent cannot execute, wrong release cannot run', () async {
    final entry = (await timeline.enqueue([intent])).single;
    const wrong = R07OperationIntent(kind: 'install', listingKey: 'source:one',
      packageId: 'com.example', channel: release, release: release);
    var dispatched = false;
    await expectLater(timeline.run(entry, wrong, 'downloading', () async {
      dispatched = true;
    }, successStage: 'ready'), throwsStateError);
    expect(dispatched, isFalse);
    await timeline.cancelQueued(entry.id);
    await expectLater(timeline.run(entry, intent, 'downloading', () async {
      dispatched = true;
    }, successStage: 'ready'), throwsStateError);
    expect(dispatched, isFalse);
    expect((await timeline.read(entry.id)).stage, 'cancelled');
  });

  test('interrupted transfer is unknown; live owner remains untouched', () async {
    final rows = await timeline.enqueue([intent, intent]);
    await timeline.advance(rows.first.id, 'downloading');
    await timeline.recoverInterrupted();
    expect((await timeline.read(rows.first.id)).stage, 'unknown');
    final entered = Completer<void>(), releaseOwner = Completer<void>();
    final running = timeline.run(rows.last, intent, 'downloading', () async {
      entered.complete();
      await releaseOwner.future;
      await timeline.advance(rows.last.id, 'downloaded', transferId: transfer);
      await timeline.advance(rows.last.id, 'verifying');
    }, successStage: 'ready');
    try {
      await entered.future;
      await timeline.recoverInterrupted();
      expect((await timeline.read(rows.last.id)).stage, 'downloading');
    } finally {
      releaseOwner.complete();
      await running;
    }
  });

  test('indexed history boundary preserves all unresolved rows above 512', () async {
    final rows = await timeline.enqueue(List.filled(521, intent));
    for (final row in rows.take(520)) {
      await timeline.cancelQueued(row.id);
    }
    final reopened = R07OperationTimeline(testingRoot: root);
    final page = await reopened.readActivity(historyLimit: 10);
    expect(page.length, 11);
    expect(page.first.id, rows.last.id);
    expect(page.where((row) => row.finished).length, 10);
    expect(await reopened.counts(rows.last.batchId), (completed: 520, total: 521));
  });

  test('offline operation records failure, not checked success', () async {
    const check = R07OperationIntent(kind: 'check', listingKey: 'source:one',
      packageId: 'com.example', channel: channel, release: release);
    final entry = (await timeline.enqueue([check])).single;
    await expectLater(timeline.run(entry, check, 'checking', () async {
      throw const SocketException('offline');
    }, successStage: 'checked', failureReason: (_) => 'network'), throwsA(isA<SocketException>()));
    final failed = await timeline.read(entry.id);
    expect(failed.stage, 'failed');
    expect(failed.reason, 'network');
    expect((await timeline.events(entry.id)).map((e) => e['stage']), ['queued', 'checking', 'failed']);
  });

  test('direct preparation has exact identity and cannot link a download-only receipt', () async {
    final local = await timeline.beginPreparation(intent);
    await timeline.observePreparation(local.id, 'scanning');
    await timeline.observePreparation(local.id, 'preparingInstall');
    await expectLater(timeline.linkAttempt(local.id, attempt, listingKey: intent.listingKey,
      packageId: intent.packageId, channel: channel, release: transfer), throwsStateError);
    await timeline.linkAttempt(local.id, attempt, listingKey: intent.listingKey,
      packageId: intent.packageId, channel: channel, release: release);
    expect((await timeline.read(local.id)).attemptId, attempt);
    const download = R07OperationIntent(kind: 'download', listingKey: 'source:one',
      packageId: 'com.example', channel: channel, release: release);
    final entry = (await timeline.enqueue([download])).single;
    await timeline.run(entry, download, 'downloading', () async {
      await timeline.advance(entry.id, 'downloaded', transferId: transfer);
      await timeline.advance(entry.id, 'verifying');
    }, successStage: 'downloadReady');
    await expectLater(timeline.linkAttempt(entry.id, attempt, listingKey: intent.listingKey,
      packageId: intent.packageId, channel: channel, release: release), throwsStateError);
  });

  test('captured child process death establishes stale ownership on Linux', () async {
    final child = await Process.start('/bin/sh', ['-c', 'exec sleep 60']);
    try {
      final owner = await R07ProcessOwner.observe(child.pid);
      expect(await owner.inspect(), R07ProcessState.live);
      expect(child.kill(), isTrue);
      await child.exitCode;
      expect(await owner.inspect(), R07ProcessState.dead);
    } finally {
      child.kill();
      await child.exitCode;
    }
  });

  test('process identity roundtrip refuses forged owner encoding', () async {
    final owner = await R07ProcessOwner.capture();
    expect(R07ProcessOwner.decode(owner.encode()).processId, pid);
    expect(await owner.inspect(), isNot(R07ProcessState.dead));
    expect(() => R07ProcessOwner.decode('invalid'), throwsFormatException);
  });
}

// Inject a classified database error after callback entry; the other tests
// independently induce actual contention on separate SQLite connections.
class _CallbackBusy extends DatabaseException {
  _CallbackBusy() : super('database is locked');
  @override
  int getResultCode() => 5;
  @override
  Object? get result => null;
}
