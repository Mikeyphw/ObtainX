import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/services/install_bundle_plan.dart';

const base = InstallApkMember(
  path: '/work/apks/base.apk',
  packageName: 'org.example.demo',
  versionCode: 14,
  minSdkVersion: 26,
  targetSdkVersion: 35,
);

InstallApkMember config(String name, {String? package, int? version}) =>
    InstallApkMember(
      path: '/work/apks/$name',
      packageName: package,
      versionCode: version,
    );

InstallBundlePlan resolve(
  List<InstallApkMember> members, {
  InstallArtifactFormat format = InstallArtifactFormat.apks,
  List<String> abis = const ['arm64-v8a', 'armeabi-v7a'],
  String? expected = 'org.example.demo',
  int? sdk = 36,
}) => resolveInstallBundlePlan(
  members: members,
  format: format,
  supportedAbis: abis,
  expectedPackageName: expected,
  deviceSdkVersion: sdk,
);

void main() {
  test('detects standalone APK and all supported container suffixes', () {
    expect(installArtifactFormat('a.apk'), InstallArtifactFormat.apk);
    expect(installArtifactFormat('A.XAPK'), InstallArtifactFormat.xapk);
    expect(installArtifactFormat('release.APKM'), InstallArtifactFormat.apkm);
    expect(installArtifactFormat('release.apks'), InstallArtifactFormat.apks);
    expect(installArtifactFormat('archive.ZIP'), InstallArtifactFormat.zip);
    for (final name in [
      'release.tar', 'release.tar.gz', 'release.tgz',
      'release.tar.bz2', 'release.tar.xz',
    ]) {
      expect(installArtifactFormat(name), InstallArtifactFormat.tarball);
    }
    expect(installArtifactFormat('readme.txt'), isNull);
    expect(installArtifactFormat('bundle.apks.exe'), isNull);
  });

  test('standalone returns exactly one APK with metadata and no splits', () {
    final plan = resolve([base], format: InstallArtifactFormat.apk);
    expect(plan.sessionPaths, ['/work/apks/base.apk']);
    expect(plan.requiresSplitSession, isFalse);
    expect(plan.packageName, 'org.example.demo');
    expect(plan.versionCode, 14);
    expect(plan.minSdkVersion, 26);
    expect(plan.targetSdkVersion, 35);
    expect(() => plan.sessionPaths.add('evil.apk'), throwsUnsupportedError);
  });

  test('APKS, APKM, XAPK, ZIP and TAR preserve base plus all neutral splits', () {
    for (final kind in [
      InstallArtifactFormat.apks, InstallArtifactFormat.apkm,
      InstallArtifactFormat.xapk, InstallArtifactFormat.zip,
      InstallArtifactFormat.tarball,
    ]) {
      final plan = resolve([
        config('config.en.apk'),
        base,
        config('split_config.xxhdpi.apk'),
      ], format: kind);
      expect(plan.sessionPaths, [
        '/work/apks/base.apk',
        '/work/apks/config.en.apk',
        '/work/apks/split_config.xxhdpi.apk',
      ]);
      expect(plan.requiresSplitSession, isTrue);
    }
  });

  test('chooses preferred supported arm64 ABI while preserving language', () {
    final plan = resolve([
      config('split_config.armeabi_v7a.apk'),
      config('split_config.en.apk'),
      base,
      config('split_config.arm64_v8a.apk'),
    ]);
    expect(plan.sessionPaths, [
      base.path,
      '/work/apks/split_config.arm64_v8a.apk',
      '/work/apks/split_config.en.apk',
    ]);
    expect(plan.sessionPaths, isNot(contains('/work/apks/split_config.armeabi_v7a.apk')));
  });

  test('ABI fallback chooses armeabi-v7a when arm64 not supported', () {
    final plan = resolve([
      base,
      config('split_config.arm64_v8a.apk'),
      config('split_config.armeabi_v7a.apk'),
    ], abis: ['armeabi-v7a']);
    expect(plan.sessionPaths, [base.path, '/work/apks/split_config.armeabi_v7a.apk']);
  });

  test('x86_64 qualifier does not overlap with x86', () {
    final plan = resolve([
      base,
      config('config.x86_64.apk'),
      config('config.x86.apk'),
    ], abis: ['x86_64', 'x86']);
    expect(plan.sessionPaths, [base.path, '/work/apks/config.x86_64.apk']);
  });

  test('rejects no compatible ABI and no device ABI evidence', () {
    final files = [base, config('split_config.x86.apk')];
    expect(() => resolve(files), throwsFormatException);
    expect(() => resolve(files, abis: []), throwsFormatException);
  });

  test('rejects missing, duplicate and ambiguous base packages', () {
    expect(() => resolve([]), throwsFormatException);
    expect(() => resolve([config('config.en.apk')]), throwsFormatException);
    expect(() => resolve([
      base,
      const InstallApkMember(
        path: '/work/apks/other.apk', packageName: 'org.example.demo',
        versionCode: 14,
      ),
    ]), throwsFormatException);
  });

  test('rejects split set passed through standalone APK path', () {
    expect(
      () => resolve([base, config('config.en.apk')],
          format: InstallArtifactFormat.apk),
      throwsFormatException,
    );
  });

  test('rejects another package masquerading as config split', () {
    expect(() => resolve([base, config('config.en.apk', package: 'org.evil.app')]),
        throwsFormatException);
  });

  test('rejects split version mismatch', () {
    expect(() => resolve([base, config('config.en.apk', version: 15)]),
        throwsFormatException);
  });

  test('rejects unexpected base package ID before installer launch', () {
    expect(() => resolve([base], expected: 'org.example.other'), throwsFormatException);
  });

  test('allows package discovery before approved package ID migration', () {
    expect(resolve([base], expected: null).packageName, 'org.example.demo');
  });

  test('rejects APKs above the device minSdk', () {
    expect(() => resolve([base], sdk: 25), throwsFormatException);
    expect(() => resolve([
      base,
      const InstallApkMember(path: '/work/apks/config.en.apk',
          minSdkVersion: 37),
    ]), throwsFormatException);
  });

  test('rejects base missing package/version metadata', () {
    expect(() => resolve([
      const InstallApkMember(path: '/work/apks/base.apk', versionCode: 14),
    ]), throwsFormatException);
    expect(() => resolve([
      const InstallApkMember(path: '/work/apks/base.apk', packageName: 'org.example.demo'),
    ]), throwsFormatException);
  });

  test('rejects malformed package IDs and negative version code', () {
    expect(() => resolve([
      const InstallApkMember(path: '/work/apks/base.apk', packageName: '../evil',
          versionCode: 14),
    ], expected: null), throwsFormatException);
    expect(() => resolve([
      const InstallApkMember(path: '/work/apks/base.apk', packageName: 'org.example.demo',
          versionCode: -1),
    ]), throwsFormatException);
  });

  test('rejects non-APK, comma-delimited or newline member paths', () {
    for (final path in ['/work/a.zip', '/work/a,b.apk', '/work/a\nb.apk',
        '/work/a\\b.apk']) {
      expect(() => resolve([InstallApkMember(path: path,
          packageName: 'org.example.demo', versionCode: 14)]),
          throwsFormatException);
    }
  });

  test('rejects duplicate path and ambiguous duplicated basenames', () {
    expect(() => resolve([base, base]), throwsFormatException);
    expect(() => resolve([
      base,
      config('config.en.apk'),
      const InstallApkMember(path: '/work/other/CONFIG.EN.apk'),
    ]), throwsFormatException);
  });

  test('rejects multiple splits for the same ABI rather than guessing', () {
    expect(() => resolve([
      base, config('config.arm64_v8a.apk'),
      config('split_config.arm64_v8a.apk'),
    ]), throwsFormatException);
  });

  test('rejects unknown extra APK roles, even with a plausible package name', () {
    expect(() => resolve([
      base,
      const InstallApkMember(path: '/work/apks/feature_dashboard.apk',
          packageName: 'org.example.demo', versionCode: 14),
    ]), throwsFormatException);
  });

  test('file order cannot influence selected base or ABI', () {
    final set = [
      config('config.en.apk'), config('config.armeabi_v7a.apk'),
      base, config('config.arm64_v8a.apk'),
    ];
    final first = resolve(set).sessionPaths;
    final second = resolve(set.reversed.toList()).sessionPaths;
    expect(first, second);
  });

  test('OBB filenames bind to the selected package and unique expansion files', () {
    expect(() => validateObbFileNames([
      '/stage/Android/obb/org.example.demo/main.14.org.example.demo.obb',
      '/stage/Android/obb/org.example.demo/patch.14.org.example.demo.obb',
    ], 'org.example.demo'), returnsNormally);
    for (final bad in [
      'main.14.org.other.app.obb', 'something.14.org.example.demo.obb',
      'main.abc.org.example.demo.obb',
    ]) {
      expect(() => validateObbFileNames([bad], 'org.example.demo'),
          throwsFormatException);
    }
    expect(() => validateObbFileNames([
      'main.14.org.example.demo.obb',
      'MAIN.14.ORG.EXAMPLE.DEMO.OBB',
    ], 'org.example.demo'), throwsFormatException);
  });
}
