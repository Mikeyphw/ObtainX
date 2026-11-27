/// Durable operation intents and stage observations. Installer outcomes remain
/// authoritative only in the linked R05 journal; this timeline never invents
/// Android approvals or confirmed installation evidence.
library;

import 'dart:convert';
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
    final unboundLocal = kind == 'localArchive' && listingKey == 'local-archive' &&
        packageId == 'unknown' && channel == 'unknown';
    if (!const {'check', 'download', 'install', 'localArchive'}.contains(kind) ||
        listingKey.isEmpty || listingKey.length > 1000 || packageId.isEmpty ||
        packageId.length > 1000 || RegExp(r'[\x00-\x1f/\\]').hasMatch(listingKey) ||
        RegExp(r'[\x00-\x1f/\\]').hasMatch(packageId) ||
        (!unboundLocal && !hash.hasMatch(channel)) || !hash.hasMatch(release) ||
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

class R07EventRetentionPreview {
  const R07EventRetentionPreview._(this.cutoff, this.listingKey, this.packageId,
    this.channel, this.entries);
  final DateTime cutoff;
  final String? listingKey, packageId, channel;
  final Map<String, ({int revision, int events, String fingerprint})> entries;
  int get removableEvents => entries.values.fold(0, (count, item) => count + item.events);
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
  static const _terminal = {'checked', 'downloadReady', 'failed', 'cancelled', 'declined', 'installLinked', 'paused'};
  static const _stages = {'queued', 'checking', 'downloading', 'downloaded', 'verifying',
    'extracting', 'downloadReady', 'ready', 'scanning', 'preparingInstall', 'installLinked',
    'checked', 'unknown', 'failed', 'cancelled', 'declined', 'paused', 'copying'};
  static const _reasons = {'network', 'cancelled', 'interrupted', 'source', 'ownership', 'operation', 'verificationDeclined', 'paused'};

  Future<T> _use<T>(Future<T> Function(Transaction) action) async {
    final root = await _root();
    await root.create(recursive: true);
    final path = '${root.path}/r07-operation-timeline.sqlite';
    return withR07SqliteTransaction(path, () async {
      if (await FileSystemEntity.type(root.path, followLinks: false) !=
          FileSystemEntityType.directory) {
        throw const FileSystemException('Unsafe operation timeline root');
      }
      for (final suffix in ['', '-wal', '-shm', '-journal']) {
        final type = await FileSystemEntity.type('$path$suffix', followLinks: false);
        if (type != FileSystemEntityType.notFound && type != FileSystemEntityType.file) {
          throw const FileSystemException('Unsafe operation timeline');
        }
      }
      Future<void> createScopeIndexes(Database db) async {
        await db.execute('CREATE INDEX IF NOT EXISTS operations_listing_history ON operations(listingKey, finished, updated DESC, id)');
        await db.execute('CREATE INDEX IF NOT EXISTS operations_package_history ON operations(packageId, finished, updated DESC, id)');
        await db.execute('CREATE INDEX IF NOT EXISTS operations_channel_history ON operations(channel, finished, updated DESC, id)');
        await db.execute('CREATE INDEX IF NOT EXISTS operations_parent ON operations(parentId)');
      }
      return openDatabase(path, version: 2, singleInstance: false,
      onUpgrade: (db, oldVersion, _) async {
        if (oldVersion == 1) await createScopeIndexes(db);
      },
      onConfigure: (db) async { await db.rawQuery('PRAGMA busy_timeout=0'); },
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
        await createScopeIndexes(db);
      });
    }, action, exclusive: true);
  }

  Future<List<R07TimelineEntry>> enqueue(List<R07OperationIntent> intents) async {
    if (intents.isEmpty) return [];
    for (final intent in intents) { intent.validate(); }
    final batch = _id();
    return _use((txn) async {
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
    });
  }

  Future<R07TimelineEntry> read(String id) => _use((db) async {
    final rows = await db.query('operations', where: 'id = ?', whereArgs: [id]);
    if (rows.length != 1) throw StateError('Operation no longer exists');
    return R07TimelineEntry.fromRow(rows.single);
  });

  static bool _allowedTransition(String before, String after) {
    if (before == 'queued') {
      return const {'checking', 'downloading', 'preparingInstall', 'cancelled', 'copying'}.contains(after);
    }
    if (const {'failed', 'cancelled', 'unknown'}.contains(after)) return !_terminal.contains(before);
    return switch (before) {
      'checking' => after == 'checked',
      'copying' => after == 'verifying',
      'downloading' => after == 'downloaded' || after == 'paused',
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
    return _use((txn) async {
      final rows = await txn.query('operations', where: 'id = ?', whereArgs: [id]);
      if (rows.length != 1) throw StateError('Operation no longer exists');
      final previous = R07TimelineEntry.fromRow(rows.single);
      if ((expectedStage != null && previous.stage != expectedStage) || previous.finished ||
          (previous.transferId != null && transferId != null && previous.transferId != transferId) ||
          (previous.attemptId != null && attemptId != null && previous.attemptId != attemptId) ||
          previous.revision >= 64 || !_allowedTransition(previous.stage, stage) ||
          (resolvedListingKey != null && (previous.resolvedListingKey != null ||
              previous.transferId == null || !const {'verifying', 'extracting'}.contains(previous.stage))) ||
          (stage == 'installLinked' && attemptId == null) ||
          (stage == 'copying' && previous.intent.kind != 'localArchive') ||
          (previous.intent.channel == 'unknown' && stage == 'ready')) {
        throw StateError('Operation changed or has already finished');
      }
      final owner = previous.stage == 'queued' && const {'checking', 'downloading', 'preparingInstall', 'copying'}.contains(stage)
          ? (await R07ProcessOwner.capture()).encode() : previous.processOwner;
      final update = <String, Object?>{'processOwner': owner, 'stage': stage, 'revision': previous.revision + 1,
        'updated': DateTime.now().toUtc().microsecondsSinceEpoch, 'reason': reason,
        'finished': _terminal.contains(stage) ? 1 : 0,
        'transferId': transferId ?? previous.transferId, 'attemptId': attemptId ?? previous.attemptId,
        'resolvedListingKey': resolvedListingKey ?? previous.resolvedListingKey,
        'resolvedPackageId': resolvedPackageId ?? previous.resolvedPackageId};
      if (await txn.update('operations', update, where: 'id = ? AND revision = ?',
          whereArgs: [id, previous.revision]) != 1) {
        throw StateError('Operation revision conflict');
      }
      await txn.insert('events', {'operationId': id, 'revision': update['revision'], 'stage': stage,
        'updated': update['updated'], 'reason': reason});
      return R07TimelineEntry.fromRow({...rows.single, ...update});
    });
  }

  /// Serialize actual owners, not just progress rows. Failure before acquiring
  /// the guard must not overwrite another owner's running receipt.
  Future<T> run<T>(R07TimelineEntry entry, R07OperationIntent expected,
      String startStage, Future<T> Function() action,
      {required String successStage, String Function(Object)? failureReason, String? Function(Object)? failureTransferId}) async {
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
          await advance(entry.id, reason == 'cancelled' ? 'cancelled' : reason == 'paused' ? 'paused' : 'failed', reason: reason, transferId: failureTransferId?.call(error));
        } catch (_) { /* primary failure remains authoritative */ }
        rethrow;
      }
    });
  }

  Future<R07TimelineEntry> beginLocalArchive() async {
    final id = _id(), batch = _id();
    final intent = R07OperationIntent(kind: 'localArchive', listingKey: 'local-archive',
      packageId: 'unknown', channel: 'unknown', release: r07JournalFingerprint('local-archive:$id'));
    intent.validate();
    final owner = (await R07ProcessOwner.capture()).encode();
    return _use((txn) async {
      final now = DateTime.now().toUtc().microsecondsSinceEpoch;
      final row = <String, Object?>{'id': id, 'batchId': batch, 'kind': intent.kind,
        'listingKey': intent.listingKey, 'packageId': intent.packageId, 'channel': intent.channel,
        'release': intent.release, 'stage': 'copying', 'revision': 1, 'updated': now,
        'finished': 0, 'processOwner': owner};
      await txn.insert('operations', row);
      await txn.insert('events', {'operationId': id, 'revision': 0, 'stage': 'queued', 'updated': now});
      await txn.insert('events', {'operationId': id, 'revision': 1, 'stage': 'copying', 'updated': now});
      return R07TimelineEntry.fromRow(row);
    });
  }

  Future<R07TimelineEntry> bindLocalArchive(String id, {required String listingKey,
      required String packageId, required String channel, required String archiveSha256}) async {
    if (!RegExp(r'^[a-f0-9]{64}$').hasMatch(archiveSha256) ||
        !RegExp(r'^[a-f0-9]{64}$').hasMatch(channel) ||
        !RegExp(r'^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$').hasMatch(packageId)) {
      throw const FormatException('Invalid manifest-bound local archive identity');
    }
    final bound = R07OperationIntent(kind: 'localArchive', listingKey: listingKey,
      packageId: packageId, channel: channel,
      release: r07JournalFingerprint('local-install:$archiveSha256'));
    bound.validate();
    return _use((txn) async {
      final rows = await txn.query('operations', where: 'id = ?', whereArgs: [id]);
      if (rows.length != 1) throw StateError('Local archive operation missing');
      final previous = R07TimelineEntry.fromRow(rows.single);
      if (previous.intent.kind != 'localArchive' || previous.intent.channel != 'unknown' ||
          previous.finished || previous.revision >= 64 || !const {'verifying', 'extracting'}.contains(previous.stage)) {
        throw StateError('Local archive has already been bound or settled');
      }
      final update = <String, Object?>{'listingKey': bound.listingKey, 'packageId': bound.packageId,
        'channel': bound.channel, 'release': bound.release, 'stage': 'ready',
        'revision': previous.revision + 1, 'updated': DateTime.now().toUtc().microsecondsSinceEpoch};
      if (await txn.update('operations', update, where: 'id = ? AND revision = ?',
          whereArgs: [id, previous.revision]) != 1) {
        throw StateError('Local archive identity changed');
      }
      await txn.insert('events', {'operationId': id, 'revision': update['revision'],
        'stage': 'ready', 'updated': update['updated']});
      return R07TimelineEntry.fromRow({...rows.single, ...update});
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
      if (!current.finished && const {'install', 'localArchive'}.contains(current.intent.kind) && current.stage != 'unknown') {
        await advance(id, stage, expectedStage: current.stage,
          reason: stage == 'cancelled' ? 'cancelled' : stage == 'unknown' ? 'ownership' : 'operation');
      }
    } catch (_) { /* preserve primary result; an unresolved receipt stays visible */ }
  }

  Future<void> observePreparation(String? id, String stage) async {
    if (id == null) return;
    final current = await read(id);
    if (current.finished) return; // Never replace the linked R05 outcome.
    if (!const {'install', 'localArchive'}.contains(current.intent.kind)) return;
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
        !const {'install', 'localArchive'}.contains(current.intent.kind) ||
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
  Future<List<R07TimelineEntry>> readActivity({int? historyLimit}) => _use((txn) async {
    final active = await txn.query('operations', where: 'finished = 0', orderBy: 'updated DESC, id');
    final history = historyLimit == 0 ? <Map<String, Object?>>[] : await txn.query('operations',
      where: 'finished = 1', orderBy: 'updated DESC, id', limit: historyLimit);
    return [...active, ...history].map(R07TimelineEntry.fromRow).toList(growable: false);
  });

  Future<({List<R07TimelineEntry> rows, int unreadableCount,
      Set<String> channels, Map<String, ({int completed, int total})> batches})> readForActivity({
      int? historyLimit, String? packageId, String? listingKey, String? operationId,
      String channel = 'all', String filter = 'all'}) => _use((txn) async {
    final scope = <String>[], args = <Object?>[];
    if (packageId != null) { scope.add('packageId = ?'); args.add(packageId); }
    if (listingKey != null) { scope.add('listingKey = ?'); args.add(listingKey); }
    if (operationId != null) { scope.add('id = ?'); args.add(operationId); }
    final channelRows = await txn.query('operations', distinct: true, columns: ['channel'],
      where: scope.isEmpty ? null : scope.join(' AND '), whereArgs: scope.isEmpty ? null : args);
    final channels = channelRows.map((row) => row['channel']).whereType<String>()
        .where((value) => value == 'unknown' || RegExp(r'^[a-f0-9]{64}$').hasMatch(value)).toSet();
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
  });

  Future<void> visitForExport(Future<void> Function(R07TimelineEntry) visit, {
      String? packageId, String? listingKey, String? operationId,
      String channel = 'all', String filter = 'all'}) => _use((txn) async {
    final conditions = <String>[], args = <Object?>[];
    if (packageId != null) { conditions.add('packageId = ?'); args.add(packageId); }
    if (listingKey != null) { conditions.add('listingKey = ?'); args.add(listingKey); }
    if (operationId != null) { conditions.add('id = ?'); args.add(operationId); }
    if (channel != 'all') { conditions.add('channel = ?'); args.add(channel); }
    if (filter == 'done') conditions.add('finished = 1');
    if (filter == 'review') conditions.add("stage IN ('queued', 'unknown', 'failed')");
    var after = '';
    while (true) {
      final page = await txn.query('operations', where: [...conditions, 'id > ?'].join(' AND '),
        whereArgs: [...args, after], orderBy: 'id', limit: 100);
      if (page.isEmpty) break;
      for (final row in page) {
        final record = R07TimelineEntry.fromRow(row);
        await visit(record);
        after = record.id;
      }
    }
  });

  // Compact only unlinked, terminal, known-channel, childless operations.
  // Retain the complete summary, first event and final event. Never delete
  // recovery bytes, unknown/paused operations or linked attempts/transfers.
  // Bounded review batches avoid an unbounded in-memory deletion manifest.
  Future<R07EventRetentionPreview> _previewEvents(Transaction txn, DateTime cutoff,
      String? listingKey, String? packageId, String? channel) async {
    final where = <String>['o.finished = 1', "o.stage IN ('checked','downloadReady','failed','cancelled','declined')",
      "o.channel != 'unknown'", 'o.parentId IS NULL', 'o.transferId IS NULL', 'o.attemptId IS NULL',
      'o.updated < ?', 'o.revision > 1',
      'NOT EXISTS (SELECT 1 FROM operations child WHERE child.parentId = o.id)',
      'EXISTS (SELECT 1 FROM events middle WHERE middle.operationId = o.id AND middle.revision > 0 AND middle.revision < o.revision)'];
    final args = <Object?>[cutoff.toUtc().microsecondsSinceEpoch];
    if (listingKey != null) { where.add('o.listingKey = ?'); args.add(listingKey); }
    if (packageId != null) { where.add('o.packageId = ?'); args.add(packageId); }
    if (channel != null) { where.add('o.channel = ?'); args.add(channel); }
    final rows = await txn.rawQuery('SELECT o.*, (SELECT COUNT(*) FROM events e WHERE e.operationId = o.id '
      'AND e.revision > 0 AND e.revision < o.revision) AS removable FROM operations o '
      'WHERE ${where.join(' AND ')} ORDER BY o.updated, o.id LIMIT 256', args);
    final entries = <String, ({int revision, int events, String fingerprint})>{};
    for (final row in rows) {
      final operation = R07TimelineEntry.fromRow(row);
      if (!RegExp(r'^[a-f0-9]{64}$').hasMatch(operation.intent.channel)) {
        throw const FormatException('Invalid timeline retention channel');
      }
      final events = await txn.query('events', where: 'operationId = ?',
        whereArgs: [operation.id], orderBy: 'revision', limit: 66);
      if (events.length != operation.revision + 1 || events.first['stage'] != 'queued' ||
          events.last['stage'] != operation.stage || events.last['updated'] != row['updated'] ||
          events.indexed.any((pair) => pair.$2['revision'] != pair.$1 ||
            !_stages.contains(pair.$2['stage']) || pair.$2['updated'] is! int ||
            (pair.$2['reason'] != null && !_reasons.contains(pair.$2['reason'])))) {
        throw const FormatException('Timeline retention endpoint mismatch');
      }
      entries[operation.id] = (revision: operation.revision, events: row['removable'] as int,
        fingerprint: r07JournalFingerprint(jsonEncode([row, events])));
    }
    return R07EventRetentionPreview._(cutoff.toUtc(), listingKey, packageId, channel, Map.unmodifiable(entries));
  }

  Future<R07EventRetentionPreview> previewTerminalEvents(DateTime cutoff, {
      String? listingKey, String? packageId, String? channel}) => _use((txn) =>
    _previewEvents(txn, cutoff, listingKey, packageId, channel));

  Future<int> compactTerminalEvents(R07EventRetentionPreview preview) => _use((txn) async {
    final current = await _previewEvents(txn, preview.cutoff, preview.listingKey,
      preview.packageId, preview.channel);
    if (current.entries.length != preview.entries.length || current.entries.entries.any(
        (entry) => preview.entries[entry.key] != entry.value)) {
      throw StateError('Timeline retention changed; review again');
    }
    var removed = 0;
    for (final entry in current.entries.entries) {
      final count = await txn.delete('events', where: 'operationId = ? AND revision > 0 AND revision < ?',
        whereArgs: [entry.key, entry.value.revision]);
      if (count != entry.value.events) throw StateError('Timeline retention changed');
      removed += count;
    }
    return removed;
  });

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
      final transferStage = const {'checking', 'downloading', 'downloaded', 'verifying', 'extracting', 'copying'}.contains(entry.stage);
      final preparationStage = const {'ready', 'scanning', 'preparingInstall'}.contains(entry.stage);
      if (!transferStage && !preparationStage) { continue; }
      if ((preparationStage || entry.intent.kind == 'localArchive') && (entry.processOwner == null ||
          await R07ProcessOwner.decode(entry.processOwner!).inspect() != R07ProcessState.dead)) {
        continue;
      }
      var entered = false;
      try {
        await withR07JournalGuard(Directory('${root.path}/r07-operation-timeline'),
          'listing:${entry.intent.kind == 'check' ? 'check' : 'transfer'}:${entry.intent.listingKey}', () async {
          entered = true;
          final current = await read(entry.id);
          if (current.revision == entry.revision && current.stage == entry.stage) {
            await advance(entry.id, 'unknown', expectedStage: entry.stage, reason: 'interrupted');
          }
        }, acquisitionTimeout: const Duration(milliseconds: 100));
      } on R07JournalBusy {
        // Only acquisition contention proves nothing about the existing owner.
        // A timeline failure inside the guard remains observable.
        if (entered) { rethrow; }
      }
    }
  }
}
