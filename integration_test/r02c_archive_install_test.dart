// RT02C API36 source-bound archive-to-StockInstaller acceptance.
// This is NOT the complete user-facing download/import/OBB experience.
import 'dart:async';
import 'dart:io';
import 'package:flutter/services.dart' show PlatformException, MissingPluginException;
import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:obtainium/installers/stock_installer.dart';
import 'package:obtainium/installers/r02f_p03_cancellable_stock.dart';
import 'package:obtainium/services/install_precommit_gate.dart';
import 'package:obtainium/providers/settings_provider.dart';
import 'package:obtainium/providers/apps_provider.dart';
import 'package:obtainium/services/artifact_file_work.dart';
import 'package:obtainium/services/install_bundle_plan.dart';
import 'package:obtainium/services/r09_artifact_inspection.dart';
import 'package:path_provider/path_provider.dart';

const packageName = 'dev.bikram.obtainx.rt02.fixture';
const controlToken = String.fromEnvironment('OX_R02C_CONTROL_TOKEN');
const scenarios = ['apks', 'apkm', 'xapk', 'zip', 'tar.gz', 'traversal', 'ambiguous'];
const baseSha = String.fromEnvironment('OX_R02C_BASE_SHA');
const splitSha = String.fromEnvironment('OX_R02C_SPLIT_SHA');
const v1Sha = String.fromEnvironment('OX_R02C_V1_SHA');
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

Future<Map<String, dynamic>> control(String route, String name, {String? result, int? sessionId}) async {
  if (!scenarios.contains(name) || controlToken.length != 48) {
    throw StateError('Unauthenticated RT02C boundary request');
  }
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 10);
  try {
    final request = await client.postUrl(Uri.parse('http://127.0.0.1:$fixturePort/rt02c/$route'));
    request.headers.contentType = ContentType.json;
    request.headers.set('X-RT02C-Token', controlToken);
    final body = <String, Object>{'case': name};
    if (sessionId != null) body['owned_session_id'] = sessionId;
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

// Use the same sealed, app-owned foreground StockInstaller handoff that
// AppsProvider uses for an explicitly initiated install. The legacy plugin
// requests silent install and delivers pending-action status via an Activity
// intent; this is not the foreground session contract used by the app.
Future<int> installOwnedArchive(String caseName, List<String> paths) async {
  final bridge = R02fP03CancellableStock.instance;
  final before = await bridge.snapshot().timeout(const Duration(seconds: 10));
  expect(before['active'], isNull, reason: 'No unresolved native session before install');
  final listing = 'rt02c:${sha256.convert(utf8.encode(controlToken))}:$caseName';
  final owner = InstallPrecommitGate(listing, scenarios.indexOf(caseName) + 1);
  expect(owner.sealForHandoff(nativeCancelable: true), isTrue);
  try {
    final result = await StockInstaller(SettingsProvider()).installApk(
        paths, appId: packageName,
        installOptions: {'r02fP03Gate': owner}).timeout(const Duration(seconds: 195));
    expect(result.isSuccess, isTrue,
        reason: 'Owned Android session must commit both signed members');
    final state = await bridge.snapshot().timeout(const Duration(seconds: 10));
    expect(state['active'], isNull, reason: 'Native session must have settled');
    final terminal = state['terminal'] as Map<String, dynamic>?;
    if (terminal == null) throw StateError('Native terminal receipt missing');
    expect(terminal['listingKey'], listing);
    expect(terminal['packageName'], packageName);
    expect(terminal['outcome'], 'success');
    expect(terminal['detail'], 'ANDROID_STATUS_0');
    expect(terminal['cancelRequested'], isFalse);
    final sessionId = terminal['sessionId'];
    if (sessionId is! int || sessionId <= 0) {
      throw StateError('Invalid native session identity');
    }
    expect(owner.isFinished, isTrue);
    final baseline = jsonDecode(terminal['baseline'] as String) as Map<String, dynamic>;
    final after = jsonDecode(terminal['after'] as String) as Map<String, dynamic>;
    expect(baseline['present'], isTrue);
    expect(baseline['versionCode'], 1);
    expect(baseline['baseSha256'], v1Sha);
    expect(baseline['splitSha256'], isEmpty);
    expect(after['present'], isTrue);
    expect(after['versionCode'], 2);
    expect(after['baseSha256'], baseSha);
    expect(after['splitSha256'], [splitSha]);
    return sessionId;
  } finally {
    // Keep diagnostics bounded: never expose the operation token, paths,
    // raw native journal or platform exception text to the hosted artifact.
    try {
      final state = await bridge.snapshot().timeout(const Duration(seconds: 5));
      final active = state['active'] as Map<String, dynamic>?;
      final terminal = state['terminal'] as Map<String, dynamic>?;
      const allowed = {'staged', 'committing', 'approval', 'cancel_uncertain'};
      final phase = active == null ? 'NO_ACTIVE_SESSION' :
          active['listingKey'] == listing && allowed.contains(active['state'])
          ? (active['state'] as String).toUpperCase() : 'UNVERIFIED_ACTIVE';
      const outcomes = {'success', 'cancelled', 'unknown', 'error'};
      final outcome = terminal != null && terminal['listingKey'] == listing &&
          outcomes.contains(terminal['outcome'])
          ? (terminal['outcome'] as String).toUpperCase() : 'NO_MATCHING_TERMINAL';
      debugPrint('OX_R02C_NATIVE_STATE=$phase TERMINAL=$outcome');
    } catch (_) {
      debugPrint('OX_R02C_NATIVE_STATE=UNAVAILABLE TERMINAL=UNAVAILABLE');
    }
  }
}

// Keep only fixed, source-defined diagnostics. Never print an exception's
// message, control token, URLs, file paths, or a raw stack trace into receipts.
String diagnosticCategory(Object error) {
  if (error is PlatformException) {
    const allowed = {'R09_APK_PATH_REFUSED', 'R09_APK_MANIFEST_REFUSED',
      'R09_APK_PLATFORM_METADATA_REFUSED', 'R09_APK_IDENTITY_MISMATCH',
      'R09_APK_SIGNERS_REFUSED', 'R09_APK_INSPECTION_REFUSED', 'PACKAGE_QUERY_FAILED'};
    return allowed.contains(error.code) ? error.code : 'PLATFORM_EXCEPTION';
  }
  if (error is MissingPluginException) return 'MISSING_PLUGIN';
  if (error is FormatException) return 'FORMAT_EXCEPTION';
  if (error is TimeoutException) return 'TIMEOUT';
  if (error is FileSystemException) return 'FILESYSTEM_EXCEPTION';
  if (error is StateError) return 'STATE_ERROR';
  if (error is TestFailure || error is AssertionError) return 'ASSERTION_FAILED';
  return 'OTHER_ERROR';
}

Future<int?> runScenario(String caseName, String archiveSha) async {
    debugPrintSynchronously('OX_R02C_DART_STAGE=SCENARIO_STARTED case=$caseName');
    var diagnosticStep = 'SCENARIO_SETUP';
    void mark(String step) {
      diagnosticStep = step;
      debugPrintSynchronously('OX_RT02C_CHECKPOINT case=$caseName step=$step');
    }
    Directory? scratch;
    var scenarioFailed = false;
    try {
      mark('SCENARIO_SETUP');
      final fileName = fixtureName(caseName);
      final temp = await Directory.systemTemp.createTemp('ox-rt02c-');
      scratch = temp;
      mark('DOWNLOAD_ARCHIVE');
      final input = await downloadVerifiedArchive(fileName, temp, archiveSha);
      mark('EXTRACT_ARCHIVE');
      final destination = '${temp.path}/extracted';
      if (caseName == 'traversal') {
        await expectLater(extractZipOffIsolate(input.path, destination, limits: limits),
            throwsA(isA<FormatException>()));
        expect(Directory(destination).existsSync(), isFalse,
            reason: 'Unsafe archive must never publish extraction');
        debugPrint('OX_R02C_DART_STAGE=PREINSTALL_REFUSED');
        return null;
      }
      if (caseName == 'tar.gz') {
        await extractTarballOffIsolate(input.path, destination, limits: limits);
      } else {
        await extractZipOffIsolate(input.path, destination, limits: limits);
      }
      mark('EXTRACTED_INVENTORY');
      final extracted = Directory(destination);
      expect(extracted.existsSync(), isTrue);
      final apkFiles = extracted.listSync(recursive: true, followLinks: false)
          .whereType<File>().where((file) => file.path.toLowerCase().endsWith('.apk')).toList()
        ..sort((a, b) => a.path.compareTo(b.path));
      expect(apkFiles.length, caseName == 'ambiguous' ? 3 : 2);
      mark('SIGNED_MEMBER_DIGESTS');
      final members = <InstallApkMember>[];
      for (final file in apkFiles) {
        final filename = file.uri.pathSegments.last;
        final isSplit = filename == 'config.x86_64.apk';
        final expected = isSplit ? splitSha : baseSha;
        final actual = await sha256.bind(file.openRead()).first;
        if (actual.toString() != expected) throw StateError('Extracted APK SHA256 mismatch');
        members.add(InstallApkMember(path: file.path, packageName: packageName,
          versionCode: 2, minSdkVersion: 26, targetSdkVersion: 35,
          splitName: isSplit ? 'config.x86_64' : null));
      }
      mark('BUNDLE_PLAN');
      if (caseName == 'ambiguous') {
        expect(() => resolveInstallBundlePlan(
          members: members, format: InstallArtifactFormat.apkm,
          supportedAbis: const ['x86_64'], deviceSdkVersion: 36,
          expectedPackageName: packageName), throwsA(isA<FormatException>()));
        debugPrint('OX_R02C_DART_STAGE=PREINSTALL_REFUSED');
        return null;
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
      if (caseName == 'apks') {
        mark('R09_STAGE');
        final stage = await (await getTemporaryDirectory()).createTemp('r09-review-');
        var reviewFailed = false;
        try {
          final inspected = <R09ApkFacts>[];
          for (final file in apkFiles) {
            final name = file.uri.pathSegments.last;
            final memberKind = name == 'config.x86_64.apk' ? 'SPLIT' : 'BASE';
            mark('R09_${memberKind}_COPY');
            final copy = await file.copy('${stage.path}/$name');
            mark('R09_${memberKind}_INSPECT');
            final facts = await inspectR09Apk(copy, name);
            mark('R09_${memberKind}_PACKAGE');
            expect(facts.packageName, packageName);
            mark('R09_${memberKind}_VERSION');
            expect(facts.versionCode, 2);
            mark('R09_${memberKind}_SDK');
            expect(facts.minSdk, 26);
            mark('R09_${memberKind}_DIGEST');
            expect(facts.sha256, name == 'config.x86_64.apk' ? splitSha : baseSha);
            mark('R09_${memberKind}_ROLE');
            expect(facts.split, name == 'config.x86_64.apk' ? 'config.x86_64' : null);
            inspected.add(facts);
          }
          mark('R09_BASE_SIGNERS');
          final baseFacts = inspected.singleWhere((member) => member.split == null);
          expect(baseFacts.signers, isNotEmpty);
          final splitFacts = inspected.singleWhere((member) => member.split != null);
          expect(splitFacts.signers, unorderedEquals(baseFacts.signers));
          mark('R09_INSTALLED_QUERY');
          final installed = await getInstalledInfo(packageName, light: false, printErr: false, throwOnError: true);
          mark('R09_INSTALLED_VERSION');
          expect(installed?.versionCode, 1);
          mark('R09_INSTALLED_SIGNERS');
          final installedSigners = certificateHashesFromSignatures(installed?.signingInfo?.apkContentSigners ?? const <List<int>>[])
              .map((value) => value.replaceAll(':', '').toLowerCase()).toList();
          expect(installedSigners, isNotEmpty);
          mark('R09_REVIEW_PLAN');
          final review = reviewR09Artifact(artifactSha256: archiveSha, bytes: await input.length(),
            members: inspected, format: InstallArtifactFormat.apks,
            supportedAbis: const ['x86_64'], sdk: 36, locales: const ['en-US'],
            density: 420, expectedPackage: packageName, installedSigners: installedSigners,
            installedPackageObserved: true, actionsDigestVerified: false);
          mark('R09_REVIEW_REFUSALS');
          const allowedRefusals = {'r09ReviewBaseRequired', 'r09ReviewSplitIdentity',
            'r09ReviewPackageMismatch', 'r09ReviewBundleRefused', 'r09ReviewSdkMismatch',
            'r09ReviewAbiMismatch', 'r09ReviewMissingSplits', 'r09ReviewSplitSignerMismatch',
            'r09ReviewSignerUnavailable', 'r09ReviewSignerDiffers'};
          for (final refusal in review.refusals) {
            final code = allowedRefusals.contains(refusal) ? refusal : 'UNKNOWN_REFUSAL';
            debugPrintSynchronously('OX_RT02C_REVIEW_REFUSAL case=$caseName code=$code');
          }
          expect(review.refusals, isEmpty);
          mark('R09_REVIEW_SIGNER_MATCH');
          expect(review.signerStatus, 'r09ReviewSignerMatches');
          mark('R09_REVIEW_SELECTION');
          expect(review.selectedPaths, hasLength(2));
          mark('R09_REVIEW_ELIGIBILITY');
          expect(review.eligible, isTrue);
          debugPrint('OX_R09_MANIFEST_REAL_APK_INSPECTION_PASS');
        } catch (_) {
          reviewFailed = true;
          rethrow;
        } finally {
          if (!reviewFailed) mark('R09_STAGE_CLEANUP');
          try {
            await stage.delete(recursive: true);
          } catch (_) {
            if (!reviewFailed) rethrow;
          }
        }
      }
      mark('HOST_INSTALL_AUTHORIZATION');
      final authorization = await control('call', caseName);
      expect(authorization['authorized'], isTrue);
      debugPrint('OX_R02C_DART_STAGE=INSTALL_CALL');
      mark('OWNED_INSTALL_SESSION');
      final sessionId = await installOwnedArchive(caseName, plan.sessionPaths);
      debugPrint('OX_R02C_DART_STAGE=INSTALL_RETURNED');
      return sessionId;
    } catch (error) {
      scenarioFailed = true;
      debugPrintSynchronously('OX_RT02C_FAILURE case=$caseName step=$diagnosticStep error=${diagnosticCategory(error)}');
      rethrow;
    } finally {
      try {
        if (!scenarioFailed) mark('SCENARIO_CLEANUP');
        if (scratch != null && scratch.existsSync()) await scratch.delete(recursive: true);
      } catch (error) {
        if (!scenarioFailed) {
          debugPrintSynchronously('OX_RT02C_FAILURE case=$caseName step=$diagnosticStep error=${diagnosticCategory(error)}');
          rethrow;
        }
      }
    }
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('RT02C seven real independently attested archive cases', (tester) async {
    if (!Platform.isAndroid) throw StateError('RT02C Android-only');
    expect(RegExp(r'^[a-f0-9]{64}$').hasMatch(v1Sha), isTrue);
    // Pairwise checks preserve uniqueness without constructing a set from
    // environment constants, whose defaults coincide during static analysis.
    expect(v1Sha, isNot(baseSha));
    expect(v1Sha, isNot(splitSha));
    expect(baseSha, isNot(splitSha));
    for (final name in scenarios) {
      final prepared = await control('prepare', name);
      if (prepared['case'] != name || prepared['archive_sha256'] is! String) {
        throw StateError('Host preparation receipt missing');
      }
      final sessionId = await runScenario(name, prepared['archive_sha256'] as String);
      final negative = name == 'traversal' || name == 'ambiguous';
      expect(sessionId == null, negative);
      final result = await control('finish', name,
          result: negative ? 'refused' : 'installed', sessionId: sessionId);
      if (result['verified'] != true) throw StateError('Android attestation missing');
    }
  }, timeout: const Timeout(Duration(minutes: 100)));
}
