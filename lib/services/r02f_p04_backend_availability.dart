/// Read-only R02F P04 backend evidence. A permission code is not install proof.
/// Explicit user-initiated checks may call the existing serialized plugin, but
/// this classifier itself never requests privilege, installs or changes DPM.
import 'package:shizuku_apk_installer/shizuku_apk_installer.dart';

enum P04BackendState {
  notRequested,
  unavailable,
  unsupported,
  authorizationRequired,
  wrongBackendPermission,
  authorizedUnqualified,
  unknown,
}

class P04BackendAvailability {
  final InstallerMode mode;
  final String? permissionCode;
  final P04BackendState state;
  const P04BackendAvailability(this.mode, this.permissionCode, this.state);

  bool get isAuthorized => state == P04BackendState.authorizedUnqualified;
  bool get canClaimInstallSuccess => false;
  bool get releaseQualified => false;
  bool get physicalDeviceQualified => false;

  /// A test is permitted only with an independently checked disposable
  /// emulator, a fixture pin, and an explicit user-initiated authorization.
  /// This merely authorizes a *test*, never claims an install took place.
  bool mayRunAuthorizedDisposableTest({
    required bool userInitiated,
    required bool hostedApi36,
    required bool signedDisposableFixture,
  }) => isAuthorized && userInitiated && hostedApi36 && signedDisposableFixture;
}

P04BackendAvailability classifyP04Backend(
  InstallerMode mode,
  String? code, {
  bool userInitiated = true,
}) {
  if (!userInitiated) {
    return P04BackendAvailability(mode, null, P04BackendState.notRequested);
  }
  if (code == 'services_not_found') {
    return P04BackendAvailability(mode, code, P04BackendState.unavailable);
  }
  if (code == 'old_shizuku' || code == 'old_android_with_adb') {
    return P04BackendAvailability(mode, code, P04BackendState.unsupported);
  }
  if (code == 'denied' || code == 'permission_denied') {
    return P04BackendAvailability(mode, code, P04BackendState.authorizationRequired);
  }
  if (code == 'granted_adb' || code == 'granted_root' || code == 'granted_owner') {
    final bool matching = mode == InstallerMode.dhizuku
        ? code == 'granted_owner'
        : code == 'granted_adb' || code == 'granted_root';
    return P04BackendAvailability(
      mode,
      code,
      matching ? P04BackendState.authorizedUnqualified
               : P04BackendState.wrongBackendPermission,
    );
  }
  return P04BackendAvailability(mode, code, P04BackendState.unknown);
}
