// Hosted API36 only: production native ACTION_VIEW to disposable external
// PackageInstaller target. Broadcast boolean is never an install confirmation.
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:obtainium/providers/installer_provider.dart';
import 'package:obtainium/services/third_party_install_evidence.dart';
import 'package:path_provider/path_provider.dart';

const _sha = String.fromEnvironment('OX_P04B_P02_BASE_SHA');
const _fixture = 'dev.bikram.obtainx.rt02.fixture';
const _target = 'dev.bikram.obtainx.p04b.positive';
const _component = 'dev.bikram.obtainx.p04b.positive.PositiveInstallActivity';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('external installer user-approved update stays unverified in Dart', (tester) async {
    if (!Platform.isAndroid || !RegExp(r'^[a-f0-9]{64}$').hasMatch(_sha)) {
      throw StateError('Hosted real Android and SHA-bound fixture required');
    }
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: Text('P04B CI'))));
    final temporary = await getTemporaryDirectory();
    final file = File('${temporary.path}/p04b-p02-${DateTime.now().microsecondsSinceEpoch}.apk');
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 15);
    try {
      final request = await client.getUrl(Uri.parse('http://127.0.0.1:18784/base_v2.apk'));
      final response = await request.close().timeout(const Duration(seconds: 25));
      if (response.statusCode != 200) throw StateError('Signed fixture HTTP refused');
      final bytes = await response.fold<List<int>>([], (result,part) => result..addAll(part));
      if (bytes.length < 300 || bytes.length > 16*1024*1024 ||
          sha256.convert(bytes).toString() != _sha) {
        throw StateError('Signed disposable v2 bytes untrusted');
      }
      await file.writeAsBytes(bytes, flush: true);
      debugPrint('OX_P04B_P02_REAL_EXTERNAL_HANDOFF_STARTED');
      final bridge = await installApkViaThirdParty(
        file.path,
        targetPackage: _target,
        targetActivity: _component,
        expectedPackageName: _fixture,
      ).timeout(const Duration(seconds: 150));
      // Even a real PACKAGE_REPLACED callback is insufficient to prove exact
      // signed bytes. Hosted Python must independently inspect PackageManager.
      final result = classifyUnverifiedThirdPartyHandoff(bridge);
      expect(result.isHandedOff, isTrue);
      expect(result.isSuccess, isFalse);
      expect(result.isCancelled, isFalse);
      debugPrint('OX_P04B_P02_REAL_EXTERNAL_BRIDGE_NO_FALSE_SUCCESS_PASS');
    } finally {
      client.close(force: true);
      if (file.existsSync()) await file.delete();
    }
  });
}
