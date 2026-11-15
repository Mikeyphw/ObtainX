/// R02 user-selected local package review. This policy never confirms installs:
/// only Android's observed package state may establish a completed result.
library;

import 'package:obtainium/services/install_bundle_plan.dart';

const int r02LocalArchiveMaximumBytes = 1024 * 1024 * 1024;

InstallArtifactFormat classifyR02LocalArtifact(String name, int length) {
  if (length < 1 || length > r02LocalArchiveMaximumBytes ||
      name.isEmpty || name.length > 255 || name.contains('/') ||
      name.contains('\\') || name.contains('..') || name.contains('\u0000')) {
    throw const FormatException('Untrusted local document name or size');
  }
  final format = installArtifactFormat(name);
  if (format == null) {
    throw const FormatException('Unsupported or non-installable local artifact');
  }
  return format;
}

/// A real local installation only proceeds for exactly one matching tracked
/// source listing, so no unrelated source's release may be attributed to it.
void verifyR02LocalTarget({
  required String expectedPackage,
  required String actualPackage,
  required int sourceListingCount,
  required int requestedVersion,
  required int? installedVersion,
  required bool reviewAccepted,
}) {
  if (!reviewAccepted || sourceListingCount != 1 ||
      expectedPackage != actualPackage ||
      !RegExp(r'^[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+$')
          .hasMatch(actualPackage) || requestedVersion < 0) {
    throw const FormatException('Local install requires exact tracked package and explicit review');
  }
  // Downgrades are never silently approved by this import path, even if a
  // privileged backend could theoretically perform one.
  if (installedVersion != null && requestedVersion < installedVersion) {
    throw const FormatException('Local downgrade requires separate verified flow');
  }
}

bool r02LocalObservedInstallConfirmed({
  required bool installerReportedSuccess,
  required String expectedPackage,
  required int expectedVersionCode,
  required String? observedPackage,
  required int? observedVersionCode,
  required bool byteEvidenceQualified,
}) => installerReportedSuccess && byteEvidenceQualified &&
    expectedPackage == observedPackage &&
    expectedVersionCode == observedVersionCode;
