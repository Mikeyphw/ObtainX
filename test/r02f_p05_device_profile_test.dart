import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/services/install_bundle_plan.dart';
import 'package:obtainium/services/r02f_p05_device_profile.dart';

const String packageId = 'org.example.p05';
const InstallApkMember baseMember = InstallApkMember(
  path: '/tmp/p05/base.apk', packageName: packageId, versionCode: 5,
  minSdkVersion: 26, targetSdkVersion: 35,
);

InstallApkMember config(String qualifier, {int? sdk, int? target}) =>
    InstallApkMember(path: '/tmp/p05/config.$qualifier.apk',
      packageName: packageId, versionCode: 5,
      minSdkVersion: sdk, targetSdkVersion: target);

void main() {
  test('P05 actual RT02D planner selects ARM64 region and nearest density', () {
    final members = [baseMember, config('x86'), config('arm64_v8a'),
      config('en'), config('en-rUS'), config('xhdpi'), config('xxhdpi')];
    validateP05DeviceProfile(sdk: 36, supportedAbis: ['arm64-v8a', 'x86'],
      locales: ['en-US'], densityDpi: 420);
    final plan = resolveInstallBundlePlan(members: members,
      format: InstallArtifactFormat.apks,
      supportedAbis: ['arm64-v8a', 'x86'],
      deviceLocales: ['en-US'], deviceDensityDpi: 420,
      deviceSdkVersion: 36, expectedPackageName: packageId);
    verifyP05SdkEnvelope(plan: plan, members: members, deviceSdk: 36);
    expect(plan.sessionPaths, contains('/tmp/p05/config.arm64_v8a.apk'));
    expect(plan.sessionPaths, contains('/tmp/p05/config.en-rUS.apk'));
    expect(plan.sessionPaths, contains('/tmp/p05/config.xxhdpi.apk'));
    expect(plan.sessionPaths, isNot(contains('/tmp/p05/config.x86.apk')));
  });
  test('P05 refuses empty, duplicate, malformed ABI evidence', () {
    for (final abis in [<String>[], ['arm64-v8a', 'arm64-v8a'], ['arm64-v8a;rm']]) {
      expect(() => validateP05DeviceProfile(sdk: 36,
        supportedAbis: abis, locales: ['en-US'], densityDpi: 420),
        throwsFormatException);
    }
  });
  test('P05 refuses invalid SDK density and locale inputs', () {
    for (final sdk in [0, 101]) {
      expect(() => validateP05DeviceProfile(sdk: sdk,
        supportedAbis: ['arm64-v8a'], locales: ['en-US'], densityDpi: 420),
        throwsFormatException);
    }
    for (final dpi in [0, 2001]) {
      expect(() => validateP05DeviceProfile(sdk: 36,
        supportedAbis: ['arm64-v8a'], locales: ['en-US'], densityDpi: dpi),
        throwsFormatException);
    }
    for (final locales in [<String>['en-US', 'en-US'], ['../etc/passwd']]) {
      expect(() => validateP05DeviceProfile(sdk: 36,
        supportedAbis: ['arm64-v8a'], locales: locales, densityDpi: 420),
        throwsFormatException);
    }
  });
  test('P05 rejects incompatible base or split SDK without approval', () {
    final members = [baseMember, config('arm64_v8a')];
    final plan = resolveInstallBundlePlan(members: members,
      format: InstallArtifactFormat.apks,
      supportedAbis: ['arm64-v8a'], deviceSdkVersion: 36);
    verifyP05SdkEnvelope(plan: plan, members: members, deviceSdk: 36);
    expect(() => verifyP05SdkEnvelope(plan: plan,
      members: [baseMember, config('arm64_v8a', sdk: 99)], deviceSdk: 36),
      throwsFormatException);
    expect(() => verifyP05SdkEnvelope(plan: plan,
      members: [baseMember, config('arm64_v8a', target: 34)], deviceSdk: 36),
      throwsFormatException);
    expect(() => verifyP05SdkEnvelope(plan: plan,
      members: [baseMember], deviceSdk: 36), throwsFormatException);
  });
  test('P05 refuses Android 11+ direct OBB regardless of permission', () {
    for (final sdk in [30, 35, 36]) {
      expect(p05DirectObbDeliveryEligible(androidSdk: sdk, hasObb: true,
        externalContainerHandoff: false, storagePermissionGranted: true), false);
    }
  });
  test('P05 allows only eligible pre-R direct OBB path', () {
    expect(p05DirectObbDeliveryEligible(androidSdk: 29, hasObb: true,
      externalContainerHandoff: false, storagePermissionGranted: true), true);
    expect(p05DirectObbDeliveryEligible(androidSdk: 29, hasObb: true,
      externalContainerHandoff: false, storagePermissionGranted: false), false);
    expect(p05DirectObbDeliveryEligible(androidSdk: 29, hasObb: true,
      externalContainerHandoff: true, storagePermissionGranted: true), false);
    expect(p05DirectObbDeliveryEligible(androidSdk: 29, hasObb: false,
      externalContainerHandoff: false, storagePermissionGranted: true), false);
  });
}
