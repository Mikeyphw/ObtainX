/// Durable operation intents and stage observations. Installer outcomes remain
/// authoritative only in the linked R05 journal; this timeline never invents
/// Android approvals or confirmed installation evidence.
library;

import 'dart:io';
import 'dart:math';

import 'package:obtainium/services/r07_journal_guard.dart';
import 'package:obtainium/services/r07_process_owner.dart';
import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart';

class R07OperationIntent {
  const R07OperationIntent({required this.kind, required this.listingKey,
    required this.packageId, required this.channel, required this.release,
    this.parentId});
  final String kind, listingKey, packageId, channel, release;
  final String? parentId;

  bool matches(R07OperationIntent other) => kind == other.kind &&
      listingKey == other.listingKey && packageId == other.packageId &&
      channel == other.channel && release == other.release && parentId == other.parentId;

  void validate() {
    final hash = RegExp(r'^[a-f0-9]{64}$');
    if (!const {'check', 'download', 'install'}.contains(kind) ||
        listingKey.isEmpty || listingKey.length > 1000 || packageId.isEmpty ||
        packageId.length > 1000 || RegExp(r'[\x00-\x1f/\\]').hasMatch(listingKey) ||
        RegExp(r'[\x00-\x1f/\\]').hasMatch(packageId) ||
        !hash.hasMatch(channel) || !hash.hasMatch(release) ||
        (parentId != null && !RegExp(r'^[A-Za-z0-9_-]{16,90}$').hasMatch(parentId!))) {
      throw const FormatException('Invalid operation identity');
    }
  }
}

class R07TimelineEntry {
  const R07TimelineEntry({required this.id, required this.batchId,
    required this.intent, required this.stage, required this.revision,
    required this.updatedUtc, required this.finished,
    this.reason, this.transferId, this.attemptId, this.resolvedListingKey, this.resolvedPackageId, this.processOwner});
  final String id, batchId, stage;
  final R07OperationIntent intent;
  final int revision;
  final DateTime updatedUtc;
  final bool finished;
  final String? reason, transferId, attemptId, resolvedListingKey, resolvedPackageId, processOwner;
  factory R07TimelineEntry.fromRow(Map<String, Object?> row) {
    final intent = R07OperationIntent(kind: row['kind'] as String,
      listingKey: row['listingKey'] as String, packageId: row['packageId'] as String,
      channel: row['channel'] as String, release: row['release'] as String,
      parentId: row['parentId'] as String?);
    intent.validate();
    final id = row['id'] as String, batchId = row['batchId'] as String;
    final stage = row['stage'] as String, revision = row['revision'] as int;
    final owner = row['processOwner'] as String?;
    final identity = RegExp(r'^r07_[a-f0-9]{32}$');
    if (!identity.hasMatch(id) || !identity.hasMatch(batchId) || revision < 0 || revision > 64 ||
        !R07OperationTimeline._stages.contains(stage) ||
        row['finished'] != (R07OperationTimeline._terminal.contains(stage) ? 1 : 0) ||
        (row['reason'] != null && !R07OperationTimeline._reasons.contains(row['reason'])) ||
        ((row['resolvedListingKey'] == null) != (row['resolvedPackageId'] == null))) {
      throw const FormatException('Invalid operation timeline row');
    }
    if (owner != null) { R07ProcessOwner.decode(owner); }
    return R07TimelineEntry(id: row['id'] as String, batchId: row['batchId'] as String,
      intent: intent, stage: row['stage'] as String, revision: row['revision'] as int,
      updatedUtc: DateTime.fromMicrosecondsSinceEpoch(row['updated'] as int, isUtc: true),
      finished: row['finished'] == 1, reason: row['reason'] as String?,
      transferId: row['transferId'] as String?, attemptId: row['attemptId'] as String?,
      resolvedListingKey: row['resolvedListingKey'] as String?, resolvedPackageId: row['resolvedPackageId'] as String?,
      processOwner: row['processOwner'] as String?);
  }
}

class R07OperationTimeline {
  R07OperationTimeline({this.testingRoot});
  final Directory? testingRoot;
  static final instance = R07OperationTimeline();
  Future<Directory> _root() async => testingRoot ?? await getApplicationSupportDirectory();
  static String _id() {
    final random = Random.secure();
    return 'r07_${List.generate(16, (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0')).join()}';
  }
  static const _terminal = {'checked', 'downloadReady', 'failed', 'cancelled', 'declined', 'installLinked'};
  static const _stages = {'queued', 'checking', 'downloading', 'downloaded', 'verifying',
    'extracting', 'downloadReady', 'ready', 'scanning', 'preparingInstall', 'installLinked',
    'checked', 'unknown', 'failed', 'cancelled', 'declined'};
  static const _reasons = {'network', 'cancelled', 'interrupted', 'source', 'ownership', 'operation', 'verificationDeclined'};

  Future<T> _use<T>(Future<T> Function(Database) action) async {
    final root = await _root();
    await root.create(recursive: true);
    final path = '${root.path}/r07-operation-timeline.sqlite';
    for (final suffix in ['', '-wal', '-shm', '-journal']) {
      final type = await FileSystemEntity.type('$path$suffix', followLinks: false);
      if (type != FileSystemEntityType.notFound && type != FileSystemEntityType.file) {
        throw const FileSystemException('Unsafe operation timeline');
      }
    }
    final db = await openDatabase(path, version: 1, singleInstance: false,
      onConfigure: (db) async { await db.rawQuery('PRAGMA busy_timeout=1000'); },
      onCreate: (db, _) async {
        await db.execute('CREATE TABLE operations (id TEXT PRIMARY KEY, batchId TEXT NOT NULL, '
          'kind TEXT NOT NULL, listingKey TEXT NOT NULL, packageId TEXT NOT NULL, channel TEXT NOT NULL, '
          'release TEXT NOT NULL, parentId TEXT, stage TEXT NOT NULL, revision INTEGER NOT NULL, '
          'updated INTEGER NOT NULL, finished INTEGER NOT NULL, reason TEXT, transferId TEXT, attemptId TEXT, '
          'resolvedListingKey TEXT, resolvedPackageId TEXT, processOwner TEXT)');
        await db.execute('CREATE INDEX operations_history ON operations(finished, updated DESC, id)');
        await db.execute('CREATE INDEX operations_batch ON operations(batchId, kind, finished)');
        await db.execute('CREATE TABLE events (operationId TEXT NOT NULL, revision INTEGER NOT NULL, '
          'stage TEXT NOT NULL, updated INTEGER NOT NULL, reason TEXT, PRIMARY KEY(operationId, revision))');
      });
    try { return await action(db); } finally { await db.close(); }
  }

  Future<List<R07TimelineEntry>> enqueue(List<R07OperationIntent> intents) async {
    if (intents.isEmpty) return [];
    for (final intent in intents) { intent.validate(); }
    final batch = _id();
    return _use((db) => db.transaction((txn) async {
      final result = <R07TimelineEntry>[];
      for (final intent in intents) {
        final id = _id();
        final row = <String, Object?>{'id': id, 'batchId': batch, 'kind': intent.kind,
          'listingKey': intent.listingKey, 'packageId': intent.packageId, 'channel': intent.channel,
          'release': intent.release, 'parentId': intent.parentId, 'stage': 'queued', 'revision': 0,
          'updated': DateTime.now().toUtc().microsecondsSinceEpoch, 'finished': 0};
        await txn.insert('operations', row);
        await txn.insert('events', {'operationId': id, 'revision': 0, 'stage': 'queued', 'updated': row['updated']});
        result.add(R07TimelineEntry.fromRow(row));
      }
      return result;
    }));
  }

  Future<R07TimelineEntry> read(String id) => _use((db) async {
    final rows = await db.query('operations', where: 'id = ?', whereArgs: [id]);
    if (rows.length != 1) throw StateError('Operation no longer exists');
    return R07TimelineEntry.fromRow(rows.single);
  });

  static bool _allowedTransition(String before, String after) {
    if (before == 'queued') {
      return const {'checking', 'downloading', 'preparingInstall', 'cancelled'}.contains(after);
    }
    if (const {'failed', 'cancelled', 'unknown'}.contains(after)) return !_terminal.contains(before);
    return switch (before) {
      'checking' => after == 'checked',
      'downloading' => after == 'downloaded',
      'downloaded' => after == 'verifying',
      'verifying' => const {'verifying', 'extracting', 'ready', 'downloadReady'}.contains(after),
      'extracting' => const {'extracting', 'ready', 'downloadReady'}.contains(after),
      'ready' => const {'scanning', 'preparingInstall', 'declined', 'installLinked'}.contains(after),
      'scanning' => const {'preparingInstall', 'declined', 'installLinked'}.contains(after),
      'preparingInstall' => const {'scanning', 'declined', 'installLinked'}.contains(after),
      _ => false,
    };
  }

  Future<R07TimelineEntry> advance(String id, String stage, {String? reason,
      String? transferId, String? attemptId, String? expectedStage,
      String? resolvedListingKey, String? resolvedPackageId}) {
    if ((resolvedListingKey == null) != (resolvedPackageId == null) ||
        !_stages.contains(stage) || (reason != null && !_reasons.contains(reason)) ||
        (transferId != null && !RegExp(r'^[a-f0-9]{64}$').hasMatch(transferId)) ||
        (attemptId != null && !RegExp(r'^[A-Za-z0-9_-]{16,90}$').hasMatch(attemptId))) {
      throw const FormatException('Untrusted operation observation');
    }
    return _use((db) => db.transaction((txn) async {
      final rows = await txn.query('operations', where: 'id = ?', whereArgs: [id]);
      if (rows.length != 1) throw StateError('Operation no longer exists');
      final previous = R07TimelineEntry.fromRow(rows.single);
      if ((expectedStage != null && previous.stage != expectedStage) || previous.finished ||
          (previous.transferId != null && transferId != null && previous.transferId != transferId) ||
          (previous.attemptId != null && attemptId != null && previous.attemptId != attemptId) ||
          previous.revision >= 64 || !_allowedTransition(previous.stage, stage) ||
          (resolvedListingKey != null && (previous.resolvedListingKey != null ||
              previous.transferId == null || !const {'verifying', 'extracting'}.contains(previous.stage))) ||
          (stage == 'installLinked' && attemptId == null)) {
        throw StateError('Operation changed or has already finished');
      }
      final owner = previous.stage == 'queued' && const {'checking', 'downloading', 'preparingInstall'}.contains(stage)
          ? (await R07ProcessOwner.capture()).encode() : previous.processOwner;
      final update = <String, Object?>{'processOwner': owner, 'stage': stage, 'revision': previous.revision + 1,
        'updated': DateTime.now().toUtc().microsecondsSinceEpoch, 'reason': reason,
        'finished': _terminal.contains(stage) ? 1 : 0,
        'transferId': transferId ?? previous.transferId, 'attemptId': attemptId ?? previous.attemptId,
        'resolvedListingKey': resolvedListingKey ?? previous.resolvedListingKey,
        'resolvedPackageId': resolvedPackageId ?? previous.resolvedPackageId};
      if (await txn.update('operations', update, where: 'id = ? AND revision = ?',
          whereArgs: [id, previous.revision]) != 1) throw StateError('Operation revision conflict');
      await txn.insert('events', {'operationId': id, 'revision': update['revision'], 'stage': stage,
        'updated': update['updated'], 'reason': reason});
      return R07TimelineEntry.fromRow({...rows.single, ...update});
    }));
  }

  /// Serialize actual owners, not just progress rows. Failure before acquiring
  /// the guard must not overwrite another owner's running receipt.
  Future<T> run<T>(R07TimelineEntry entry, R07OperationIntent expected,
      String startStage, Future<T> Function() action,
      {required String successStage, String Function(Object)? failureReason}) async {
    final root = await _root();
    return withR07JournalGuard(Directory('${root.path}/r07-operation-timeline'),
      'listing:${expected.kind == 'check' ? 'check' : 'transfer'}:${expected.listingKey}', () async {
      final current = await read(entry.id);
      if (!current.intent.matches(expected) || current.stage != 'queued') {
        throw StateError('Queued operation identity changed');
      }
      await advance(entry.id, startStage, expectedStage: 'queued');
      try {
        final result = await action();
        await advance(entry.id, successStage);
        return result;
      } catch (error) {
        // Retain the primary operation error. A failed journal update leaves
        // an unresolved observation, never a fabricated terminal result.
        try {
          final reason = failureReason?.call(error) ?? 'operation';
          await advance(entry.id, reason == 'cancelled' ? 'cancelled' : 'failed', reason: reason);
        } catch (_) { /* primary failure remains authoritative */ }
        rethrow;
      }
    });
  }

  Future<R07TimelineEntry> beginPreparation(R07OperationIntent intent) async {
    if (intent.kind != 'install') { throw ArgumentError.value(intent.kind); }
    final entry = (await enqueue([intent])).single;
    return advance(entry.id, 'preparingInstall', expectedStage: 'queued');
  }

  Future<void> settlePreparation(String? id, String stage) async {
    if (id == null) { return; }
    try {
      final current = await read(id);
      if (!current.finished && current.intent.kind == 'install' && current.stage != 'unknown') {
        await advance(id, stage, expectedStage: current.stage,
          reason: stage == 'cancelled' ? 'cancelled' : stage == 'unknown' ? 'ownership' : 'operation');
      }
    } catch (_) { /* preserve primary result; an unresolved receipt stays visible */ }
  }

  Future<void> observePreparation(String? id, String stage) async {
    if (id == null) return;
    final current = await read(id);
    if (current.finished) return; // Never replace the linked R05 outcome.
    if (current.intent.kind != 'install') return;
    if (current.stage == stage) return;
    await advance(id, stage, expectedStage: current.stage,
      reason: stage == 'declined' ? 'verificationDeclined' : stage == 'cancelled' ? 'cancelled' : null);
  }

  Future<void> resolveDownloadedIdentity(String id, String listingKey, String packageId) async {
    final current = await read(id);
    final resolved = R07OperationIntent(kind: current.intent.kind, listingKey: listingKey,
      packageId: packageId, channel: current.intent.channel, release: current.intent.release,
      parentId: current.intent.parentId);
    resolved.validate();
    await advance(id, current.stage, expectedStage: current.stage,
      resolvedListingKey: listingKey, resolvedPackageId: packageId);
  }

  Future<R07TimelineEntry> validateInstallBinding(String id, {required String listingKey,
      required String packageId, required String channel, required String release}) async {
    final current = await read(id);
    if (current.intent.channel != channel || current.intent.release != release ||
        (current.resolvedListingKey ?? current.intent.listingKey) != listingKey ||
        (current.resolvedPackageId ?? current.intent.packageId) != packageId ||
        current.intent.kind != 'install' ||
        !const {'ready', 'scanning', 'preparingInstall'}.contains(current.stage)) {
      throw StateError('Timeline listing/release does not match install receipt');
    }
    return current;
  }

  Future<void> linkAttempt(String id, String attemptId, {required String listingKey,
      required String packageId, required String channel, required String release}) async {
    final current = await validateInstallBinding(id, listingKey: listingKey, packageId: packageId,
      channel: channel, release: release);
    await advance(id, 'installLinked', attemptId: attemptId, expectedStage: current.stage);
  }

  Future<void> cancelQueued(String id) async {
    await advance(id, 'cancelled', expectedStage: 'queued', reason: 'cancelled');
  }

  /// Active/recoverable records are never excluded by history size. Terminal
  /// history has a stable, indexed page boundary. No state change on reads.
  Future<List<R07TimelineEntry>> readActivity({int? historyLimit}) => _use((db) => db.transaction((txn) async {
    final active = await txn.query('operations', where: 'finished = 0', orderBy: 'updated DESC, id');
    final history = historyLimit == 0 ? <Map<String, Object?>>[] : await txn.query('operations',
      where: 'finished = 1', orderBy: 'updated DESC, id', limit: historyLimit);
    return [...active, ...history].map(R07TimelineEntry.fromRow).toList(growable: false);
  }));

  Future<({List<R07TimelineEntry> rows, int unreadableCount,
      Set<String> channels, Map<String, ({int completed, int total})> batches})> readForActivity({
      int? historyLimit, String? packageId, String? listingKey, String? operationId,
      String channel = 'all', String filter = 'all'}) => _use((db) => db.transaction((txn) async {
    final scope = <String>[], args = <Object?>[];
    if (packageId != null) { scope.add('packageId = ?'); args.add(packageId); }
    if (listingKey != null) { scope.add('listingKey = ?'); args.add(listingKey); }
    if (operationId != null) { scope.add('id = ?'); args.add(operationId); }
    final channelRows = await txn.query('operations', distinct: true, columns: ['channel'],
      where: scope.isEmpty ? null : scope.join(' AND '), whereArgs: scope.isEmpty ? null : args);
    final channels = channelRows.map((row) => row['channel']).whereType<String>()
        .where((value) => RegExp(r'^[a-f0-9]{64}$').hasMatch(value)).toSet();
    if (channel != 'all') { scope.add('channel = ?'); args.add(channel); }
    final activeConditions = [...scope, 'finished = 0', if (filter == 'review') "stage IN ('queued','unknown')"];
    final historyConditions = [...scope, 'finished = 1', if (filter == 'review') "stage = 'failed'"];
    final active = filter == 'done' ? <Map<String, Object?>>[] : await txn.query('operations',
      where: activeConditions.join(' AND '), whereArgs: args, orderBy: 'updated DESC, id');
    final history = historyLimit == 0 ? <Map<String, Object?>>[] : await txn.query('operations',
      where: historyConditions.join(' AND '), whereArgs: args, orderBy: 'updated DESC, id', limit: historyLimit);
    final rows = <R07TimelineEntry>[];
    var unreadableCount = 0;
    for (final raw in [...active, ...history]) {
      try { rows.add(R07TimelineEntry.fromRow(raw)); }
      on FormatException { unreadableCount++; }
      on TypeError { unreadableCount++; }
    }
    final batches = <String, ({int completed, int total})>{};
    final ids = rows.where((row) => row.intent.kind == 'check').map((row) => row.batchId).toSet().toList();
    for (var offset = 0; offset < ids.length; offset += 100) {
      final group = ids.skip(offset).take(100).toList();
      final results = await txn.rawQuery('SELECT batchId, COUNT(*) AS total, COALESCE(SUM(finished), 0) AS completed '
        'FROM operations WHERE batchId IN (${List.filled(group.length, '?').join(',')}) GROUP BY batchId', group);
      for (final result in results) {
        batches[result['batchId'] as String] = (completed: result['completed'] as int, total: result['total'] as int);
      }
    }
    return (rows: rows, unreadableCount: unreadableCount, channels: channels, batches: batches);
  }));

  Future<List<Map<String, Object?>>> events(String id) => _use((db) =>
    db.query('events', where: 'operationId = ?', whereArgs: [id], orderBy: 'revision'));

  Future<({int completed, int total})> counts(String batchId) => _use((db) async {
    final rows = await db.rawQuery('SELECT COUNT(*) AS total, COALESCE(SUM(finished), 0) AS completed '
      'FROM operations WHERE batchId = ?', [batchId]);
    return (completed: rows.single['completed'] as int, total: rows.single['total'] as int);
  });

  /// If the exact listing guard is obtainable, no transfer/check owner holds
  /// it. Reconcile only the captured revision, never a newer operation. An
  /// interrupted Android attempt is still reviewed through R05/native state.
  Future<void> recoverInterrupted() async {
    final root = await _root();
    for (final entry in await readActivity(historyLimit: 0)) {
      final transferStage = const {'checking', 'downloading', 'downloaded', 'verifying', 'extracting'}.contains(entry.stage);
      final preparationStage = const {'ready', 'scanning', 'preparingInstall'}.contains(entry.stage);
      if (!transferStage && !preparationStage) { continue; }
      if (preparationStage && (entry.processOwner == null ||
          await R07ProcessOwner.decode(entry.processOwner!).inspect() != R07ProcessState.dead)) {
        continue;
      }
      try {
        await withR07JournalGuard(Directory('${root.path}/r07-operation-timeline'),
          'listing:${entry.intent.kind == 'check' ? 'check' : 'transfer'}:${entry.intent.listingKey}', () async {
          final current = await read(entry.id);
          if (current.revision == entry.revision && current.stage == entry.stage) {
            await advance(entry.id, 'unknown', expectedStage: entry.stage, reason: 'interrupted');
          }
        });
      } on DatabaseException {
        // Contended or unreadable ownership is not evidence of interruption.
      }
    }
  }
}
