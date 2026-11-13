// Real hosted API36 app-page -> AppsProvider.installApk -> stock PackageInstaller.
// This is NOT a bare Cancel button harness and never uses adb install-abandon.
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:easy_localization/easy_localization.dart';
import 'package:easy_localization/src/localization.dart';
import 'package:easy_localization/src/translations.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:obtainium/installers/r02f_p03_cancellable_stock.dart';
import 'package:obtainium/pages/app.dart';
import 'package:obtainium/providers/apps_provider.dart';
import 'package:obtainium/providers/source_provider.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';

const _pkg = 'dev.bikram.obtainx.rt02.fixture';
const _baseSha = String.fromEnvironment('OX_P03_BASE_SHA');
const _splitSha = String.fromEnvironment('OX_P03_SPLIT_SHA');
const _port = 18782;

Future<File> _download(String name, String expectedSha, Directory dir) async {
  if (!RegExp(r'^[a-f0-9]{64}$').hasMatch(expectedSha)) {
    throw StateError('P03 fixture SHA256 missing');
  }
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 12);
  try {
    final request = await client.getUrl(Uri.parse('http://127.0.0.1:$_port/fixtures/$name'));
    final response = await request.close().timeout(const Duration(seconds: 20));
    if (response.statusCode != HttpStatus.ok) {
      throw StateError('P03 fixture HTTP refused');
    }
    final bytes = await response.fold<List<int>>([], (acc, next) => acc..addAll(next));
    if (bytes.length < 1000 || bytes.length > 16 * 1024 * 1024 ||
        sha256.convert(bytes).toString() != expectedSha) {
      throw StateError('P03 source-bound APK integrity failed');
    }
    final file = File('${dir.path}/$name');
    await file.writeAsBytes(bytes, flush: true);
    return file;
  } finally {
    client.close(force: true);
  }
}

Future<void> _requestForeground() async {
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 15);
  try {
    final request = await client.postUrl(Uri.parse('http://127.0.0.1:$_port/p03/foreground'));
    request.contentLength = 0;
    final response = await request.close().timeout(const Duration(seconds: 25));
    final body = await utf8.decoder.bind(response).join();
    if (response.statusCode != 200 || body != 'foreground_ready') {
      throw StateError('Host did not verify approval screen before ObtainX foreground');
    }
  } finally {
    client.close(force: true);
  }
}

Future<Map<String, dynamic>> _waitForApproval() async {
  final deadline = DateTime.now().add(const Duration(seconds: 110));
  while (DateTime.now().isBefore(deadline)) {
    final pending = await R02fP03CancellableStock.instance.pending();
    if (pending != null && pending['packageName'] == _pkg &&
        pending['state'] == 'approval' && pending['sessionExists'] == true) {
      return pending;
    }
    await Future<void>.delayed(const Duration(milliseconds: 400));
  }
  throw StateError('P03 owned session never reached Android pending user approval');
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('production AppPage Cancel abandons owned pending Android install', (tester) async {
    if (!Platform.isAndroid) throw StateError('Real Android required');
    final root = await getTemporaryDirectory();
    final dir = await Directory('${root.path}/p03-${DateTime.now().microsecondsSinceEpoch}')
        .create(recursive: true);
    final provider = AppsProvider();
    try {
      await provider.waitForInitialLoad();
      if (provider.initError != null) {
        throw StateError('ObtainX app provider initialization refused: ${provider.initError}');
      }
      final settings = provider.settingsProvider;
      final translations = await const RootBundleAssetLoader().load(
        'assets/translations', const Locale('en'),
      );
      if (translations == null) throw StateError('App translations unavailable');
      Localization.load(const Locale('en'), translations: Translations(translations));
      final icon = (await rootBundle.load('assets/graphics/logo_remember.png'))
          .buffer.asUint8List();
      final base = await _download('base_v2.apk', _baseSha, dir);
      final split = await _download('config.x86_64.apk', _splitSha, dir);
      const app = App(
        id: _pkg,
        url: 'https://github.com/example/obtainx-r02f-p03-disposable-fixture',
        author: 'ObtainX CI fixture',
        name: 'ObtainX RT02 Fixture',
        installedVersion: '1',
        latestVersion: '2',
        apkUrls: const [MapEntry('base_v2.apk', 'http://127.0.0.1:18782/fixtures/base_v2.apk')],
        preferredApkIndex: 0,
        additionalSettings: const {'versionDetection': 'auto'},
      );
      provider.apps[app.listingKey] = AppInMemory(
        app, -1, await getInstalledInfo(_pkg), icon,
      );
      final owner = provider.beginInstallPreparation(app.listingKey);
      await tester.pumpWidget(MultiProvider(
        providers: [
          ChangeNotifierProvider<AppsProvider>.value(value: provider),
          ChangeNotifierProvider.value(value: settings),
        ],
        child: MaterialApp(home: AppPage(appId: app.listingKey)),
      ));
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.byType(AppPage), findsOneWidget);
      final cancelKey = Key('p03-cancel-${app.listingKey}');
      expect(find.byKey(cancelKey), findsOneWidget,
          reason: 'Real AppPage must expose app-owned cancellation');
      // Route changes must not replace the exact listing cancellation owner.
      final navigator = tester.state<NavigatorState>(find.byType(Navigator));
      navigator.push(MaterialPageRoute<void>(builder: (_) =>
          const Scaffold(body: Center(child: Text('P03 route transition')))));
      await tester.pump(const Duration(milliseconds: 400));
      navigator.pop();
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.byType(AppPage), findsOneWidget);
      expect(find.byKey(cancelKey), findsOneWidget);
      expect(provider.canCancelInstallPreparation(app.listingKey), isTrue);
      debugPrint('OX_P03_DART_STAGE=APP_ROUTE_OWNER_SURVIVED');

      // Critical: invoke production AppsProvider.installApk, NOT a direct
      // StockInstaller call. Its real verification/pending-asset/rollback path
      // passes the owner token into the first-party native session.
      final install = provider.installApk(
        DownloadedApk(_pkg, base, release: InstallReleaseSnapshot.fromApp(app)),
        null,
        additionalAPKs: [DownloadedApk(_pkg, split)],
        skipMalwareScan: true,
        preparationGate: owner,
      );
      debugPrint('OX_P03_DART_STAGE=PRODUCTION_PROVIDER_INSTALL_STARTED');
      final native = await _waitForApproval();
      expect(native['listingKey'], app.listingKey);
      expect(native['sessionExists'], true);
      debugPrint('OX_P03_DART_STAGE=ANDROID_APPROVAL_PENDING');
      await _requestForeground();
      await tester.pump(const Duration(milliseconds: 600));
      expect(find.byType(AppPage), findsOneWidget);
      final realCancel = find.byKey(cancelKey);
      expect(realCancel, findsOneWidget,
          reason: 'Actual production AppPage lost its Cancel action');
      await tester.ensureVisible(realCancel);
      await tester.tap(realCancel);
      await tester.pump();
      debugPrint('OX_P03_DART_STAGE=REAL_APP_PAGE_CANCEL_TAPPED');
      expect(owner.wasCancelled, isTrue);
      final installed = await install.timeout(const Duration(seconds: 60));
      expect(installed, isFalse,
          reason: 'App provider cannot report a successful install after UI Cancel');
      final snapshot = await R02fP03CancellableStock.instance.snapshot();
      final terminal = snapshot['terminal'] as Map<String, dynamic>?;
      expect(terminal?['id'], native['id']);
      expect(terminal?['outcome'], 'cancelled',
          reason: 'Native abandon and original APK integrity must be established');
      debugPrint('OX_P03_DART_STAGE=APP_OWNED_CANCEL_RESULT_VERIFIED');
      provider.endInstallPreparation(app.listingKey, owner);
    } finally {
      await tester.pumpWidget(const SizedBox.shrink());
      provider.dispose();
      if (dir.existsSync()) await dir.delete(recursive: true);
    }
  });
}
