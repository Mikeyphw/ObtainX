// P04B: production native external ACTION_VIEW -> disposable Android target.
// This deliberately tests an UNVERIFIED/DISMISSED handoff, not install success.
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:obtainium/providers/installer_provider.dart';
import 'package:obtainium/services/third_party_install_evidence.dart';
import 'package:path_provider/path_provider.dart';

const _expectedSha = String.fromEnvironment('OX_P04B_BASE_SHA');
const _package = 'dev.bikram.obtainx.rt02.fixture';
const _targetPackage = 'dev.bikram.obtainx.p04b.target';
const _targetActivity = 'dev.bikram.obtainx.p04b.target.DeclineActivity';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('real external receiver declines APK, no false confirmation', (tester) async {
    if (!Platform.isAndroid || !RegExp(r'^[0-9a-f]{64}$').hasMatch(_expectedSha)) {
      throw StateError('P04B real Android or source-bound APK SHA missing');
    }
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: Text('P04B'))));
    final dir = await getTemporaryDirectory();
    final file = File('${dir.path}/p04b-${DateTime.now().microsecondsSinceEpoch}.apk');
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 15);
    try {
      final req = await client.getUrl(Uri.parse('http://127.0.0.1:18783/base_v2.apk'));
      final resp = await req.close().timeout(const Duration(seconds: 20));
      if (resp.statusCode != 200) throw StateError('P04B bounded fixture request failed');
      final bytes = await resp.fold<List<int>>([], (acc, part) => acc..addAll(part));
      if (bytes.length < 300 || bytes.length > 16 * 1024 * 1024 ||
          sha256.convert(bytes).toString() != _expectedSha) {
        throw StateError('P04B source-bound signed APK SHA mismatch');
      }
      await file.writeAsBytes(bytes, flush: true);
      final bridge = await installApkViaThirdParty(
        file.path,
        targetPackage: _targetPackage,
        targetActivity: _targetActivity,
        expectedPackageName: _package,
      ).timeout(const Duration(seconds: 115));
      expect(bridge, isFalse,
          reason: 'External target declined; no Android install broadcast can be accepted');
      final result = classifyUnverifiedThirdPartyHandoff(bridge);
      expect(result.isHandedOff, isTrue);
      expect(result.isSuccess, isFalse);
      expect(result.isCancelled, isFalse);
      debugPrint('OX_R02F_P04B_DART_REAL_DECLINE_NO_FALSE_SUCCESS_PASS');
    } finally {
      client.close(force: true);
      if (file.existsSync()) await file.delete();
    }
  });
}
