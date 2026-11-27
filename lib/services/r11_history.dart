import 'dart:convert';
import 'package:crypto/crypto.dart';
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

Map<String, Object?> r11PublicHistory(List<R07ActivityRecord> records) => {
  'schema': 'obtainx.history.v1',
  'historicalOnly': true,
  'records': [for (final record in records)
    if (record.install != null) r11PublicReceipt(record.install!)
    else if (record.download != null) {
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
    } else if (record.timeline != null) {
      'kind': record.timeline!.intent.kind,
      'id': record.timeline!.id,
      'listing': r11HistoryKey(record.timeline!.intent.listingKey),
      'package': r11ValidPackage(record.timeline!.intent.packageId) ? record.timeline!.intent.packageId : null,
      'channel': record.timeline!.intent.channel,
      'releaseFingerprint': record.timeline!.intent.release,
      'stage': record.timeline!.stage,
      'parent': record.timeline!.intent.parentId,
      'transfer': record.timeline!.transferId,
      'attempt': record.timeline!.attemptId,
      'updatedUtc': record.updatedUtc.toIso8601String(),
    }
  ],
};
