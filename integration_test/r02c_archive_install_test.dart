// RT02C API36 source-bound archive-to-StockInstaller acceptance.
// This is NOT the complete user-facing download/import/OBB experience.
import 'dart:io';
import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:obtainium/installers/stock_installer.dart';
import 'package:obtainium/providers/settings_provider.dart';
import 'package:obtainium/services/artifact_file_work.dart';
import 'package:obtainium/services/install_bundle_plan.dart';

const packageName = 'dev.bikram.obtainx.rt02.fixture';
const controlToken = String.fromEnvironment('OX_R02C_CONTROL_TOKEN');
const scenarios = ['apks', 'apkm', 'xapk', 'zip', 'tar.gz', 'traversal', 'ambiguous'];
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

Future<File> downloadVerifiedArchive(String fileName, Directory folder, String archiveSha) async {
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

Future<Map<String, dynamic>> control(String route, String name, {String? result}) async {
  if (!scenarios.contains(name) || controlToken.length != 48) {
    throw StateError('Unauthenticated RT02C boundary request');
  }
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 10);
  try {
    final request = await client.postUrl(Uri.parse('http://127.0.0.1:$fixturePort/rt02c/$route'));
    request.headers.contentType = ContentType.json;
    request.headers.set('X-RT02C-Token', controlToken);
    final body = <String, String>{'case': name};
    if (result != null) {
      body['result'] = result;
    }
    // The hosted controller intentionally rejects unbounded/chunked POST bodies.
    // HttpClientRequest defaults contentLength to -1, so send exact UTF-8 bytes.
    final payload = utf8.encode(jsonEncode(body));
    request.contentLength = payload.length;
    request.add(payload);
    final response = await request.close().timeout(const Duration(minutes: 4));
    final text = await utf8.decoder.bind(response).join();
    if (response.statusCode != HttpStatus.ok) {
      throw StateError('Host refused the exact Android scenario boundary');
    }
    final decoded = jsonDecode(text);
    if (decoded is! Map<String, dynamic>) throw StateError('Invalid host receipt');
    return decoded;
  } finally {
    client.close(force: true);
  }
}

Future<void> runScenario(String caseName, String archiveSha) async {
    debugPrint('OX_R02C_DART_STAGE=SCENARIO_STARTED case=$caseName');
    final fileName = fixtureName(caseName);
    final temp = await Directory.systemTemp.createTemp('ox-rt02c-');
    try {
      final input = await downloadVerifiedArchive(fileName, temp, archiveSha);
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
      await control('call', caseName); // Authorize real installer only for positive cases.
      debugPrint('OX_R02C_DART_STAGE=INSTALL_CALL');
      final result = await StockInstaller(SettingsProvider()).installApk(
          plan.sessionPaths, appId: packageName).timeout(const Duration(minutes: 3));
      debugPrint('OX_R02C_DART_STAGE=INSTALL_RETURNED');
      expect(result.isSuccess, isTrue,
          reason: 'Android must commit both signed members as one session');
    } finally {
      if (temp.existsSync()) await temp.delete(recursive: true);
    }
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('RT02C seven real independently attested archive cases', (tester) async {
    if (!Platform.isAndroid) throw StateError('RT02C Android-only');
    for (final name in scenarios) {
      final prepared = await control('prepare', name);
      if (prepared['case'] != name || prepared['archive_sha256'] is! String) {
        throw StateError('Host preparation receipt missing');
      }
      await runScenario(name, prepared['archive_sha256'] as String);
      final result = await control('finish', name,
          result: name == 'traversal' || name == 'ambiguous' ? 'refused' : 'installed');
      if (result['verified'] != true) throw StateError('Android attestation missing');
    }
  }, timeout: const Timeout(Duration(minutes: 100)));
}
