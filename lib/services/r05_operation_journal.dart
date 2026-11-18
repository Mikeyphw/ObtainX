/// Crash-tolerant, bounded, private on-device R05 operation receipts.
/// Files contain only redacted provenance and explicitly qualified evidence.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:obtainium/services/r05_operation_receipt.dart';
import 'package:path_provider/path_provider.dart';

class R05OperationJournal {
  R05OperationJournal({Directory? testingRoot}) : this._internal(testingRoot);
  R05OperationJournal._internal(this._testingRoot);
  static final R05OperationJournal instance = R05OperationJournal();
  static const int maxOperations = 512;
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
        result.complete(await operation());
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

  Future<List<R05OperationReceipt>> _readAll() async {
    final root = await _root();
    final files = await root.list(followLinks: false).toList();
    if (files.length > maxOperations) throw const FileSystemException('R05 journal inventory exceeds limit');
    final receipts = <R05OperationReceipt>[];
    for (final entity in files) {
      final name = entity.uri.pathSegments.last;
      // A crash between temp creation and atomic rename leaves a staging
      // file. It is not a committed receipt; preserve it without deleting
      // it or promoting it to an outcome.
      if (RegExp(r'^\.[A-Za-z0-9_-]{16,90}-[0-9a-f]{24}\.tmp$').hasMatch(name)) {
        if (entity is! File || await entity.length() > maxReceiptBytes) {
          throw const FormatException('Unsafe R05 interrupted staging file');
        }
        continue;
      }
      if (entity is! File || !RegExp(r'^[A-Za-z0-9_-]{16,90}\.json$')
          .hasMatch(entity.uri.pathSegments.last)) {
        throw const FormatException('Unknown or interrupted R05 journal file');
      }
      receipts.add(await _read(entity));
    }
    receipts.sort((a, b) => b.createdUtc.compareTo(a.createdUtc));
    return List<R05OperationReceipt>.unmodifiable(receipts);
  }

  Future<void> _write(R05OperationReceipt receipt, {bool creating = false}) async {
    final root = await _root();
    final target = _file(root, receipt.id);
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
  }

  Future<R05OperationReceipt> begin({
    required String listingKey, required String packageId,
    required String backend, required String kind,
    required List<String> fileNames,
    String? sourceHost, String? sourceBranch, String? workflow,
    int? runId, int? runAttempt, String? commitSha, int? artifactId,
    String? downloadSha256, String? archiveSignerSha256, int? expectedVersionCode,
  }) => _exclusive(() async {
    final all = await _readAll();
    if (all.length >= maxOperations) {
      throw const FileSystemException('R05 journal full: export or explicitly clear old evidence first');
    }
    final random = Random.secure();
    final id = 'r05_${DateTime.now().toUtc().microsecondsSinceEpoch.toRadixString(16)}_'
        '${List<int>.generate(12, (_) => random.nextInt(256)).map((b) => b.toRadixString(16).padLeft(2, '0')).join()}';
    final receipt = R05OperationReceipt.start(
      id: id, listingKey: listingKey, packageId: packageId,
      backend: backend, kind: kind, fileNames: fileNames,
      sourceHost: sourceHost, sourceBranch: sourceBranch, workflow: workflow,
      runId: runId, runAttempt: runAttempt, commitSha: commitSha,
      artifactId: artifactId, expectedVersionCode: expectedVersionCode, downloadSha256: downloadSha256,
      archiveSignerSha256: archiveSignerSha256,
    );
    await _write(receipt, creating: true);
    return receipt;
  });

  Future<R05OperationReceipt> transition(String id, R05InstallStage stage, {
    R05AndroidEvidence? evidence, int? androidCode, String? reason,
  }) => _exclusive(() async {
    final root = await _root();
    final previous = await _read(_file(root, id));
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
    final previous = await _read(_file(root, id));
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

  /// A broadcast has package scope, not operation scope. Never attribute it
  /// to a specific install attempt while two live attempts are ambiguous.
  Future<R05OperationReceipt?> uniqueUnresolved(String listingKey) => _exclusive(() async {
    final candidates = (await _readAll()).where((item) =>
      item.listingKey == listingKey &&
      (item.stage == R05InstallStage.pending ||
       item.stage == R05InstallStage.awaitingApproval ||
       item.stage == R05InstallStage.handedOff ||
       item.stage == R05InstallStage.unknown)).toList();
    return candidates.length == 1 ? candidates.single : null;
  });

  Future<R05OperationReceipt?> latestUnresolved(String listingKey) => _exclusive(() async {
    final all = await _readAll();
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
    final all = await _readAll();
    for (final item in all) {
      if (item.stage == R05InstallStage.pending) {
        await _write(item.transition(R05InstallStage.unknown,
            reason: 'App restarted before installer outcome was recorded'));
      }
    }
  });
}
