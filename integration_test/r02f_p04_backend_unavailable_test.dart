// Hosted API36: the actual plugin must report unavailable on a disposable
// emulator with neither service installed. Never provisions a device owner.
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:obtainium/installers/shizuku_plugin.dart';
import 'package:obtainium/services/r02f_p04_backend_availability.dart';
import 'package:shizuku_apk_installer/shizuku_apk_installer.dart';

const _mode = String.fromEnvironment('OX_P04_BACKEND_TEST_MODE', defaultValue: 'unavailable');
const _selected = String.fromEnvironment('OX_P04_BACKEND_SELECTED');

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('P04 Shizuku and Dhizuku exact backend availability', (tester) async {
    if (!Platform.isAndroid) throw StateError('Android runtime required');
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: Text('P04 backend availability'))));
    if (_mode == 'unavailable') {
      for (final mode in [InstallerMode.shizuku, InstallerMode.dhizuku]) {
        // Never invoke the plugin without a deliberate hosted test context.
        final p = await probeP04BackendAvailability(mode, userInitiated: true)
            .timeout(const Duration(seconds: 30));
        expect(p.state, P04BackendState.unavailable,
            reason: 'Hosted clean emulator must not silently acquire binder permissions');
        expect(p.canClaimInstallSuccess, false);
        expect(p.releaseQualified, false);
        if (mode == InstallerMode.shizuku) {
          debugPrint('OX_P04_SHIZUKU_REAL_ABSENCE_PASS');
        } else {
          debugPrint('OX_P04_DHIZUKU_REAL_ABSENCE_PASS');
        }
      }
    } else if (_mode == 'authorized_read_only' &&
               (_selected == 'shizuku' || _selected == 'dhizuku')) {
      const mode = _selected == 'shizuku' ? InstallerMode.shizuku : InstallerMode.dhizuku;
      final p = await probeP04BackendAvailability(mode, userInitiated: true)
          .timeout(const Duration(seconds: 30));
      expect(p.state, P04BackendState.authorizedUnqualified);
      expect(p.mayRunAuthorizedDisposableTest(
        userInitiated: true, hostedApi36: true, signedDisposableFixture: true), true);
      expect(p.canClaimInstallSuccess, false);
      debugPrint('OX_P04_BACKEND_EXPLICIT_AUTHORIZED_READ_ONLY_PASS');
    } else {
      throw StateError('Invalid backend test mode/selection; refused');
    }
  });
}
