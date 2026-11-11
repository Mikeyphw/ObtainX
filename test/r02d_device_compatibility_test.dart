import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/services/install_bundle_plan.dart';

const root = '/stage/ox-verified';
const pkg = 'org.example.demo';
const base = InstallApkMember(
  path: '$root/base.apk', packageName: pkg, versionCode: 22,
  minSdkVersion: 26, targetSdkVersion: 35,
);

InstallApkMember split(String name) => InstallApkMember(
  path: '$root/$name', packageName: pkg, versionCode: 22,
);

InstallBundlePlan plan(List<InstallApkMember> files, {
  List<String> locales = const <String>[],
  int? dpi,
  List<String> abis = const ['arm64-v8a', 'armeabi-v7a'],
}) => resolveInstallBundlePlan(
  members: files,
  format: InstallArtifactFormat.apks,
  supportedAbis: abis,
  expectedPackageName: pkg,
  deviceSdkVersion: 36,
  deviceLocales: locales,
  deviceDensityDpi: dpi,
);

void main() {
  test('RT02D selects ARM64, best locale and nearest matching density', () {
    final items = [
      split('config.en.apk'), split('config.xxhdpi.apk'),
      split('config.fr.apk'), split('config.hdpi.apk'),
      split('config.arm64_v8a.apk'), split('config.armeabi_v7a.apk'), base,
    ];
    final selected = plan(items, locales: ['fr-CA', 'en-US'], dpi: 420);
    expect(selected.sessionPaths, [
      base.path, '$root/config.arm64_v8a.apk',
      '$root/config.en.apk', '$root/config.fr.apk', '$root/config.xxhdpi.apk',
    ]);
    expect(selected.sessionPaths, isNot(contains('$root/config.hdpi.apk')));
    expect(selected.sessionPaths, isNot(contains('$root/config.armeabi_v7a.apk')));
  });

  test('RT02D refuses ambiguous locale without device evidence', () {
    expect(() => plan([base, split('config.en.apk'), split('config.fr.apk')]),
        throwsFormatException);
  });

  test('RT02D refuses ambiguous density without device evidence', () {
    expect(() => plan([base, split('config.xhdpi.apk'), split('config.xxhdpi.apk')]),
        throwsFormatException);
  });

  test('RT02D picks exact region before language-only fallback', () {
    final selected = plan([
      base, split('config.en.apk'), split('config.en-rUS.apk'),
      split('config.fr.apk'),
    ], locales: ['en-US']);
    expect(selected.sessionPaths, [base.path, '$root/config.en-rUS.apk']);
  });

  test('RT02D chooses language fallback if exact region unavailable', () {
    final selected = plan([
      base, split('config.fr.apk'), split('config.en.apk'),
    ], locales: ['en-US']);
    expect(selected.sessionPaths, [base.path, '$root/config.en.apk']);
  });

  test('RT02D includes all matching configured device languages', () {
    final selected = plan([
      base, split('config.en.apk'), split('config.fr.apk'),
      split('config.de.apk'),
    ], locales: ['fr-CA', 'en-US']);
    expect(selected.sessionPaths, [
      base.path, '$root/config.en.apk', '$root/config.fr.apk',
    ]);
  });

  test('RT02D refuses incompatible selected language', () {
    expect(() => plan([base, split('config.fr.apk'), split('config.en.apk')],
        locales: ['ja-JP']), throwsFormatException);
  });

  test('RT02D refuses invalid density and multiple identical density roles', () {
    expect(() => plan([base], dpi: -1), throwsFormatException);
    expect(() => plan([base, split('config.hdpi.apk'),
          split('split_config.hdpi.apk')], dpi: 240), throwsFormatException);
  });

  test('RT02D preserves all neutral splits and base identity', () {
    final selected = plan([
      split('config.anydpi.apk'), split('config.nodpi.apk'),
      split('config.arm64_v8a.apk'), base,
    ], locales: ['en-US'], dpi: 320);
    expect(selected.sessionPaths, [
      base.path, '$root/config.anydpi.apk',
      '$root/config.arm64_v8a.apk', '$root/config.nodpi.apk',
    ]);
  });

  test('RT02D staged OBB paths cannot escape extraction root', () {
    final valid = [
      '$root/Android/obb/$pkg/main.22.$pkg.obb',
      '$root/Android/obb/$pkg/patch.22.$pkg.obb',
    ];
    expect(() => validateStagedObbPaths(valid, pkg, extractionRoot: root),
        returnsNormally);
    for (final bad in [
      '$root/../other/main.22.$pkg.obb',
      '/stage/ox-verified-other/main.22.$pkg.obb',
      '$root//main.22.$pkg.obb',
      '$root/./main.22.$pkg.obb',
      '$root\\main.22.$pkg.obb',
      '/outside/main.22.$pkg.obb',
      '$root/main.22.org.other.app.obb',
    ]) {
      expect(() => validateStagedObbPaths([bad], pkg, extractionRoot: root),
          throwsFormatException, reason: bad);
    }
  });

  test('RT02D refuses broad or relative OBB staging roots', () {
    for (final rootPath in ['/', '.', 'stage/data', '/stage/../trusted']) {
      expect(() => validateStagedObbPaths(
        ['$root/main.22.$pkg.obb'], pkg, extractionRoot: rootPath,
      ), throwsFormatException);
    }
  });
}
