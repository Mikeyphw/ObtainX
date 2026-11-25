import 'package:sqflite/sqflite.dart';

bool r11InQuietHours(DateTime local, int start, int end) {
  if (start == end) return false;
  final minute = local.hour * 60 + local.minute;
  return start < end ? minute >= start && minute < end : minute >= start || minute < end;
}

bool r11RateLimited(int now, int? previous, int minutes) =>
    minutes > 0 && previous != null && now - previous < minutes * 60000;

/// SQLite claim, not an isolate-local preference read/modify/write. An
/// unavailable policy database must postpone automatic work, never bypass it.
Future<bool> r11ClaimAutomaticRun(int minutes, DateTime now, {String? databasePath}) async {
  if (minutes <= 0) return true;
  final path = databasePath ?? '${await getDatabasesPath()}/r11_schedule.db';
  final database = await openDatabase(path, singleInstance: false, version: 1,
    onCreate: (db, _) => db.execute('CREATE TABLE schedule (id INTEGER PRIMARY KEY, started INTEGER NOT NULL)'));
  try {
    return await database.transaction((txn) async {
      final rows = await txn.query('schedule', where: 'id = ?', whereArgs: [1]);
      final previous = rows.isEmpty ? null : rows.single['started'] as int;
      final timestamp = now.millisecondsSinceEpoch;
      if (r11RateLimited(timestamp, previous, minutes)) return false;
      await txn.insert('schedule', {'id': 1, 'started': timestamp},
        conflictAlgorithm: ConflictAlgorithm.replace);
      return true;
    });
  } finally {
    await database.close();
  }
}
