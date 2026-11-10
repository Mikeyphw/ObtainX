// RT02: Real Android PackageInstaller journey using ObtainX's production StockInstaller.
// Hosted disposable Android 16 emulator only. Never included in release builds.
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:obtainium/installers/stock_installer.dart';
import 'package:obtainium/providers/settings_provider.dart';
import 'package:obtainium/services/install_bundle_plan.dart';

const packageName = 'dev.bikram.obtainx.rt02.fixture';
const scenario = String.fromEnvironment('OX_R02_SCENARIO');
const baseSha = String.fromEnvironment('OX_R02_BASE_SHA');
const splitSha = String.fromEnvironment('OX_R02_SPLIT_SHA');
const fixturePort = 18782;

Future<File> fetchFixture(String name, String expected, Directory parent) async {
  if (!RegExp(r'^[0-9a-f]{64}$').hasMatch(expected)) {
    throw StateError('Missing exact fixture SHA256');
  }
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 10);
  try {
    final request = await client.getUrl(Uri.parse('http://127.0.0.1:$fixturePort/$name'));
    final response = await request.close().timeout(const Duration(seconds: 25));
    if (response.statusCode != HttpStatus.ok) throw StateError('Missing local fixture: $name');
    final data = await response.fold<List<int>>(<int>[], (out, chunk) => out..addAll(chunk));
    if (data.length < 250 || sha256.convert(data).toString() != expected) {
      throw StateError('Source-pinned fixture digest mismatch: $name');
    }
    final file = File('${parent.path}/${name == 'config.x86_64.apk' ? name : 'base.apk'}');
    await file.writeAsBytes(data, flush: true);
    return file;
  } finally {
    client.close(force: true);
  }
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('RT02 controlled APK session through ObtainX StockInstaller', (tester) async {
    if (!Platform.isAndroid) throw StateError('RT02 is Android-only');
    if (scenario != 'standalone' && scenario != 'split') {
      throw StateError('RT02 scenario not approved');
    }
    final temporary = await Directory.systemTemp.createTemp('obtainx-rt02-');
    try {
      const version = scenario == 'standalone' ? 1 : 2;
      final base = await fetchFixture('base_v$version.apk', baseSha, temporary);
      final members = <InstallApkMember>[
        InstallApkMember(path:base.path, packageName:packageName, versionCode:version,
                         minSdkVersion:26, targetSdkVersion:35),
      ];
      if (scenario == 'split') {
        final split = await fetchFixture('config.x86_64.apk', splitSha, temporary);
        members.add(InstallApkMember(path:split.path, packageName:packageName,
                                     versionCode:2, minSdkVersion:26));
      }
      final plan = resolveInstallBundlePlan(
        members:members,
        format:scenario == 'standalone' ? InstallArtifactFormat.apk : InstallArtifactFormat.apks,
        supportedAbis:const ['x86_64'], deviceSdkVersion:36,
        expectedPackageName:packageName,
      );
      expect(plan.packageName, packageName);
      expect(plan.versionCode, version);
      expect(plan.sessionPaths.length, scenario == 'split' ? 2 : 1);
      expect(plan.requiresSplitSession, scenario == 'split');
      // Android's real system installer must confirm success; no mocked channels.
      final result = await StockInstaller(SettingsProvider()).installApk(
        plan.sessionPaths, appId:packageName,
      ).timeout(const Duration(minutes: 3));
      expect(result.isSuccess, isTrue,
        reason:'Real system PackageInstaller did not confirm installation');
    } finally {
      if (temporary.existsSync()) await temporary.delete(recursive: true);
    }
  });
}
