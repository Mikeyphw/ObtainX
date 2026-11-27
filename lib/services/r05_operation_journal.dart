/// Crash-tolerant, bounded, private on-device R05 operation receipts.
/// Files contain only redacted provenance and explicitly qualified evidence.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:obtainium/services/r05_operation_receipt.dart';
import 'package:obtainium/services/r07_journal_guard.dart';
import 'package:obtainium/services/r07_process_owner.dart';
import 'package:path_provider/path_provider.dart';

/// A read-only diagnostic projection. Corruption cannot authorize recovery or
/// mutation, but it must not hide all other independently readable history.
class R05JournalRead {
  const R05JournalRead(this.receipts, this.unreadableCount);
  final List<R05OperationReceipt> receipts;
  final int unreadableCount;
}

class R05RetentionPreview {
  R05RetentionPreview._(this.cutoff, this.listingKey, this.packageId,
      this.channel, Map<String, String> entries)
      : entries = Map.unmodifiable(entries);
  final DateTime cutoff;
  final String? listingKey, packageId, channel;
  final Map<String, String> entries;
}

class R05OperationJournal {
  R05OperationJournal({Directory? testingRoot}) : this._internal(testingRoot);
  R05OperationJournal._internal(this._testingRoot);
  static final R05OperationJournal instance = R05OperationJournal();
  // Limit unresolved operations, not the accumulated immutable history.
  static const int maxOperations = 512;
  static bool _terminal(R05OperationReceipt item) => const {
    R05InstallStage.confirmed, R05InstallStage.failed, R05InstallStage.cancelled,
  }.contains(item.stage);
  static const int maxReceiptBytes = 64 * 1024;
  final Directory? _testingRoot;
  Future<void> _tail = Future<void>.value();
  Future<void>? _startupRecovery;

  Future<void> recoverInterruptedOnce() =>
      _startupRecovery ??= recoverInterrupted();

  Future<T> _exclusive<T>(Future<T> Function() operation) {
    final result = Completer<T>();
    _tail = _tail.catchError((Object _) {}).then((_) async {
      try {
        final root = await _root();
        result.complete(await withR07JournalGuard(root, 'install-journal', operation));
      } catch (error, stack) {
        result.completeError(error, stack);
      }
    });
    return result.future;
  }

  Future<Directory> _root() async {
    final base = _testingRoot ?? await getApplicationSupportDirectory();
    final path = Directory('${base.path}/r05-install-operations');
    if (await FileSystemEntity.type(path.path, followLinks: false) == FileSystemEntityType.link) {
      throw const FileSystemException('R05 operation folder is a symbolic link');
    }
    await path.create(recursive: true);
    if (await FileSystemEntity.type(path.path, followLinks: false) != FileSystemEntityType.directory) {
      throw const FileSystemException('R05 operation folder is not a directory');
    }
    return path;
  }

  Future<Directory> _archive(Directory root) async {
    final directory = Directory('${root.path}.history');
    final type = await FileSystemEntity.type(directory.path, followLinks: false);
    if (type != FileSystemEntityType.notFound && type != FileSystemEntityType.directory) {
      throw const FileSystemException('Unsafe R05 historical archive');
    }
    return directory;
  }

  Future<File> _locate(Directory root, String id) async {
    final active = _file(root, id);
    final archived = _file(await _archive(root), id);
    final liveType = await FileSystemEntity.type(active.path, followLinks: false);
    final pastType = await FileSystemEntity.type(archived.path, followLinks: false);
    if (liveType != FileSystemEntityType.notFound && pastType != FileSystemEntityType.notFound) {
      throw const FormatException('Duplicate active and historical R05 identity');
    }
    if (liveType != FileSystemEntityType.notFound) return active;
    return archived;
  }

  Future<void> _archiveTerminal(Directory root, R05OperationReceipt receipt) async {
    if (!_terminal(receipt)) return;
    final archive = await _archive(root);
    await archive.create(recursive: true);
    final target = _file(archive, receipt.id);
    if (await FileSystemEntity.type(target.path, followLinks: false) != FileSystemEntityType.notFound) {
      throw const FormatException('R05 archive identity already exists');
    }
    final active = _file(root, receipt.id);
    // Publish the terminal receipt first, then move it atomically. Either
    // location remains readable after process death; no copy/delete window.
    await active.rename(target.path);
  }

  File _file(Directory root, String id) {
    if (!RegExp(r'^[A-Za-z0-9_-]{16,90}$').hasMatch(id)) {
      throw const FormatException('Unsafe R05 operation identifier');
    }
    return File('${root.path}/$id.json');
  }

  Future<R05OperationReceipt> _read(File file) async {
    if (await FileSystemEntity.type(file.path, followLinks: false) != FileSystemEntityType.file ||
        await file.length() > maxReceiptBytes) {
      throw const FormatException('Untrusted R05 journal entry');
    }
    final content = await file.readAsString(encoding: utf8);
    if (utf8.encode(content).length > maxReceiptBytes) {
      throw const FormatException('Oversize R05 journal entry');
    }
    final receipt = R05OperationReceipt.decode(content);
    if ('${receipt.id}.json' != file.uri.pathSegments.last) {
      throw const FormatException('R05 receipt file identity mismatch');
    }
    return receipt;
  }

  Future<R05JournalRead> _scan({required bool strict, bool includeHistory = true,
      int? historyLimit, bool Function(R05OperationReceipt)? includeFinished,
      void Function(R05OperationReceipt)? observe,
      Future<void> Function(R05OperationReceipt)? visit}) async {
    final root = await _root();
    final receipts = <R05OperationReceipt>[];
    final finished = <R05OperationReceipt>[];
    var unreadable = 0;
    final directories = <Directory>[root];
    if (includeHistory) {
      try {
        final archive = await _archive(root);
        if (await archive.exists()) directories.add(archive);
      } on FileSystemException {
        if (strict) rethrow;
        unreadable++;
      }
    }
    final ids = <String>{};
    for (final directory in directories) {
    await for (final entity in directory.list(followLinks: false)) {
      try {
        final name = entity.uri.pathSegments.last;
        // Staging is not an outcome. Preserve interrupted staging files.
        if (RegExp(r'^\.[A-Za-z0-9_-]{16,90}-[0-9a-f]{24}\.tmp$').hasMatch(name)) {
          if (entity is! File ||
              await FileSystemEntity.type(entity.path, followLinks: false) != FileSystemEntityType.file ||
              await entity.length() > maxReceiptBytes) {
            throw const FormatException('Unsafe R05 interrupted staging file');
          }
          continue;
        }
        if (entity is! File || !RegExp(r'^[A-Za-z0-9_-]{16,90}\.json$').hasMatch(name)) {
          throw const FormatException('Unknown or interrupted R05 journal file');
        }
        final item = await _read(entity);
        if (directory.path != root.path && !_terminal(item)) {
          throw const FormatException('Unresolved receipt in historical archive');
        }
        if (visit != null) {
          // Under the exclusive journal guard, an exact counterpart path is
          // sufficient to detect duplicate identities without an O(n) set.
          final counterpart = directory.path == root.path ? await _archive(root) : root;
          if (await FileSystemEntity.type(_file(counterpart, item.id).path, followLinks: false) !=
              FileSystemEntityType.notFound) {
            throw const FormatException('Duplicate R05 receipt identity');
          }
          await visit(item);
          continue;
        }
        if (!ids.add(item.id)) throw const FormatException('Duplicate R05 receipt identity');
        observe?.call(item);
        final terminalForActivity = _terminal(item) &&
            (item.stage != R05InstallStage.confirmed || item.exactBytesConfirmed);
        if (terminalForActivity && (historyLimit != null || includeFinished != null)) {
          if (includeFinished?.call(item) == false || historyLimit == 0) { continue; }
          finished.add(item);
          if (historyLimit != null) {
            finished.sort((a, b) {
              final order = b.updatedUtc.compareTo(a.updatedUtc);
              return order == 0 ? a.id.compareTo(b.id) : order;
            });
            if (finished.length > historyLimit) { finished.removeLast(); }
          }
        } else {
          receipts.add(item);
        }
      } on FileSystemException {
        if (strict) rethrow;
        unreadable++;
      } on FormatException {
        if (strict) rethrow;
        unreadable++;
      } on TypeError {
        if (strict) rethrow;
        unreadable++;
      }
    }
    }
    receipts.addAll(finished);
    receipts.sort((a, b) {
      final time = b.createdUtc.compareTo(a.createdUtc);
      return time == 0 ? a.id.compareTo(b.id) : time;
    });
    return R05JournalRead(List.unmodifiable(receipts), unreadable);
  }

  Future<void> visitForExport(Future<void> Function(R05OperationReceipt) visit) =>
    _exclusive(() async { await _scan(strict: true, visit: visit); });

  Future<List<R05OperationReceipt>> _readAll() async =>
      (await _scan(strict: true)).receipts;

  Future<List<R05OperationReceipt>> _readRecovery() async =>
      (await _scan(strict: true, includeHistory: false)).receipts;

  Future<R05JournalRead> readForActivity({int? historyLimit,
      bool Function(R05OperationReceipt)? includeFinished,
      void Function(R05OperationReceipt)? observe}) =>
      _exclusive(() => _scan(strict: false, historyLimit: historyLimit,
        includeFinished: includeFinished, observe: observe));

  Future<void> _write(R05OperationReceipt receipt, {bool creating = false}) async {
    final root = await _root();
    final target = _file(root, receipt.id);
    if (await FileSystemEntity.type(_file(await _archive(root), receipt.id).path, followLinks: false) != FileSystemEntityType.notFound) {
      throw const FormatException('Cannot overwrite archived R05 receipt');
    }
    final currentType = await FileSystemEntity.type(target.path, followLinks: false);
    if (currentType == FileSystemEntityType.link ||
        (creating && currentType != FileSystemEntityType.notFound)) {
      throw const FileSystemException('Conflicting or symlink R05 receipt');
    }
    if (!creating && currentType != FileSystemEntityType.file) {
      throw const FileSystemException('R05 receipt missing for update');
    }
    final bytes = utf8.encode(receipt.encode());
    if (bytes.length > maxReceiptBytes) throw const FormatException('R05 receipt too large');
    final random = Random.secure();
    final suffix = List<int>.generate(12, (_) => random.nextInt(256))
        .map((b) => b.toRadixString(16).padLeft(2, '0')).join();
    final stage = File('${root.path}/.${receipt.id}-$suffix.tmp');
    await stage.create(exclusive: true);
    try {
      await stage.writeAsBytes(bytes, flush: true);
      await stage.rename(target.path); // atomic replacement, same private filesystem
    } finally {
      if (await stage.exists()) await stage.delete();
    }
    await _archiveTerminal(root, receipt);
  }

  Future<R05OperationReceipt> begin({
    required String listingKey, required String packageId,
    required String backend, required String kind,
    required List<String> fileNames,
    String? sourceHost, String? sourceBranch, String? workflow,
    String? channelFingerprint,
    int? runId, int? runAttempt, String? commitSha, int? artifactId,
    String? downloadSha256, String? archiveSignerSha256, int? expectedVersionCode,
    List<String> selectedApkSha256 = const [], List<String> archiveSignerSet = const [],
    String? releaseFingerprint, String? containerSha256, int? workflowId,
    String? sourceRepository, String? finalOrigin, String? parentAttemptId, String? timelineId,
    String? processOwner,
  }) => _exclusive(() async {
    final all = await _readRecovery();
    if (timelineId != null && all.any((item) => item.listingKey == listingKey && !_terminal(item))) {
      throw StateError('An unresolved attempt already owns this listing');
    }
    if (parentAttemptId != null) {
      final parent = await _read(await _locate(await _root(), parentAttemptId));
      if (channelFingerprint == null || releaseFingerprint == null ||
          parent.listingKey != listingKey || parent.packageId != packageId ||
          parent.channelFingerprint != channelFingerprint || parent.releaseFingerprint != releaseFingerprint ||
          !const {R05InstallStage.failed, R05InstallStage.cancelled}.contains(parent.stage) ||
          all.any((item) => item.listingKey == listingKey && !_terminal(item))) {
        throw StateError('Retry parent or current ownership is no longer qualified');
      }
    }
    if (all.where((item) => !_terminal(item)).length >= maxOperations) {
      throw const FileSystemException('R05 unresolved operation limit reached');
    }
    final random = Random.secure();
    final id = 'r05_${DateTime.now().toUtc().microsecondsSinceEpoch.toRadixString(16)}_'
        '${List<int>.generate(12, (_) => random.nextInt(256)).map((b) => b.toRadixString(16).padLeft(2, '0')).join()}';
    final receipt = R05OperationReceipt.start(
      id: id, listingKey: listingKey, packageId: packageId,
      backend: backend, kind: kind, fileNames: fileNames,
      channelFingerprint: channelFingerprint,
      sourceHost: sourceHost, sourceBranch: sourceBranch, workflow: workflow,
      runId: runId, runAttempt: runAttempt, commitSha: commitSha,
      artifactId: artifactId, expectedVersionCode: expectedVersionCode, downloadSha256: downloadSha256,
      archiveSignerSha256: archiveSignerSha256,
      selectedApkSha256: selectedApkSha256, archiveSignerSet: archiveSignerSet,
      releaseFingerprint: releaseFingerprint, containerSha256: containerSha256,
      workflowId: workflowId, sourceRepository: sourceRepository, finalOrigin: finalOrigin,
      parentAttemptId: parentAttemptId, timelineId: timelineId, processOwner: processOwner,
    );
    await _write(receipt, creating: true);
    return receipt;
  });

  Future<R05OperationReceipt> transition(String id, R05InstallStage stage, {
    R05AndroidEvidence? evidence, int? androidCode, String? reason,
  }) => _exclusive(() async {
    final root = await _root();
    final previous = await _read(await _locate(root, id));
    final updated = previous.transition(stage, evidence: evidence,
        androidCode: androidCode, reason: reason);
    await _write(updated);
    return updated;
  });

  /// Late callbacks may race an independently verified package broadcast.
  /// Never regress a terminal outcome or overwrite a newer confirmation.
  Future<R05OperationReceipt> settleIfOpen(String id, R05InstallStage stage, {
    R05AndroidEvidence? evidence, int? androidCode, String? reason,
  }) => _exclusive(() async {
    final root = await _root();
    final previous = await _read(await _locate(root, id));
    if (previous.stage == R05InstallStage.confirmed ||
        previous.stage == R05InstallStage.failed ||
        previous.stage == R05InstallStage.cancelled ||
        (previous.stage == R05InstallStage.unknown && stage != R05InstallStage.confirmed &&
            stage != R05InstallStage.failed) ||
        (previous.stage == R05InstallStage.handedOff &&
            (stage == R05InstallStage.awaitingApproval || stage == R05InstallStage.handedOff))) {
      return previous;
    }
    final updated = previous.transition(stage, evidence: evidence,
        androidCode: androidCode, reason: reason);
    await _write(updated);
    return updated;
  });

  Future<List<R05OperationReceipt>> list() => _exclusive(_readAll);

  /// Explicit retention preview. Unknown channel ownership remains read-only;
  /// the null filter selects all independently bound channels.
  bool _retentionMatch(R05OperationReceipt item, DateTime cutoff,
      String? listingKey, String? packageId, String? channel) =>
      item.channelFingerprint != null &&
      _terminal(item) && (item.stage != R05InstallStage.confirmed || item.exactBytesConfirmed) &&
      item.updatedUtc.isBefore(cutoff.toUtc()) &&
      (listingKey == null || item.listingKey == listingKey) &&
      (packageId == null || item.packageId == packageId) &&
      (channel == null || item.channelFingerprint == channel);

  Future<R05RetentionPreview> _preview(DateTime cutoff, String? listingKey,
      String? packageId, String? channel) async {
    final all = await _readAll();
    final referencedParents = all.map((item) => item.parentAttemptId).whereType<String>().toSet();
    return R05RetentionPreview._(cutoff.toUtc(), listingKey, packageId, channel, {
      for (final item in all)
        if (!referencedParents.contains(item.id) && _retentionMatch(item, cutoff, listingKey, packageId, channel))
          item.id: item.encode(),
    });
  }

  Future<R05RetentionPreview> previewTerminalBefore(DateTime cutoff, {
    String? listingKey, String? packageId, String? channel,
  }) => _exclusive(() => _preview(cutoff, listingKey, packageId, channel));

  /// Every deletion is limited to the reviewed immutable terminal receipt.
  /// A changed selection refuses before deletion; unresolved entries and R03
  /// recovery bytes are never touched. Terminal stages have no transitions.
  Future<int> pruneTerminalBefore(DateTime cutoff, {String? listingKey,
    String? packageId, String? channel, R05RetentionPreview? preview,
  }) => _exclusive(() async {
    final current = await _preview(cutoff, listingKey, packageId, channel);
    if (preview != null && (preview.cutoff != current.cutoff ||
        preview.listingKey != current.listingKey || preview.packageId != current.packageId ||
        preview.channel != current.channel || preview.entries.length != current.entries.length ||
        preview.entries.entries.any((entry) => current.entries[entry.key] != entry.value))) {
      throw StateError('History selection changed; review retention again');
    }
    final approved = preview ?? current;
    final root = await _root();
    var removed = 0;
    for (final entry in approved.entries.entries) {
      final file = await _locate(root, entry.key);
      if (await FileSystemEntity.type(file.path, followLinks: false) == FileSystemEntityType.notFound) {
        continue;
      }
      final item = await _read(file);
      if (item.encode() != entry.value ||
          !_retentionMatch(item, cutoff, listingKey, packageId, channel)) {
        throw StateError('History selection changed; review retention again');
      }
      // A concurrent legitimate prune may already have removed this immutable
      // receipt. Do not remove or substitute any other file.
      try {
        await file.delete();
        removed++;
      } on FileSystemException {
        if (await FileSystemEntity.type(file.path, followLinks: false) != FileSystemEntityType.notFound) rethrow;
      }
    }
    return removed;
  });

  /// A broadcast has package scope, not operation scope. Never attribute it
  /// to a specific install attempt while two live attempts are ambiguous.
  Future<R05OperationReceipt?> uniqueUnresolved(String listingKey) => _exclusive(() async {
    final candidates = (await _readRecovery()).where((item) =>
      item.listingKey == listingKey &&
      (item.stage == R05InstallStage.pending ||
       item.stage == R05InstallStage.awaitingApproval ||
       item.stage == R05InstallStage.handedOff ||
       item.stage == R05InstallStage.unknown)).toList();
    return candidates.length == 1 ? candidates.single : null;
  });

  Future<R05OperationReceipt?> latestUnresolved(String listingKey) => _exclusive(() async {
    final all = await _readRecovery();
    for (final item in all) {
      if (item.listingKey == listingKey &&
          (item.stage == R05InstallStage.pending ||
           item.stage == R05InstallStage.awaitingApproval ||
           item.stage == R05InstallStage.handedOff ||
           item.stage == R05InstallStage.unknown)) {
        return item;
      }
    }
    return null;
  });

  /// Process death cannot be interpreted as cancellation or success.
  /// An unresolved Android approval/handoff remains visible in the review UI.
  Future<void> recoverInterrupted() => _exclusive(() async {
    final root = await _root();
    final all = await _readRecovery();
    for (final item in all) {
      if (_terminal(item)) {
        await _archiveTerminal(root, item);
      } else if (item.stage == R05InstallStage.pending) {
        final owner = item.processOwner;
        if (owner != null && await R07ProcessOwner.decode(owner).inspect() != R07ProcessState.dead) {
          continue; // A live or unprovable owner is not evidence of interruption.
        }
        await _write(item.transition(R05InstallStage.unknown,
            reason: 'App restarted before installer outcome was recorded'));
      }
    }
  });
}
