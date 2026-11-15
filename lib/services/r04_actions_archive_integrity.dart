/// R04 P02: enforce the GitHub Actions ZIP's *own* published SHA-256 before
/// bounded archive extraction or any Android installer approval/session.
/// This is not an APK signing certificate or a build attestation.
library;

import 'dart:io';
import 'package:crypto/crypto.dart';

const String r04ActionsArchiveEvidenceKey = 'r04ActionsArchiveEvidence';

class R04ArchiveIntegrityFailure implements Exception {
  const R04ArchiveIntegrityFailure(this.reason);
  final String reason;
  @override
  String toString() => 'GitHub Actions archive integrity: $reason';
}

/// Binds the fetched release inventory to the exact file selected for install.
/// A previously cached ZIP or a changed source mode cannot bypass this gate.
Future<void> verifyR04ActionsArchiveBeforeExtraction({
  required File archive,
  required Map<String, dynamic> additionalSettings,
  required String sourceUrl,
  required String selectedAssetUrl,
  required String selectedAssetName,
}) async {
  if (additionalSettings['r04GitHubSourceMode'] != 'actions') {
    return; // Normal GitHub releases are governed by their existing gates.
  }
  final rawEvidence = additionalSettings[r04ActionsArchiveEvidenceKey];
  if (rawEvidence is! Map) {
    throw const R04ArchiveIntegrityFailure('missing source-bound archive receipt');
  }
  final digest = rawEvidence['archiveSha256'];
  final archiveUrl = rawEvidence['archiveUrl'];
  final artifactId = rawEvidence['artifactId'];
  final runId = rawEvidence['runId'];
  final runAttempt = rawEvidence['runAttempt'];
  final workflowId = rawEvidence['workflowId'];
  final commitSha = rawEvidence['commitSha'];
  final expected = digest is String ? digest.toLowerCase() : '';
  if (!RegExp(r'^[a-f0-9]{64}$').hasMatch(expected) ||
      rawEvidence['sourceUrl'] != sourceUrl ||
      rawEvidence['archiveName'] != selectedAssetName ||
      archiveUrl != selectedAssetUrl ||
      artifactId is! int || artifactId <= 0 ||
      runId is! int || runId <= 0 ||
      runAttempt is! int || runAttempt <= 0 ||
      workflowId is! int || workflowId <= 0 ||
      commitSha is! String ||
      !RegExp(r'^[a-f0-9]{40}$').hasMatch(commitSha)) {
    throw const R04ArchiveIntegrityFailure('stale or invalid archive receipt');
  }
  final canonical = Uri.tryParse(selectedAssetUrl);
  final source = Uri.tryParse(sourceUrl);
  if (canonical == null || source == null) {
    throw const R04ArchiveIntegrityFailure('malformed Actions artifact URL');
  }
  final expectedPath = RegExp(
    r'^/repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/actions/artifacts/([1-9][0-9]*)/zip$',
  );
  final match = expectedPath.firstMatch(canonical.path);
  final repoParts = source.pathSegments;
  if (source.scheme != 'https' || source.host != 'github.com' ||
      source.userInfo.isNotEmpty || source.hasPort ||
      source.hasQuery || source.hasFragment || repoParts.length != 2 ||
      canonical.scheme != 'https' || canonical.host != 'api.github.com' ||
      canonical.hasQuery || canonical.hasFragment ||
      canonical.userInfo.isNotEmpty || canonical.hasPort ||
      match == null || int.tryParse(match.group(1)!) != artifactId ||
      canonical.path !=
          '/repos/${repoParts[0]}/${repoParts[1]}/actions/artifacts/$artifactId/zip') {
    throw const R04ArchiveIntegrityFailure('noncanonical Actions artifact URL');
  }
  final entityType = await FileSystemEntity.type(archive.path, followLinks: false);
  if (entityType != FileSystemEntityType.file) {
    throw const R04ArchiveIntegrityFailure('archive is not a regular file');
  }
  // Stream the actual stored bytes. Never trust Content-Length, ETag, a cached
  // "download complete" status, or a directory/archive name as ZIP integrity.
  final actual = (await sha256.bind(archive.openRead()).first).toString();
  if (actual != expected) {
    // The caller owns this downloaded APK-cache file, not the original source.
    // Discard mismatching bytes so a later retry cannot reuse a poisoned cache.
    if (await FileSystemEntity.type(archive.path, followLinks: false) ==
        FileSystemEntityType.file) {
      await archive.delete();
    }
    throw const R04ArchiveIntegrityFailure('archive SHA-256 mismatch; discarded');
  }
}
