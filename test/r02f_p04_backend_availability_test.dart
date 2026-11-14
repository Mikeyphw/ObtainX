import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/services/r02f_p04_backend_availability.dart';
import 'package:shizuku_apk_installer/shizuku_apk_installer.dart';

void main() {
  for (final mode in [InstallerMode.shizuku, InstallerMode.dhizuku]) {
    test('$mode unavailable, denied and unsupported never authorize', () {
      for (final code in ['services_not_found', 'denied', 'old_shizuku',
                          'old_android_with_adb', 'unexpected', null]) {
        final p = classifyP04Backend(mode, code);
        expect(p.isAuthorized, false);
        expect(p.canClaimInstallSuccess, false);
        expect(p.releaseQualified, false);
        expect(p.physicalDeviceQualified, false);
        expect(p.mayRunAuthorizedDisposableTest(
          userInitiated: true, hostedApi36: true,
          signedDisposableFixture: true), false);
      }
    });
    test('$mode permission is bound to selected backend', () {
      final allowed = mode == InstallerMode.shizuku
          ? ['granted_adb', 'granted_root'] : ['granted_owner'];
      final foreign = mode == InstallerMode.shizuku
          ? 'granted_owner' : 'granted_root';
      for (final code in allowed) {
        final p = classifyP04Backend(mode, code);
        expect(p.state, P04BackendState.authorizedUnqualified);
        expect(p.isAuthorized, true);
        expect(p.canClaimInstallSuccess, false);
        for (final flags in [
          [false, true, true], [true, false, true], [true, true, false]
        ]) {
          expect(p.mayRunAuthorizedDisposableTest(
            userInitiated: flags[0], hostedApi36: flags[1],
            signedDisposableFixture: flags[2]), false);
        }
        expect(p.mayRunAuthorizedDisposableTest(
          userInitiated: true, hostedApi36: true,
          signedDisposableFixture: true), true);
      }
      final p = classifyP04Backend(mode, foreign);
      expect(p.state, P04BackendState.wrongBackendPermission);
      expect(p.isAuthorized, false);
    });
    test('$mode non-user check cannot even report permission', () {
      final p = classifyP04Backend(mode, 'granted_owner', userInitiated: false);
      expect(p.state, P04BackendState.notRequested);
      expect(p.permissionCode, null);
      expect(p.isAuthorized, false);
    });
  }
}
