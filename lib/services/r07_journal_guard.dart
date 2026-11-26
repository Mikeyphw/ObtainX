/// Cross-isolate/process serialization for private journal mutations.
/// Each destination uses its own SQLite lock database, so independent downloads
/// never hold a global database transaction while awaiting network input.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:sqflite/sqflite.dart';

String r07JournalFingerprint(String value) =>
    sha256.convert(utf8.encode(value)).toString();

/// Acquisition failed within the bounded budget. This is never emitted for
/// a database error from an already-started operation.
class R07JournalBusy implements Exception {
  const R07JournalBusy();
  @override
  String toString() => 'Journal ownership is busy; try again';
}

// In-process contenders sharing a canonical private database path yield to the
// current owner. SQLite remains the cross-isolate/process authority. Do not
// let a blocking SQLite busy handler starve the owner's asynchronous work.
final _leases = <String, Completer<void>>{};

bool _isContention(DatabaseException error) {
  final code = error.getResultCode();
  return code != null && const {5, 6}.contains(code & 0xff);
}

Future<T> withR07SqliteTransaction<T>(String path,
    Future<Database> Function() open, Future<T> Function(Transaction) operation,
    {bool exclusive = false,
    Duration acquisitionTimeout = const Duration(seconds: 5)}) async {
  final key = File(path).absolute.path;
  final clock = Stopwatch()..start();
  while (_leases.containsKey(key)) {
    final remaining = acquisitionTimeout - clock.elapsed;
    if (remaining <= Duration.zero) { throw const R07JournalBusy(); }
    try {
      await _leases[key]!.future.timeout(remaining);
    } on TimeoutException {
      throw const R07JournalBusy();
    }
  }
  if (clock.elapsed >= acquisitionTimeout) { throw const R07JournalBusy(); }
  final lease = Completer<void>();
  _leases[key] = lease;
  try {
    while (true) {
      var entered = false;
      var cleanupSucceeded = true;
      try {
        final database = await open();
        late T result;
        try {
          result = await database.transaction((txn) async {
            if (clock.elapsed >= acquisitionTimeout) { throw const R07JournalBusy(); }
            entered = true;
            return await operation(txn);
          }, exclusive: exclusive);
        } catch (error, stack) {
          try {
            await database.close();
          } catch (_) {
            // Preserve the primary error and forbid retry if cleanup failed.
            cleanupSucceeded = false;
          }
          Error.throwWithStackTrace(error, stack);
        }
        await database.close();
        return result;
      } on DatabaseException catch (error) {
        // Opening/BEGIN can be retried. A callback, commit, rollback, or
        // close failure after entry has uncertain effects and MUST NOT replay.
        if (entered || !cleanupSucceeded || !_isContention(error)) { rethrow; }
        final remaining = acquisitionTimeout - clock.elapsed;
        if (remaining <= Duration.zero) { throw const R07JournalBusy(); }
        const pause = Duration(milliseconds: 40);
        await Future<void>.delayed(remaining < pause ? remaining : pause);
        if (clock.elapsed >= acquisitionTimeout) { throw const R07JournalBusy(); }
      }
    }
  } finally {
    _leases.remove(key);
    lease.complete();
  }
}

Future<T> withR07JournalGuard<T>(Directory journal, String identity,
    Future<T> Function() operation,
    {Duration acquisitionTimeout = const Duration(seconds: 5)}) async {
  final directory = Directory('${journal.absolute.path}.locks');
  final type = await FileSystemEntity.type(directory.path, followLinks: false);
  if (type != FileSystemEntityType.notFound && type != FileSystemEntityType.directory) {
    throw const FileSystemException('Unsafe operation lock directory');
  }
  await directory.create(recursive: true);
  if (await FileSystemEntity.type(directory.path, followLinks: false) !=
      FileSystemEntityType.directory) {
    throw const FileSystemException('Unsafe operation lock directory');
  }
  final path = '${directory.path}/${r07JournalFingerprint(identity)}.db';
  // Do not wait indefinitely for a live owner. SQLite's transaction lock is
  // released by the OS on process death; no guessed stale lock deletion.
  return withR07SqliteTransaction(path, () async {
    // Recheck the private path after waiting and on every acquisition retry.
    if (await FileSystemEntity.type(directory.path, followLinks: false) !=
        FileSystemEntityType.directory) {
      throw const FileSystemException('Unsafe operation lock directory');
    }
    for (final suffix in ['', '-journal', '-wal', '-shm']) {
      final entry = await FileSystemEntity.type('$path$suffix', followLinks: false);
      if (entry != FileSystemEntityType.notFound && entry != FileSystemEntityType.file) {
        throw const FileSystemException('Unsafe operation lock file');
      }
    }
    return openDatabase(path,
    singleInstance: false, version: 1,
    onConfigure: (db) async { await db.rawQuery('PRAGMA busy_timeout=0'); },
    onCreate: (db, _) async {
      await db.execute('CREATE TABLE ownership (id INTEGER PRIMARY KEY)');
      await db.insert('ownership', {'id': 1});
    });
  }, (txn) async {
      final rows = await txn.query('ownership', where: 'id = ?', whereArgs: [1]);
      if (rows.length != 1) { throw const FormatException('Operation lock identity missing'); }
      // Hold the exclusive OS-backed transaction throughout the actual
      // operation. The acquisition timeout never cancels a running owner.
      return await operation();
    }, exclusive: true, acquisitionTimeout: acquisitionTimeout);
}
