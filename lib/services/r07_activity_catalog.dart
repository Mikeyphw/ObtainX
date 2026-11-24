/// R07 Activity Center is a READ-ONLY projection of the existing R03 and R05
/// journals. It never records an operation, changes an outcome or assumes that
/// an Android installer handoff succeeded.
library;

import 'dart:convert';
import 'dart:io';

import 'package:obtainium/services/r03_download_engine.dart';
import 'package:obtainium/services/r05_operation_journal.dart';
import 'package:obtainium/services/r05_operation_receipt.dart';
import 'package:path_provider/path_provider.dart';

/// A UI row is bound to one particular journal record; download fingerprints
/// are not installation attempt IDs and are never merged just by package name.
class R07ActivityRecord {
  const R07ActivityRecord({
    required this.id,
    required this.kind,
    required this.stage,
    required this.title,
    required this.updatedUtc,
    this.listingKey,
    this.packageId,
    this.sourceHost,
    this.reason,
    this.verifiedBytes,
    this.totalBytes,
    this.download,
    this.install,
    this.uniquePendingOwnership = false,
  });

  final String id, kind, stage, title;
  final String? listingKey, packageId, sourceHost, reason;
  final DateTime updatedUtc;
  final int? verifiedBytes, totalBytes;
  final R03DownloadRecord? download;
  final R05OperationReceipt? install;
  final bool uniquePendingOwnership;

  bool get needsReview =>
      (kind == 'install' &&
          (stage == 'awaitingApproval' || stage == 'handedOff' ||
              stage == 'pending' || stage == 'unknown')) ||
      stage == 'failed';

  bool get isFinished => stage == 'confirmed' || stage == 'completed' ||
      stage == 'ready' || stage == 'cancelled' || stage == 'failed';

  /// Only cryptographically finalized download records may display 100%.
  /// A file transfer finishing is NOT a successful installation.
  double? get progress {
    if (kind != 'download' || totalBytes == null || totalBytes! <= 0 ||
        verifiedBytes == null) return null;
    final digest = download?.finalDigest;
    final done = digest != null && RegExp(r'^[a-f0-9]{64}$').hasMatch(digest) &&
        download?.completedBytes == totalBytes &&
        (download?.stage == R03Stage.ready ||
            download?.stage == R03Stage.completed);
    final ratio = (verifiedBytes! / totalBytes!).clamp(0.0, 1.0).toDouble();
    return done ? ratio : ratio.clamp(0.0, 0.99).toDouble();
  }
}

/// Valid actions depend on both journal stage and independent live evidence.
/// This pure function is also the gate used immediately before each action.
enum R07ActivityAction { review, resume, retry, cancel, open, details }

Set<R07ActivityAction> r07AllowedActions(
  R07ActivityRecord entry, {
  required bool listingMatches,
  required bool liveDownload,
  required bool cancellableInstall,
  required bool independentlyInstalled,
}) {
  final result = <R07ActivityAction>{R07ActivityAction.details};
  if (entry.kind == 'install') {
    if (entry.needsReview) result.add(R07ActivityAction.review);
    if (listingMatches && !liveDownload &&
        (entry.stage == 'unknown' || entry.stage == 'failed' ||
            entry.stage == 'cancelled')) {
      result.add(R07ActivityAction.retry);
    }
    if (listingMatches && cancellableInstall && entry.uniquePendingOwnership &&
        (entry.stage == 'pending' || entry.stage == 'awaitingApproval')) {
      result.add(R07ActivityAction.cancel);
    }
    if (entry.stage == 'confirmed' && independentlyInstalled) {
      result.add(R07ActivityAction.open);
    }
  } else if (entry.kind == 'live') {
    // Exact provider operation keyed by listing; never cancel by historical R03
    // filename. A different transfer might now own the same listing.
    if (listingMatches && liveDownload && entry.stage == 'downloading') {
      result.add(R07ActivityAction.cancel);
    }
  } else if (entry.kind == 'download') {
    if (listingMatches && !liveDownload &&
        (entry.stage == 'paused' || entry.stage == 'failed' ||
            entry.stage == 'cancelled' || entry.stage == 'retrying')) {
      result.add(R07ActivityAction.resume);
    }
  }
  return result;
}

/// A listing association is accepted only when the persisted filename has a
/// unique source-listing prefix. Distinct sources of the same Android package
/// must NOT acquire one another's Retry or Cancel actions.
String? r07UniqueListingForFile(String fileName, Iterable<String> keys) {
  final matches = keys.where((key) =>
      key.isNotEmpty && fileName.startsWith('$key-')).toList();
  // A prefix relationship between two listing keys is ambiguous without
  // authoritative transfer metadata. Never guess the longer key here.
  return matches.length == 1 ? matches.single : null;
}

class R07ActivityCatalog {
  R07ActivityCatalog({Directory? testingRoot, R05OperationJournal? installJournal})
      : _testingRoot = testingRoot,
        _installJournal = installJournal ?? R05OperationJournal.instance;

  final Directory? _testingRoot;
  final R05OperationJournal _installJournal;
  static const int maxDownloadReceipts = 512;
  static const int maxDownloadReceiptBytes = 128 * 1024;
  static final RegExp _downloadFile = RegExp(r'^[a-f0-9]{64}\.json$');

  Future<List<R07ActivityRecord>> load({
    Map<String, String> trackedPackages = const <String, String>{},
  }) async {
    // AppsProvider owns one-time startup recovery. A read-only screen MUST
    // NOT turn an in-flight install pending into unknown while it is active.
    final installs = await _installJournal.list();
    final unresolvedCounts = <String,int>{};
    for (final attempt in installs) {
      if (attempt.stage == R05InstallStage.pending ||
          attempt.stage == R05InstallStage.awaitingApproval ||
          attempt.stage == R05InstallStage.handedOff ||
          attempt.stage == R05InstallStage.unknown) {
        unresolvedCounts.update(attempt.listingKey,(n)=>n+1,ifAbsent:()=>1);
      }
    }
    final records = <R07ActivityRecord>[
      for (final attempt in installs)
        R07ActivityRecord(
          id: 'install:${attempt.id}', kind: 'install',
          stage: attempt.stage.name, title: attempt.packageId,
          listingKey: attempt.listingKey, packageId: attempt.packageId,
          sourceHost: attempt.sourceHost, reason: attempt.reason,
          updatedUtc: attempt.updatedUtc, install: attempt,
          uniquePendingOwnership: unresolvedCounts[attempt.listingKey] == 1,
        ),
    ];

    final root = _testingRoot ?? await getApplicationSupportDirectory();
    final folder = Directory('${root.path}/r03-download-journal');
    final type = await FileSystemEntity.type(folder.path, followLinks: false);
    if (type == FileSystemEntityType.notFound) {
      records.sort((a, b) => b.updatedUtc.compareTo(a.updatedUtc));
      return List<R07ActivityRecord>.unmodifiable(records);
    }
    if (type != FileSystemEntityType.directory) {
      throw const FileSystemException('Unsafe R03 download journal directory');
    }
    final entries = await folder.list(followLinks: false).toList();
    if (entries.length > maxDownloadReceipts) {
      throw const FileSystemException('R03 download journal exceeds activity limit');
    }
    for (final entity in entries) {
      final name = entity.uri.pathSegments.last;
      // R03 writes `<fingerprint>.json.tmp` atomically. Never read its staging
      // bytes, and never treat a staging file as a completed download.
      if (name.endsWith('.json.tmp') && _downloadFile.hasMatch(
          name.substring(0, name.length - 4))) {
        if (await FileSystemEntity.type(entity.path, followLinks: false) !=
            FileSystemEntityType.file) {
          throw const FormatException('Unsafe R03 staging file');
        }
        continue;
      }
      if (!_downloadFile.hasMatch(name) || entity is! File ||
          await FileSystemEntity.type(entity.path, followLinks: false) !=
              FileSystemEntityType.file ||
          await entity.length() > maxDownloadReceiptBytes) {
        // Invalid/corrupted records are not treated as completed downloads.
        // The UI surfaces the read failure; data remains on disk for audit.
        throw const FormatException('Unsafe or corrupt R03 download entry');
      }
      final decoded = jsonDecode(await entity.readAsString(encoding: utf8));
      if (decoded is! Map<String, dynamic>) {
        throw const FormatException('Malformed R03 download receipt');
      }
      final transfer = R03DownloadRecord.fromJson(decoded);
      if (name != '${transfer.jobId}.json' ||
          transfer.sourceFingerprint != transfer.jobId) {
        throw const FormatException('R03 receipt identity mismatch');
      }
      final listing = r07UniqueListingForFile(
          transfer.fileName, trackedPackages.keys);
      final complete = transfer.finalDigest != null &&
          RegExp(r'^[a-f0-9]{64}$').hasMatch(transfer.finalDigest!) &&
          transfer.completedBytes == transfer.totalBytes &&
          (transfer.stage == R03Stage.ready ||
              transfer.stage == R03Stage.completed);
      final amount = complete ? transfer.completedBytes : transfer.validatedBytes;
      final stat = await entity.stat();
      records.add(R07ActivityRecord(
        id: 'download:${transfer.jobId}', kind: 'download',
        stage: transfer.stage.name,
        title: listing == null ? transfer.fileName :
            (trackedPackages[listing] ?? transfer.fileName),
        listingKey: listing,
        packageId: listing == null ? null : trackedPackages[listing],
        sourceHost: transfer.origin,
        updatedUtc: stat.modified.toUtc(),
        verifiedBytes: amount, totalBytes: transfer.totalBytes,
        download: transfer,
      ));
    }
    records.sort((a, b) {
      final compared = b.updatedUtc.compareTo(a.updatedUtc);
      return compared == 0 ? a.id.compareTo(b.id) : compared;
    });
    return List<R07ActivityRecord>.unmodifiable(records);
  }
}
