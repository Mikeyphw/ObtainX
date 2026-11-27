/// R07 Activity Center is a READ-ONLY projection of the R03 and R05
/// journals and the durable R07 operation timeline. It never records an operation, changes an outcome or assumes that
/// an Android installer handoff succeeded.
library;

import 'dart:io';

import 'package:obtainium/services/r03_download_engine.dart';
import 'package:obtainium/services/r03_download_history.dart';
import 'package:obtainium/services/r05_operation_journal.dart';
import 'package:obtainium/services/r05_operation_receipt.dart';
import 'package:obtainium/services/r07_operation_timeline.dart';
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
    this.historyIntegrityKnown = true,
    this.timeline, this.batchCompleted, this.batchTotal, this.archivedTransfer = false,
  });

  final String id, kind, stage, title;
  final String? listingKey, packageId, sourceHost, reason;
  final DateTime updatedUtc;
  final int? verifiedBytes, totalBytes;
  final R03DownloadRecord? download;
  final R05OperationReceipt? install;
  final R07TimelineEntry? timeline;
  final int? batchCompleted, batchTotal;
  final bool uniquePendingOwnership, historyIntegrityKnown, archivedTransfer;

  bool get needsReview =>
      (kind == 'install' &&
          (stage == 'awaitingApproval' || stage == 'handedOff' ||
              stage == 'pending' || stage == 'unknown')) ||
      stage == 'failed' || (timeline != null && (stage == 'queued' || stage == 'unknown'));

  bool get isFinished => archivedTransfer || timeline?.finished == true || (download?.explicitlyResumable != true && (stage == 'confirmed' || stage == 'completed' ||
      (stage == 'ready' && timeline == null) || stage == 'cancelled' || stage == 'failed'));

  /// Only cryptographically finalized download records may display 100%.
  /// A file transfer finishing is NOT a successful installation.
  double? get progress {
    if (kind != 'download' || totalBytes == null || totalBytes! <= 0 ||
        verifiedBytes == null) {
      return null;
    }
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
  if (!entry.historyIntegrityKnown || entry.kind == 'integrity') return result;
  if (entry.kind == 'install') {
    if (entry.needsReview) result.add(R07ActivityAction.review);
    if (listingMatches && !liveDownload &&
        (entry.stage == 'failed' || entry.stage == 'cancelled') &&
        entry.install?.releaseFingerprint != null) {
      result.add(R07ActivityAction.retry);
    }
    if (listingMatches && cancellableInstall && entry.uniquePendingOwnership &&
        (entry.stage == 'pending' || entry.stage == 'awaitingApproval')) {
      result.add(R07ActivityAction.cancel);
    }
    if (entry.stage == 'confirmed' && independentlyInstalled) {
      result.add(R07ActivityAction.open);
    }
  } else if (entry.timeline != null) {
    if (entry.stage == 'queued') {
      result.add(R07ActivityAction.cancel);
      if (listingMatches && !liveDownload && entry.timeline!.intent.parentId == null &&
          const {'install', 'check', 'download'}.contains(entry.timeline!.intent.kind)) {
        result.add(R07ActivityAction.resume);
      }
    }
  } else if (entry.kind == 'live') {
    // Exact provider operation keyed by listing; never cancel by historical R03
    // filename. A different transfer might now own the same listing.
    if (listingMatches && liveDownload && entry.stage == 'downloading') {
      result.add(R07ActivityAction.cancel);
    }
  } else if (entry.kind == 'download') {
    if (!entry.archivedTransfer && listingMatches && !liveDownload && entry.download?.explicitlyResumable == true) {
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
  R07ActivityCatalog({this.testingRoot, R05OperationJournal? installJournal})
      : _installJournal = installJournal ?? R05OperationJournal.instance;

  final Directory? testingRoot;
  final R05OperationJournal _installJournal;
  Set<String> availableChannels = const {};
  // 4,096 legal SHA-256 chunk hashes alone can exceed 128 KiB.
  static const int maxDownloadReceiptBytes = R03DownloadHistory.maxReceiptBytes;
  static final RegExp _downloadFile = RegExp(r'^[a-f0-9]{64}\.json$');

  Future<List<R07ActivityRecord>> load({
    Map<String, String> trackedPackages = const <String, String>{},
    int? historyLimit, String? packageId, String? listingKey, String? operationId,
    String channel = 'all', String filter = 'all',
  }) async {
    final channels = <String>{};
    final active = <R07ActivityRecord>[], finished = <R07ActivityRecord>[];
    int compare(R07ActivityRecord a, R07ActivityRecord b) {
      final time = b.updatedUtc.compareTo(a.updatedUtc);
      return time == 0 ? a.id.compareTo(b.id) : time;
    }
    bool inScope(R07ActivityRecord row) =>
        (packageId == null || row.packageId == packageId) &&
        (listingKey == null || row.listingKey == listingKey) &&
        (operationId == null || row.id == operationId);
    String rowChannel(R07ActivityRecord row) => row.install?.channelFingerprint ??
        row.download?.historyBinding?.channel ?? row.timeline?.intent.channel ?? 'unknown';
    bool selected(R07ActivityRecord row) => inScope(row) &&
        (channel == 'all' || channel == rowChannel(row)) &&
        (filter == 'all' || (filter == 'review' && row.needsReview) || (filter == 'done' && row.isFinished));
    void append(R07ActivityRecord row) {
      if (row.kind == 'integrity') { active.add(row); return; }
      if (inScope(row)) { channels.add(rowChannel(row)); }
      if (!selected(row)) return;
      if (!row.isFinished) { active.add(row); return; }
      if (historyLimit == 0) return;
      finished.add(row);
      if (historyLimit != null) {
        finished.sort(compare);
        if (finished.length > historyLimit) { finished.removeLast(); }
      }
    }
    R07ActivityRecord installRow(R05OperationReceipt attempt, {bool integrity = true, bool unique = false}) =>
        R07ActivityRecord(id: 'install:${attempt.id}', kind: 'install',
          stage: attempt.stage == R05InstallStage.confirmed && !attempt.exactBytesConfirmed
              ? 'unknown' : attempt.stage.name, title: attempt.packageId,
          listingKey: attempt.listingKey, packageId: attempt.packageId,
          sourceHost: attempt.sourceHost, reason: attempt.reason,
          updatedUtc: attempt.updatedUtc, install: attempt,
          uniquePendingOwnership: unique, historyIntegrityKnown: integrity);
    // Read-only projection must not change a live attempt into unknown. Limit
    // terminal metadata before retaining it; live receipt counts are complete.
    final installRead = await _installJournal.readForActivity(historyLimit: historyLimit,
      includeFinished: (attempt) => selected(installRow(attempt)),
      observe: (attempt) {
        final row = installRow(attempt);
        if (inScope(row)) { channels.add(rowChannel(row)); }
      });
    final unresolvedCounts = <String, int>{};
    for (final attempt in installRead.receipts) {
      if (const {R05InstallStage.pending, R05InstallStage.awaitingApproval,
          R05InstallStage.handedOff, R05InstallStage.unknown}.contains(attempt.stage)) {
        unresolvedCounts.update(attempt.listingKey, (n) => n + 1, ifAbsent: () => 1);
      }
    }
    for (final attempt in installRead.receipts) {
      append(installRow(attempt, integrity: installRead.unreadableCount == 0,
        unique: installRead.unreadableCount == 0 && unresolvedCounts[attempt.listingKey] == 1));
    }
    if (installRead.unreadableCount != 0) {
      append(R07ActivityRecord(id: 'integrity:install', kind: 'integrity',
        stage: 'unknown', title: 'Unreadable installation history',
        reason: '${installRead.unreadableCount} receipt(s) could not be read; no evidence was erased.',
        updatedUtc: DateTime.now().toUtc(), historyIntegrityKnown: false));
    }
    final root = testingRoot ?? await getApplicationSupportDirectory();
    try {
      final timeline = R07OperationTimeline(testingRoot: root);
      if (operationId == null || operationId.startsWith('timeline:')) {
        final page = await timeline.readForActivity(historyLimit: historyLimit,
          packageId: packageId, listingKey: listingKey,
          operationId: operationId?.substring('timeline:'.length), channel: channel, filter: filter);
        channels.addAll(page.channels);
        for (final row in page.rows) {
          final count = page.batches[row.batchId];
          append(R07ActivityRecord(id: 'timeline:${row.id}', kind: 'timeline',
            stage: row.stage, title: row.intent.packageId, listingKey: row.intent.listingKey,
            packageId: row.intent.packageId, updatedUtc: row.updatedUtc, reason: row.reason,
            timeline: row, batchCompleted: count?.completed, batchTotal: count?.total));
        }
        if (page.unreadableCount != 0) {
          append(R07ActivityRecord(id: 'integrity:timeline', kind: 'integrity',
            stage: 'unknown', title: 'Unreadable operation history',
            reason: '${page.unreadableCount} timeline record(s) could not be read.',
            updatedUtc: DateTime.now().toUtc(), historyIntegrityKnown: false));
        }
      }
    } catch (_) {
      append(R07ActivityRecord(id: 'integrity:timeline', kind: 'integrity',
        stage: 'unknown', title: 'Operation timeline could not be read',
        updatedUtc: DateTime.now().toUtc(), historyIntegrityKnown: false));
    }
    final folder = Directory('${root.path}/r03-download-journal');
    // Recovery and historical namespaces are read independently. Unreadable
    // history does not remove independently readable live entries.
    var unreadableDownloads = 0;
    for (final archived in [false, true]) {
      final directory = archived ? R03DownloadHistory.archiveOf(folder) : folder;
      try {
        await R03DownloadHistory.verifyDirectory(directory);
      } on FileSystemException {
        unreadableDownloads++;
        continue;
      }
      if (!await directory.exists()) continue;
      await for (final entity in directory.list(followLinks: false)) {
        try {
          final name = entity.uri.pathSegments.last;
          if (!archived && name.endsWith('.json.tmp') && _downloadFile.hasMatch(name.substring(0, name.length - 4))) {
            if (await FileSystemEntity.type(entity.path, followLinks: false) != FileSystemEntityType.file) {
              throw const FormatException('Unsafe R03 staging file');
            }
            continue;
          }
          if (entity is! File || !(archived ? R03DownloadHistory.archivedName : _downloadFile).hasMatch(name)) {
            throw const FormatException('Unknown transfer history entry');
          }
          final transfer = await R03DownloadHistory.readRecord(entity, archived: archived);
          if (archived && !const {R03Stage.ready, R03Stage.completed, R03Stage.failed, R03Stage.cancelled}.contains(transfer.stage)) {
            throw const FormatException('Unresolved transfer in historical archive');
          }
      final historicalOwner = transfer.historyBinding;
      final listing = historicalOwner?.listingKey ?? r07UniqueListingForFile(
          transfer.fileName, trackedPackages.keys);
      final complete = transfer.finalDigest != null &&
          RegExp(r'^[a-f0-9]{64}$').hasMatch(transfer.finalDigest!) &&
          transfer.completedBytes == transfer.totalBytes &&
          (transfer.stage == R03Stage.ready ||
              transfer.stage == R03Stage.completed);
      final amount = complete ? transfer.completedBytes : transfer.validatedBytes;
      final stat = await entity.stat();
      append(R07ActivityRecord(
        id: archived ? 'download-history:$name' : 'download:${transfer.jobId}', kind: 'download',
        archivedTransfer: archived,
        stage: transfer.stage.name,
        title: listing == null ? transfer.fileName :
            (trackedPackages[listing] ?? transfer.fileName),
        listingKey: listing,
        packageId: historicalOwner?.packageId ?? (listing == null ? null : trackedPackages[listing]),
        sourceHost: transfer.origin,
        updatedUtc: stat.modified.toUtc(),
        verifiedBytes: amount, totalBytes: transfer.totalBytes,
        download: transfer,
      ));
      } on FileSystemException {
        unreadableDownloads++;
      } on FormatException {
        unreadableDownloads++;
      } on TypeError {
        unreadableDownloads++;
      }
    }
    }
    if (unreadableDownloads != 0) {
      append(R07ActivityRecord(id: 'integrity:download', kind: 'integrity',
        stage: 'unknown', title: 'Unreadable download history',
        reason: '$unreadableDownloads receipt(s) could not be read; no evidence was erased.',
        updatedUtc: DateTime.now().toUtc(), historyIntegrityKnown: false));
    }
    availableChannels = Set<String>.unmodifiable(channels);
    return List<R07ActivityRecord>.unmodifiable(<R07ActivityRecord>[...active, ...finished]..sort(compare));
  }
}
