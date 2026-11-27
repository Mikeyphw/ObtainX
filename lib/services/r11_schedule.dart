import 'package:sqflite/sqflite.dart';
import 'package:obtainium/services/r07_journal_guard.dart';

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

/// Last observed automatic scheduling decision, not a claim of current OS
/// scheduling or a successful installation. Only fixed codes and UTC time
/// are retained; no package names, URLs, or exception text.
enum R11ScheduleReason {
  quietHours, notDue, noNetwork, disabled, networkRestriction,
  chargingRestriction, minimumInterval, policyUnavailable, policyChanged,
  allowed,
}

class R11ScheduleObservation {
  const R11ScheduleObservation(this.reason, this.observedUtc);
  final R11ScheduleReason reason;
  final DateTime observedUtc;
}

Future<T> _r11ObservationStore<T>(Future<T> Function(Transaction) action,
    {String? databasePath}) async {
  final path = databasePath ?? '${await getDatabasesPath()}/r11_schedule_observation.db';
  return withR07SqliteTransaction(path, () => openDatabase(path,
    singleInstance: false, version: 1,
    onConfigure: (db) async { await db.rawQuery('PRAGMA busy_timeout=0'); },
    onCreate: (db, _) => db.execute('CREATE TABLE observation '
      '(id INTEGER PRIMARY KEY, reason TEXT NOT NULL, observed INTEGER NOT NULL)')),
    action, exclusive: true);
}

Future<void> r11RecordScheduleObservation(R11ScheduleReason reason, DateTime now,
    {String? databasePath}) => _r11ObservationStore((txn) async {
  await txn.insert('observation', {'id': 1, 'reason': reason.name,
    'observed': now.toUtc().millisecondsSinceEpoch},
    conflictAlgorithm: ConflictAlgorithm.replace);
}, databasePath: databasePath);

Future<R11ScheduleObservation?> r11ReadScheduleObservation({String? databasePath}) =>
    _r11ObservationStore((txn) async {
      final rows = await txn.query('observation', where: 'id = ?', whereArgs: [1]);
      if (rows.isEmpty) { return null; }
      final row = rows.single;
      return R11ScheduleObservation(R11ScheduleReason.values.byName(row['reason'] as String),
        DateTime.fromMillisecondsSinceEpoch(row['observed'] as int, isUtc: true));
    }, databasePath: databasePath);
