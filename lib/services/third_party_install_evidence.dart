/// External installer bridge signals are not PackageManager verification.
///
/// The native bridge can report a package-change broadcast, but the caller
/// must independently reconcile actual package/version before recording a
/// confirmed install. This boundary deliberately never returns success.
library;

import 'package:obtainium/installers/installer.dart';

InstallResult classifyUnverifiedThirdPartyHandoff(bool bridgeChangeObserved) {
  // Both true (broadcast observed) and false (timeout/unobserved) are pending.
  // A package broadcast is not proof of the planned version or exact APK bytes.
  if (bridgeChangeObserved) {
    return InstallResult.handedOff();
  }
  return InstallResult.handedOff();
}
