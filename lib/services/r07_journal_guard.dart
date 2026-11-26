/// Cross-isolate/process serialization for private journal mutations.
/// Each destination uses its own SQLite lock database, so independent downloads
/// never hold a global database transaction while awaiting network input.
library;

import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:sqflite/sqflite.dart';

String r07JournalFingerprint(String value) =>
    sha256.convert(utf8.encode(value)).toString();

Future<T> withR07JournalGuard<T>(Directory journal, String identity,
    Future<T> Function() operation) async {
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
  for (final suffix in ['', '-journal', '-wal', '-shm']) {
    final entry = await FileSystemEntity.type('$path$suffix', followLinks: false);
    if (entry != FileSystemEntityType.notFound && entry != FileSystemEntityType.file) {
      throw const FileSystemException('Unsafe operation lock file');
    }
  }
  // Do not wait indefinitely for a live owner. SQLite's transaction lock is
  // released by the OS on process death; no guessed stale lock deletion.
  final database = await openDatabase(path, singleInstance: false, version: 1,
    onConfigure: (db) async { await db.rawQuery('PRAGMA busy_timeout=1000'); },
    onCreate: (db, _) async {
      await db.execute('CREATE TABLE ownership (id INTEGER PRIMARY KEY)');
      await db.insert('ownership', {'id': 1});
    });
  try {
    return await database.transaction((txn) async {
      final rows = await txn.query('ownership', where: 'id = ?', whereArgs: [1]);
      if (rows.length != 1) throw const FormatException('Operation lock identity missing');
      // An exclusive transaction is held until the asynchronous operation
      // finishes, including its atomic journal write. A second isolate must
      // acquire the same lock rather than relying on an isolate-local map.
      return await operation();
    }, exclusive: true);
  } finally {
    await database.close();
  }
}
