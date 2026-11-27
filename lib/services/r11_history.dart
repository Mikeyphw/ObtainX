import 'dart:convert';
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:obtainium/services/artifact_resource_budget.dart';
import 'package:obtainium/services/r05_operation_receipt.dart';
import 'package:obtainium/services/r07_activity_catalog.dart';
import 'package:obtainium/services/r11_external_requests.dart';

String r11HistoryKey(String key) => sha256.convert(utf8.encode(key)).toString();

Map<String, Object?> r11PublicReceipt(R05OperationReceipt receipt) => {
  'schema': 'obtainx.historical-receipt.v1',
  'historicalOnly': true,
  'id': receipt.id,
  'parentAttemptId': receipt.parentAttemptId,
  'timelineId': receipt.timelineId,
  'package': r11ValidPackage(receipt.packageId) ? receipt.packageId : null,
  'listing': r11HistoryKey(receipt.listingKey),
  'channel': receipt.channelFingerprint,
  'stage': receipt.stage.name,
  'createdUtc': receipt.createdUtc.toIso8601String(),
  'updatedUtc': receipt.updatedUtc.toIso8601String(),
  'verifiedUtc': receipt.exactBytesConfirmed ? receipt.verifiedUtc?.toIso8601String() : null,
  'exactBytesConfirmed': receipt.exactBytesConfirmed,
  'selectedApkSha256': receipt.selectedApkSha256,
  'archiveSignerSet': receipt.archiveSignerSet,
  'installedApkSha256': receipt.installedApkSha256,
  'installedSignerSet': receipt.installedSignerSet,
  'releaseFingerprint': receipt.releaseFingerprint,
  'containerSha256': receipt.containerSha256,
  'versionCode': receipt.androidVersionCode,
  'archiveSha256': receipt.downloadSha256,
  'archiveSignerSha256': receipt.archiveSignerSha256,
  'installedSignerSha256': receipt.installedSignerSha256,
};

Map<String, Object?>? r11PublicRecord(R07ActivityRecord record) {
  if (record.install != null) return r11PublicReceipt(record.install!);
  if (record.download != null) return {
      'kind': 'download',
      'id': r11HistoryKey(record.id),
      'listing': record.listingKey == null ? null : r11HistoryKey(record.listingKey!),
      'package': r11ValidPackage(record.packageId ?? '') ? record.packageId : null,
      'channel': record.download!.historyBinding?.channel,
      'releaseFingerprint': record.download!.historyBinding?.releaseFingerprint,
      'stage': record.download!.stage.name,
      'updatedUtc': record.updatedUtc.toIso8601String(),
      'verifiedBytes': record.verifiedBytes,
      'totalBytes': record.totalBytes,
      'digest': record.download!.finalDigest,
    };
    if (record.timeline != null) return {
      'kind': record.timeline!.intent.kind,
      'id': record.timeline!.id,
      'listing': record.timeline!.intent.channel == 'unknown' ? null : r11HistoryKey(record.timeline!.intent.listingKey),
      'package': r11ValidPackage(record.timeline!.intent.packageId) ? record.timeline!.intent.packageId : null,
      'channel': record.timeline!.intent.channel,
      'releaseFingerprint': record.timeline!.intent.release,
      'stage': record.timeline!.stage,
      'parent': record.timeline!.intent.parentId,
      'transfer': record.timeline!.transferId,
      'attempt': record.timeline!.attemptId,
      'updatedUtc': record.updatedUtc.toIso8601String(),
    };
    return null;
}

Map<String, Object?> r11PublicHistory(List<R07ActivityRecord> records) => {
  'schema': 'obtainx.history.v1', 'historicalOnly': true,
  'records': records.map(r11PublicRecord).whereType<Map<String, Object?>>().toList(),
};

/// Write incrementally to an exclusive private staging file, then atomically
/// publish only the completed document. Size is bounded independently of
/// history row count; callers may narrow scope if the export exceeds budget.
Future<File> writeR11PublicHistory(File destination,
    Future<void> Function(Future<void> Function(R07ActivityRecord)) visit,
    {int maxBytes = 256 * 1024 * 1024, void Function()? checkCancellation}) async {
  if (maxBytes < 1 || maxBytes > 256 * 1024 * 1024 ||
      await FileSystemEntity.type(destination.path, followLinks: false) != FileSystemEntityType.notFound) {
    throw const FileSystemException('Invalid history export destination or limit');
  }
  final part = File('${destination.path}.part');
  await part.create(exclusive: true);
  RandomAccessFile? output;
  var written = 0;
  var first = true;
  var published = false;
  try {
    final file = await part.open(mode: FileMode.write);
    output = file;
    var capacityCheckedAt = -1024 * 1024;
    Future<void> append(String text) async {
      checkCancellation?.call();
      final bytes = utf8.encode(text);
      if (bytes.length > maxBytes - written) throw const FileSystemException('History export exceeds limit');
      if (written - capacityCheckedAt >= 1024 * 1024) {
        await ensureArtifactStorageCapacity(destination.parent.path, 2 * 1024 * 1024);
        capacityCheckedAt = written;
      }
      await file.writeFrom(bytes);
      written += bytes.length;
    }
    await append('{"schema":"obtainx.history.v1","historicalOnly":true,"records":[');
    await visit((record) async {
      if (record.kind == 'integrity') throw const FormatException('Unreadable history');
      final value = r11PublicRecord(record);
      if (value == null) return;
      await append('${first ? '' : ','}${jsonEncode(value)}');
      first = false;
    });
    await append(']}');
    await file.flush();
    await file.close();
    output = null;
    checkCancellation?.call();
    await part.rename(destination.path);
    published = true;
    return destination;
  } finally {
    try { await output?.close(); } finally {
      if (!published && await part.exists()) await part.delete();
    }
  }
}
