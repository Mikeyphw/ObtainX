import 'package:android_package_manager/android_package_manager.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/providers/apps_provider.dart';
import 'package:obtainium/installers/installer.dart';
import 'package:obtainium/providers/source_provider.dart';
import 'package:obtainium/services/third_party_install_evidence.dart';

class _Installed extends PackageInfo {
  _Installed(String packageName, String version, int versionCode)
      : super(
          installLocation: AndroidInstallLocation.unspecified,
          packageName: packageName,
          versionName: version,
          versionCode: versionCode,
        );
}

App _tracked({String source = 'https://example.invalid/first'}) => App(
      id: 'org.example.p04',
      url: source,
      author: 'P04 disposable test',
      name: 'P04 fixture',
      installedVersion: '1',
      latestVersion: '2',
      preferredApkIndex: 0,
      apkUrls: const [MapEntry('base.apk', 'https://example.invalid/base.apk')],
    );

void main() {
  final original = _tracked();
  final v2 = _Installed('org.example.p04', '2', 2);
  final pending = InstallReleaseSnapshot.fromApp(original).withPackage(v2);

  test('external bridge broadcast is NEVER standalone proof', () {
    for (final signal in [false, true]) {
      final handoff = classifyUnverifiedThirdPartyHandoff(signal);
      expect(handoff.isHandedOff, isTrue);
      expect(handoff.isSuccess, isFalse);
      expect(handoff.isCancelled, isFalse);
    }
  });

  test('exact release plus actual matching observed package is eligible', () {
    expect(p04PendingMatchesInstalledPackage(original, pending, v2), isTrue);
  });

  test('stale v1 package broadcast cannot confirm the requested v2', () {
    expect(
      p04PendingMatchesInstalledPackage(
        original, pending, _Installed('org.example.p04', '1', 1)),
      isFalse,
    );
  });

  test('same version number from another package cannot confirm', () {
    expect(
      p04PendingMatchesInstalledPackage(
        original, pending, _Installed('org.example.other', '2', 2)),
      isFalse,
    );
  });

  test('missing intent cannot be upgraded by a spurious broadcast', () {
    expect(p04PendingMatchesInstalledPackage(original, null, v2), isFalse);
  });

  test('source change invalidates the old pending receipt', () {
    expect(
      p04PendingMatchesInstalledPackage(
        _tracked(source: 'https://example.invalid/second'), pending, v2),
      isFalse,
    );
  });

  test('wrong versionCode even with same versionName is not a match', () {
    expect(
      p04PendingMatchesInstalledPackage(
        original, pending, _Installed('org.example.p04', '2', 3)),
      isFalse,
    );
  });

  test('stock result codes are distinct from external handoff', () {
    expect(InstallResult.fromPlatformCode(0).isSuccess, isTrue);
    expect(InstallResult.fromPlatformCode(null).isCancelled, isTrue);
    expect(InstallResult.fromPlatformCode(3).isAlreadyInstalled, isTrue);
    expect(InstallResult.fromPlatformCode(-1).isError, isTrue);
  });
}
