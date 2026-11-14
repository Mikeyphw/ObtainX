/// R02F P05: validate observed Android profile and APK SDK metadata before
/// accepting the existing deterministic RT02D bundle plan.
/// These checks are not proof of APK installation or of OBB write access.
library;

import 'package:obtainium/services/install_bundle_plan.dart';

void validateP05DeviceProfile({
  required int sdk,
  required List<String> supportedAbis,
  required List<String> locales,
  required int? densityDpi,
}) {
  if (sdk < 1 || sdk > 100) {
    throw const FormatException('P05 Android SDK profile invalid');
  }
  if (supportedAbis.isEmpty || supportedAbis.length > 16 ||
      supportedAbis.toSet().length != supportedAbis.length ||
      supportedAbis.any((abi) =>
          !RegExp(r'^[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*$').hasMatch(abi))) {
    throw const FormatException('P05 supported ABI evidence invalid');
  }
  if (locales.length > 32 || locales.toSet().length != locales.length ||
      locales.any((locale) =>
          !RegExp(r'^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8}){0,5}$')
              .hasMatch(locale))) {
    throw const FormatException('P05 locale evidence invalid');
  }
  if (densityDpi != null && (densityDpi < 80 || densityDpi > 2000)) {
    throw const FormatException('P05 display density evidence invalid');
  }
}

/// Tightens the SDK envelope for the *same* APKs selected by the production
/// RT02D planner. Unknown optional archive fields are not invented.
void verifyP05SdkEnvelope({
  required InstallBundlePlan plan,
  required List<InstallApkMember> members,
  required int deviceSdk,
}) {
  if (deviceSdk < 1 || deviceSdk > 100 || members.isEmpty) {
    throw const FormatException('P05 device SDK or member inventory invalid');
  }
  if (plan.minSdkVersion != null &&
      (plan.minSdkVersion! < 1 || plan.minSdkVersion! > deviceSdk)) {
    throw const FormatException('P05 incompatible base minSdk');
  }
  if (plan.targetSdkVersion != null && plan.targetSdkVersion! < 1) {
    throw const FormatException('P05 invalid base targetSdk');
  }
  if (plan.minSdkVersion != null && plan.targetSdkVersion != null &&
      plan.targetSdkVersion! < plan.minSdkVersion!) {
    throw const FormatException('P05 targetSdk below minSdk');
  }
  final selected = plan.sessionPaths.toSet();
  if (selected.length != plan.sessionPaths.length) {
    throw const FormatException('P05 duplicate selected APK');
  }
  for (final member in members.where((m) => selected.contains(m.path))) {
    if (member.minSdkVersion != null &&
        (member.minSdkVersion! < 1 || member.minSdkVersion! > deviceSdk)) {
      throw const FormatException('P05 incompatible split minSdk');
    }
    if (member.targetSdkVersion != null && member.targetSdkVersion! < 1) {
      throw const FormatException('P05 invalid split targetSdk');
    }
    if (member.targetSdkVersion != null && plan.targetSdkVersion != null &&
        member.targetSdkVersion != plan.targetSdkVersion) {
      throw const FormatException('P05 APK targetSdk metadata mismatch');
    }
  }
  if (selected.any((path) => !members.any((m) => m.path == path))) {
    throw const FormatException('P05 selected APK absent from inventory');
  }
}

/// Read-only decision shared by staged OBB refusals. Android 11+ cannot use
/// the existing direct /Android/obb route, regardless of binder availability.
/// External container handoff is unverified, not an OBB success result.
bool p05DirectObbDeliveryEligible({
  required int androidSdk,
  required bool hasObb,
  required bool externalContainerHandoff,
  required bool storagePermissionGranted,
}) {
  if (androidSdk < 1 || androidSdk > 100) {
    throw const FormatException('P05 invalid Android SDK for OBB decision');
  }
  return hasObb && !externalContainerHandoff && androidSdk < 30 &&
      storagePermissionGranted;
}
