// RT02C API36 source-bound archive-to-StockInstaller acceptance.
// This is NOT the complete user-facing download/import/OBB experience.
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:obtainium/installers/stock_installer.dart';
import 'package:obtainium/providers/settings_provider.dart';
import 'package:obtainium/services/artifact_file_work.dart';
import 'package:obtainium/services/install_bundle_plan.dart';

const packageName = 'dev.bikram.obtainx.rt02.fixture';
const caseName = String.fromEnvironment('OX_R02C_CASE');
const archiveSha = String.fromEnvironment('OX_R02C_ARCHIVE_SHA');
const baseSha = String.fromEnvironment('OX_R02C_BASE_SHA');
const splitSha = String.fromEnvironment('OX_R02C_SPLIT_SHA');
const fixturePort = 18782;

const limits = ArchiveExtractionLimits(
  maxArchiveBytes: 12 * 1024 * 1024,
  maxExpandedBytes: 24 * 1024 * 1024,
  maxEntryBytes: 10 * 1024 * 1024,
  maxEntries: 20,
  maxDepth: 4,
  maxPathLength: 256,
);

String fixtureName(String name) {
  switch (name) {
    case 'apks': return 'bundle.apks';
    case 'apkm': return 'bundle.apkm';
    case 'xapk': return 'bundle.xapk';
    case 'zip': return 'bundle.zip';
    case 'tar.gz': return 'bundle.tar.gz';
    case 'traversal': return 'blocked-traversal.apks';
    case 'ambiguous': return 'ambiguous-base.apkm';
    default: throw StateError('Unapproved RT02C case');
  }
}

Future<File> downloadVerifiedArchive(String fileName, Directory folder) async {
  if (![archiveSha, baseSha, splitSha].every(
    (value) => RegExp(r'^[a-f0-9]{64}$').hasMatch(value),
  )) {
    throw StateError('Missing source-bound archive/APK SHA256');
  }
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 10);
  try {
    final req = await client.getUrl(Uri.parse('http://127.0.0.1:$fixturePort/$fileName'));
    final response = await req.close().timeout(const Duration(seconds: 25));
    if (response.statusCode != HttpStatus.ok) throw StateError('CI archive unavailable');
    final bytes = await response.fold<List<int>>(<int>[], (out, chunk) => out..addAll(chunk));
    if (bytes.length < 500 || bytes.length > limits.maxArchiveBytes ||
        sha256.convert(bytes).toString() != archiveSha) {
      throw StateError('Source-pinned archive SHA256/size mismatch');
    }
    final result = File('${folder.path}/$fileName');
    await result.writeAsBytes(bytes, flush: true);
    return result;
  } finally {
    client.close(force: true);
  }
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('RT02C real archive extraction, planning and stock install', (tester) async {
    debugPrint('OX_R02C_DART_STAGE=SCENARIO_STARTED');
    if (!Platform.isAndroid) throw StateError('RT02C Android-only');
    final fileName = fixtureName(caseName);
    final temp = await Directory.systemTemp.createTemp('ox-rt02c-');
    try {
      final input = await downloadVerifiedArchive(fileName, temp);
      final destination = '${temp.path}/extracted';
      if (caseName == 'traversal') {
        await expectLater(extractZipOffIsolate(input.path, destination, limits: limits),
            throwsA(isA<FormatException>()));
        expect(Directory(destination).existsSync(), isFalse,
            reason: 'Unsafe archive must never publish extraction');
        debugPrint('OX_R02C_DART_STAGE=PREINSTALL_REFUSED');
        return;
      }
      if (caseName == 'tar.gz') {
        await extractTarballOffIsolate(input.path, destination, limits: limits);
      } else {
        await extractZipOffIsolate(input.path, destination, limits: limits);
      }
      final extracted = Directory(destination);
      expect(extracted.existsSync(), isTrue);
      final apkFiles = extracted.listSync(recursive: true, followLinks: false)
          .whereType<File>().where((file) => file.path.toLowerCase().endsWith('.apk')).toList()
        ..sort((a, b) => a.path.compareTo(b.path));
      expect(apkFiles.length, caseName == 'ambiguous' ? 3 : 2);
      final members = <InstallApkMember>[];
      for (final file in apkFiles) {
        final filename = file.uri.pathSegments.last;
        final isSplit = filename == 'config.x86_64.apk';
        final expected = isSplit ? splitSha : baseSha;
        final actual = await sha256.bind(file.openRead()).first;
        if (actual.toString() != expected) throw StateError('Extracted APK SHA256 mismatch');
        members.add(InstallApkMember(path: file.path, packageName: packageName,
          versionCode: 2, minSdkVersion: 26, targetSdkVersion: 35));
      }
      if (caseName == 'ambiguous') {
        expect(() => resolveInstallBundlePlan(
          members: members, format: InstallArtifactFormat.apkm,
          supportedAbis: const ['x86_64'], deviceSdkVersion: 36,
          expectedPackageName: packageName), throwsA(isA<FormatException>()));
        debugPrint('OX_R02C_DART_STAGE=PREINSTALL_REFUSED');
        return;
      }
      final format = installArtifactFormat(fileName);
      expect(format, isNotNull);
      final plan = resolveInstallBundlePlan(
        members: members, format: format!, supportedAbis: const ['x86_64'],
        deviceSdkVersion: 36, expectedPackageName: packageName);
      expect(plan.packageName, packageName);
      expect(plan.versionCode, 2);
      expect(plan.sessionPaths.length, 2);
      expect(plan.requiresSplitSession, isTrue);
      debugPrint('OX_R02C_DART_STAGE=INSTALL_CALL');
      final result = await StockInstaller(SettingsProvider()).installApk(
          plan.sessionPaths, appId: packageName).timeout(const Duration(minutes: 3));
      debugPrint('OX_R02C_DART_STAGE=INSTALL_RETURNED');
      expect(result.isSuccess, isTrue,
          reason: 'Android must commit both signed members as one session');
    } finally {
      if (temp.existsSync()) await temp.delete(recursive: true);
    }
  });
}
