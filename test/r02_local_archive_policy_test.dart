import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/services/install_bundle_plan.dart';
import 'package:obtainium/services/r02_local_archive_policy.dart';

void main() {
  test('R02 recognizes all genuine local installable format families', () {
    final choices = <String, InstallArtifactFormat>{
      'example.apk': InstallArtifactFormat.apk,
      'example.xapk': InstallArtifactFormat.xapk,
      'example.apkm': InstallArtifactFormat.apkm,
      'example.apks': InstallArtifactFormat.apks,
      'example.zip': InstallArtifactFormat.zip,
      'example.tar.gz': InstallArtifactFormat.tarball,
      'example.tgz': InstallArtifactFormat.tarball,
      'example.tar.xz': InstallArtifactFormat.tarball,
    };
    for (final entry in choices.entries) {
      expect(classifyR02LocalArtifact(entry.key, 2048), entry.value);
    }
  });
  test('R02 refuses path, empty, unsupported and oversize local input', () {
    for (final name in ['', '../bad.apk', 'nested/file.apk',
      'oops\\file.apk', 'text.txt', 'example.jpg', '..apk']) {
      expect(() => classifyR02LocalArtifact(name, 2048), throwsFormatException);
    }
    for (final length in [0, -1, r02LocalArchiveMaximumBytes + 1]) {
      expect(() => classifyR02LocalArtifact('real.apk', length), throwsFormatException);
    }
  });
  test('R02 refuses unrelated, missing, ambiguous, declined and downgrade', () {
    for (final patch in <Map<String, Object?>>[
      {'expectedPackage': 'org.other'}, {'sourceListingCount': 0},
      {'sourceListingCount': 2}, {'reviewAccepted': false},
      {'requestedVersion': 1, 'installedVersion': 3},
    ]) {
      final data = <String, Object?>{
        'expectedPackage': 'org.example.app',
        'actualPackage': 'org.example.app',
        'sourceListingCount': 1,
        'requestedVersion': 2,
        'installedVersion': 1,
        'reviewAccepted': true,
        ...patch,
      };
      expect(() => verifyR02LocalTarget(
        expectedPackage: data['expectedPackage']! as String,
        actualPackage: data['actualPackage']! as String,
        sourceListingCount: data['sourceListingCount']! as int,
        requestedVersion: data['requestedVersion']! as int,
        installedVersion: data['installedVersion'] as int?,
        reviewAccepted: data['reviewAccepted']! as bool,
      ), throwsFormatException);
    }
  });
  test('R02 no success from callback, version-only or unavailable byte evidence', () {
    for (final ok in [false, true]) {
      for (final bytes in [false, true]) {
        final outcome = r02LocalObservedInstallConfirmed(
          installerReportedSuccess: ok,
          expectedPackage: 'org.example.app', expectedVersionCode: 2,
          observedPackage: 'org.example.app', observedVersionCode: 2,
          byteEvidenceQualified: bytes,
        );
        expect(outcome, ok && bytes);
      }
    }
    expect(r02LocalObservedInstallConfirmed(
      installerReportedSuccess: true,
      expectedPackage: 'org.example.app', expectedVersionCode: 2,
      observedPackage: 'org.other.app', observedVersionCode: 2,
      byteEvidenceQualified: true,
    ), isFalse);
  });
}
