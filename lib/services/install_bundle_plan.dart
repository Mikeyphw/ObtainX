/// Validated, deterministic install plan for downloaded Android APK bundles.
///
/// This is deliberately independent of the Android PackageManager plugin so
/// adversarial package inventories can be tested on a hosted Dart VM. Android
/// metadata is collected by the caller *before* any installer is invoked.
///
/// This planner does NOT attest signatures or prove installation. Android must
/// validate signing certificates and commit the complete session atomically.
library;

enum InstallArtifactFormat { apk, xapk, apkm, apks, zip, tarball }

InstallArtifactFormat? installArtifactFormat(String assetName) {
  final name = assetName.toLowerCase();
  if (name.endsWith('.apk')) {
    return InstallArtifactFormat.apk;
  }
  if (name.endsWith('.xapk')) {
    return InstallArtifactFormat.xapk;
  }
  if (name.endsWith('.apkm')) {
    return InstallArtifactFormat.apkm;
  }
  if (name.endsWith('.apks')) {
    return InstallArtifactFormat.apks;
  }
  if (name.endsWith('.zip')) {
    return InstallArtifactFormat.zip;
  }
  if (name.endsWith('.tar') || name.endsWith('.tar.gz') ||
      name.endsWith('.tgz') || name.endsWith('.tar.bz2') ||
      name.endsWith('.tar.xz')) {
    return InstallArtifactFormat.tarball;
  }
  return null;
}

/// APK name patterns known to be configuration splits of a base APK.
/// Other multi-APK combinations are NOT guessed to be one install session.
bool isConfigurationSplitApk(String path) {
  final name = path.replaceAll('\\', '/').split('/').last.toLowerCase();
  return RegExp(r'^(?:split_)?config[._-][a-z0-9_.-]+\.apk$')
      .hasMatch(name);
}

class InstallApkMember {
  const InstallApkMember({
    required this.path,
    this.packageName,
    this.versionCode,
    this.minSdkVersion,
    this.targetSdkVersion,
  });

  final String path;
  final String? packageName;
  final int? versionCode;
  final int? minSdkVersion;
  final int? targetSdkVersion;
}

class InstallBundlePlan {
  InstallBundlePlan({
    required this.packageName,
    required this.versionCode,
    required this.baseApkPath,
    required List<String> configApkPaths,
    required this.format,
    this.minSdkVersion,
    this.targetSdkVersion,
  }) : configApkPaths = List<String>.unmodifiable(configApkPaths);

  final String packageName;
  final int versionCode;
  final String baseApkPath;
  final List<String> configApkPaths;
  final InstallArtifactFormat format;
  final int? minSdkVersion;
  final int? targetSdkVersion;

  /// The base APK always comes first, then deterministic, compatible splits.
  List<String> get sessionPaths =>
      List<String>.unmodifiable([baseApkPath, ...configApkPaths]);
  bool get requiresSplitSession => configApkPaths.isNotEmpty;
}

String _apkName(String path) => path.replaceAll('\\', '/').split('/').last;

void _verifyApkPath(String path) {
  if (!path.toLowerCase().endsWith('.apk') || path.contains(',') ||
      path.contains('\u0000') || path.contains('\n') ||
      path.contains('\r') || path.contains('\\') ||
      _apkName(path).isEmpty) {
    // The stock installer transports multiple paths as a comma-joined string.
    // Reject delimiter injection instead of accidentally passing extra paths.
    throw const FormatException('Invalid APK member path');
  }
}

const _knownAbis = [
  'arm64-v8a', 'armeabi-v7a', 'armeabi', 'x86_64', 'x86', 'mips64', 'mips',
  'riscv64',
];

String _normalizedAbi(String text) => text.toLowerCase().replaceAll('-', '_');

String? _apkAbi(String path) {
  final name = _normalizedAbi(_apkName(path));
  final seen = <String>[];
  for (final abi in _knownAbis) {
    final normalized = _normalizedAbi(abi);
    final re = RegExp('(^|[.])${RegExp.escape(normalized)}' r'(?=[.]|$)');
    if (re.hasMatch(name)) {
      seen.add(abi);
    }
  }
  // An APK named as two ABIs is ambiguous, not universally compatible.
  if (seen.length > 1) {
    throw const FormatException('Ambiguous split ABI qualifiers');
  }
  return seen.isEmpty ? null : seen.single;
}

/// Exactly one parseable base APK is mandatory. Package/version mismatches,
/// multiple standalone variants, unknown split roles and incompatible ABIs
/// fail closed; never silently install the first APK in archive enumeration.
InstallBundlePlan resolveInstallBundlePlan({
  required List<InstallApkMember> members,
  required InstallArtifactFormat format,
  required List<String> supportedAbis,
  String? expectedPackageName,
  int? deviceSdkVersion,
}) {
  if (members.isEmpty) {
    throw const FormatException('Archive contains no APKs');
  }
  if (members.length > 4096) {
    throw const FormatException('Too many APK members');
  }
  if (format == InstallArtifactFormat.apk && members.length != 1) {
    throw const FormatException('A standalone APK must be a single file');
  }
  final seenPaths = <String>{};
  final seenNames = <String>{};
  for (final member in members) {
    _verifyApkPath(member.path);
    if (!seenPaths.add(member.path.toLowerCase()) ||
        !seenNames.add(_apkName(member.path).toLowerCase())) {
      throw const FormatException('Duplicate or ambiguous APK filenames');
    }
  }
  final config = members.where((m) => isConfigurationSplitApk(m.path)).toList();
  final baseCandidates = members.where((m) => !isConfigurationSplitApk(m.path)).toList();
  if (baseCandidates.length != 1) {
    throw const FormatException('Bundle requires exactly one unambiguous base APK');
  }
  final base = baseCandidates.single;
  final packageName = base.packageName;
  final versionCode = base.versionCode;
  if (packageName == null || packageName.isEmpty || versionCode == null ||
      versionCode < 0 ||
      !RegExp(r'^[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+$')
          .hasMatch(packageName)) {
    throw const FormatException('Base APK metadata unavailable or invalid');
  }
  if (expectedPackageName != null && expectedPackageName != packageName) {
    throw const FormatException('Bundle package does not match tracked application');
  }
  if (base.minSdkVersion != null && deviceSdkVersion != null &&
      base.minSdkVersion! > deviceSdkVersion) {
    throw const FormatException('APK requires a newer Android SDK');
  }
  for (final member in config) {
    if (member.packageName != null && member.packageName != packageName) {
      throw const FormatException('Split package identity mismatch');
    }
    if (member.versionCode != null && member.versionCode != versionCode) {
      throw const FormatException('Split versionCode mismatch');
    }
    if (member.minSdkVersion != null && deviceSdkVersion != null &&
        member.minSdkVersion! > deviceSdkVersion) {
      throw const FormatException('Split requires a newer Android SDK');
    }
  }
  final byAbi = <String, InstallApkMember>{};
  final nonAbi = <InstallApkMember>[];
  for (final member in config) {
    final abi = _apkAbi(member.path);
    if (abi == null) {
      nonAbi.add(member);
    } else if (byAbi.containsKey(abi)) {
      throw const FormatException('Multiple APK splits for the same ABI');
    } else {
      byAbi[abi] = member;
    }
  }
  InstallApkMember? abiMember;
  if (byAbi.isNotEmpty) {
    for (final abi in supportedAbis) {
      if (byAbi.containsKey(abi)) {
        abiMember = byAbi[abi];
        break;
      }
    }
    if (abiMember == null) {
      throw const FormatException('No compatible ABI configuration split');
    }
  }
  final selectedConfig = [...nonAbi, if (abiMember != null) abiMember]
    ..sort((a, b) => a.path.compareTo(b.path));
  return InstallBundlePlan(
    packageName: packageName,
    versionCode: versionCode,
    baseApkPath: base.path,
    configApkPaths: selectedConfig.map((m) => m.path).toList(),
    format: format,
    minSdkVersion: base.minSdkVersion,
    targetSdkVersion: base.targetSdkVersion,
  );
}

/// Fail closed on misplaced OBB files: a bundle must not copy another app's
/// expansion data to the tracked package directory.
void validateObbFileNames(List<String> paths, String packageName) {
  final expected = RegExp(
    '^(?:main|patch)\\.[0-9]+\\.${RegExp.escape(packageName)}' r'\.obb$',
    caseSensitive: false,
  );
  final seen = <String>{};
  for (final path in paths) {
    final name = _apkName(path);
    if (!expected.hasMatch(name) || !seen.add(name.toLowerCase())) {
      throw const FormatException('OBB file does not belong to planned package');
    }
  }
}
