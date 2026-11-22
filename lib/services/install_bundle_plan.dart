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

const _densityDpis = <String, int>{
  'ldpi': 120, 'mdpi': 160, 'tvdpi': 213, 'hdpi': 240,
  'xhdpi': 320, 'xxhdpi': 480, 'xxxhdpi': 640,
};

String _configQualifier(String path) {
  final name = _apkName(path).toLowerCase();
  return RegExp(r'^(?:split_)?config[._-](.+)\.apk$')
          .firstMatch(name)?.group(1) ?? '';
}

String _canonicalLocale(String text) {
  return text.toLowerCase().replaceAll('_', '-')
      .replaceAllMapped(
        RegExp(r'-r([a-z]{2})$'),
        (match) => '-${match.group(1)!}',
      );
}

bool _isLanguageQualifier(String qualifier) =>
    RegExp(r'^[a-z]{2,3}(?:[-_]r[a-z]{2})?$').hasMatch(qualifier);

/// Exactly one parseable base APK is mandatory. Package/version mismatches,
/// multiple standalone variants, unknown split roles and incompatible ABIs
/// fail closed; never silently install the first APK in archive enumeration.
InstallBundlePlan resolveInstallBundlePlan({
  required List<InstallApkMember> members,
  required InstallArtifactFormat format,
  required List<String> supportedAbis,
  String? expectedPackageName,
  int? deviceSdkVersion,
  List<String> deviceLocales = const <String>[],
  int? deviceDensityDpi,
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
  if (deviceDensityDpi != null && deviceDensityDpi <= 0) {
    throw const FormatException('Invalid device display density');
  }
  final byAbi = <String, InstallApkMember>{};
  final byLocale = <String, InstallApkMember>{};
  final byDensity = <int, InstallApkMember>{};
  final nonAbi = <InstallApkMember>[];
  for (final member in config) {
    final abi = _apkAbi(member.path);
    final qualifier = _configQualifier(member.path);
    if (abi != null) {
      if (byAbi.containsKey(abi)) {
        throw const FormatException('Multiple APK splits for the same ABI');
      }
      byAbi[abi] = member;
    } else if (qualifier == 'nodpi' || qualifier == 'anydpi') {
      nonAbi.add(member);
    } else if (_densityDpis.containsKey(qualifier)) {
      final dpi = _densityDpis[qualifier]!;
      if (byDensity.containsKey(dpi)) {
        throw const FormatException('Multiple APK splits for the same density');
      }
      byDensity[dpi] = member;
    } else if (_isLanguageQualifier(qualifier)) {
      final locale = _canonicalLocale(qualifier);
      if (byLocale.containsKey(locale)) {
        throw const FormatException('Multiple APK splits for the same locale');
      }
      byLocale[locale] = member;
    } else {
      // Keep non-ABI, non-locale, non-density config splits as independent
      // resources; do not guess new split roles or silently drop them.
      nonAbi.add(member);
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
  final selectedLocales = <InstallApkMember>[];
  if (byLocale.isNotEmpty) {
    if (deviceLocales.isEmpty && byLocale.length > 1) {
      throw const FormatException('Ambiguous language splits require locale evidence');
    }
    if (deviceLocales.isEmpty) {
      selectedLocales.add(byLocale.values.single);
    } else {
      for (final preferred in deviceLocales) {
        final locale = _canonicalLocale(preferred);
        if (byLocale.containsKey(locale)) {
          final match = byLocale[locale]!;
          if (!selectedLocales.contains(match)) selectedLocales.add(match);
          continue;
        }
        final language = locale.split('-').first;
        if (byLocale.containsKey(language)) {
          final match = byLocale[language]!;
          if (!selectedLocales.contains(match)) selectedLocales.add(match);
        }
      }
      if (selectedLocales.isEmpty) {
        throw const FormatException('No compatible language configuration split');
      }
    }
  }
  InstallApkMember? densityMember;
  if (byDensity.isNotEmpty) {
    if (deviceDensityDpi == null && byDensity.length > 1) {
      throw const FormatException('Ambiguous density splits require display evidence');
    }
    if (deviceDensityDpi == null) {
      densityMember = byDensity.values.single;
    } else {
      final choices = byDensity.keys.toList()
        ..sort((a, b) {
          final diffA = (a - deviceDensityDpi).abs();
          final diffB = (b - deviceDensityDpi).abs();
          final distance = diffA.compareTo(diffB);
          return distance != 0 ? distance : b.compareTo(a);
        });
      densityMember = byDensity[choices.first];
    }
  }
  final selectedConfig = [...nonAbi, ?abiMember, ...selectedLocales, ?densityMember]
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

/// A lexical containment check only. The caller must independently refuse
/// symlink/non-regular entries and verify the real bytes before any OBB move.
void validateStagedObbPaths(List<String> paths, String packageName, {
  required String extractionRoot,
}) {
  validateObbFileNames(paths, packageName);
  final root = extractionRoot.endsWith('/') && extractionRoot.length > 1
      ? extractionRoot.substring(0, extractionRoot.length - 1)
      : extractionRoot;
  if (root == '/' || !root.startsWith('/') || root.contains('\\') ||
      root.contains('//') || root.contains('\u0000') ||
      root.split('/').contains('..') || root.split('/').contains('.')) {
    throw const FormatException('Untrusted OBB extraction root');
  }
  for (final path in paths) {
    if (!path.startsWith('$root/') || path.contains('\\') ||
        path.contains('//') || path.contains('\u0000') ||
        path.split('/').contains('..') || path.split('/').contains('.')) {
      throw const FormatException('OBB member escapes validated staging root');
    }
  }
}
