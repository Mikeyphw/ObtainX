/// Byte-bound APK review. A parsed manifest, local SHA-256 and Android's
/// certificate observation are different evidence; none is an install receipt.
library;

import 'dart:io';

import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';
import 'package:obtainium/services/artifact_file_work.dart';
import 'package:obtainium/services/install_bundle_plan.dart';

const r09InspectionMaxBytes = 512 * 1024 * 1024;
const r09ComparisonBatchLimit = 2;
const r09InspectionMaxApks = 64;
const r09InspectionLimits = ArchiveExtractionLimits(
  maxArchiveBytes: r09InspectionMaxBytes,
  maxExpandedBytes: 1024 * 1024 * 1024,
  maxEntryBytes: r09InspectionMaxBytes,
  maxEntries: 1024,
);
const _channel = MethodChannel('dev.imranr.obtainium/r09_apk_inspection');
final _digest = RegExp(r'^[0-9a-f]{64}$');

class R09ApkFacts {
  R09ApkFacts({required this.path, required this.name, required this.sha256,
    required this.packageName, required this.versionCode, this.versionName,
    this.split, this.configForSplit, this.minSdk, this.targetSdk, this.splitRequired = false,
    this.requiredSplits = const [], this.requiredSplitTypes = const [],
    this.splitTypes = const [], this.nativeAbis = const [], this.signers = const []});

  final String path, name, sha256, packageName;
  final int versionCode;
  final String? versionName, split, configForSplit;
  final int? minSdk, targetSdk;
  final bool splitRequired;
  final List<String> requiredSplits, requiredSplitTypes, splitTypes, nativeAbis, signers;

  factory R09ApkFacts.fromNative(Map<Object?, Object?> data,
      {required String path, required String name, required String sha256}) {
    String? text(String key) {
      final value = data[key];
      if (value == null) return null;
      if (value is! String || value.length > 4096) {
        throw const FormatException('Invalid APK metadata');
      }
      return value;
    }
    List<String> strings(String key) {
      final value = data[key];
      if (value is! List || value.length > 64 ||
          value.any((entry) => entry is! String || entry.length > 255)) {
        throw const FormatException('Invalid APK metadata inventory');
      }
      return List<String>.unmodifiable(value.cast<String>());
    }
    final package = text('packageName');
    final version = data['versionCode'];
    final sdk = data['minSdk'];
    final targetSdk = data['targetSdk'];
    final signers = strings('signers');
    if (package == null || !RegExp(r'^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+$').hasMatch(package) ||
        version is! int || version < 0 || (sdk != null && (sdk is! int || sdk <= 0)) ||
        (targetSdk != null && (targetSdk is! int || targetSdk <= 0)) ||
        data['splitRequired'] is! bool || !_digest.hasMatch(sha256) ||
        signers.isEmpty || signers.toSet().length != signers.length ||
        signers.any((value) => !_digest.hasMatch(value))) {
      throw const FormatException('Invalid APK identity evidence');
    }
    return R09ApkFacts(path: path, name: name, sha256: sha256,
      packageName: package, versionCode: version, versionName: text('versionName'),
      split: text('split'), configForSplit: text('configForSplit'), minSdk: sdk as int?, targetSdk: targetSdk as int?,
      splitRequired: data['splitRequired'] as bool, requiredSplits: strings('requiredSplits'),
      requiredSplitTypes: strings('requiredSplitTypes'), splitTypes: strings('splitTypes'),
      nativeAbis: strings('nativeAbis'), signers: signers);
  }
}

Future<R09ApkFacts> inspectR09Apk(File file, String displayName) async {
  if (await FileSystemEntity.type(file.path, followLinks: false) != FileSystemEntityType.file) {
    throw const FormatException('APK is not a regular file');
  }
  final digest = await sha256FileOffIsolate(file.path);
  final data = await _channel.invokeMapMethod<Object?, Object?>('inspect', {'path': file.path});
  if (data == null || await sha256FileOffIsolate(file.path) != digest) {
    throw const FormatException('APK inspection bytes changed');
  }
  return R09ApkFacts.fromNative(data, path: file.path, name: displayName, sha256: digest);
}

Future<InstallApkMember> inspectInstallApkMember(File file) async {
  if (await FileSystemEntity.type(file.path, followLinks: false) != FileSystemEntityType.file ||
      await file.length() > 768 * 1024 * 1024 || await file.length() <= 0) {
    throw const FormatException('Invalid APK inspection input');
  }
  final before = await sha256FileOffIsolate(file.path);
  final root = await (await getTemporaryDirectory()).createTemp('r09-review-');
  try {
    final copy = File('${root.path}/member.apk');
    final sink = copy.openWrite();
    try {
      var copied = 0;
      await for (final bytes in file.openRead()) {
        copied += bytes.length;
        if (copied > 768 * 1024 * 1024) throw const FormatException('APK inspection size limit');
        sink.add(bytes);
        await sink.flush();
      }
    } finally {
      await sink.close();
    }
    final facts = await inspectR09Apk(copy, file.uri.pathSegments.last);
    if (facts.sha256 != before || await sha256FileOffIsolate(file.path) != before) {
      throw const FormatException('APK changed during manifest inspection');
    }
    return InstallApkMember(path: file.path, packageName: facts.packageName,
      versionCode: facts.versionCode, minSdkVersion: facts.minSdk, targetSdkVersion: facts.targetSdk,
      splitName: facts.split, configForSplit: facts.configForSplit, sha256: facts.sha256,
      signers: facts.signers, nativeAbis: facts.nativeAbis, requiredSplits: facts.requiredSplits,
      requiredSplitTypes: facts.requiredSplitTypes, splitTypes: facts.splitTypes, splitRequired: facts.splitRequired);
  } finally {
    await root.delete(recursive: true);
  }
}

bool _sameSigners(List<String> first, List<String> second) =>
    first.isNotEmpty && second.isNotEmpty && first.toSet().length == second.toSet().length &&
    first.toSet().containsAll(second);

class R09ArtifactInspection {
  R09ArtifactInspection({required this.artifactSha256, required this.bytes,
    required List<R09ApkFacts> members, required List<String> selectedPaths,
    required List<String> refusals, required this.signerStatus,
    required this.actionsDigestVerified, this.installedVersionCode, this.installedVersionName, this.releaseKey}) : members = List.unmodifiable(members),
      selectedPaths = List.unmodifiable(selectedPaths), refusals = List.unmodifiable(refusals);
  final String artifactSha256;
  final int bytes;
  final List<R09ApkFacts> members;
  final List<String> selectedPaths, refusals;
  final String signerStatus;
  final bool actionsDigestVerified;
  final int? installedVersionCode;
  final String? installedVersionName, releaseKey;
  bool get eligible => refusals.isEmpty && selectedPaths.isNotEmpty;
}

/// Use the same bundle planner as installation. Actual manifest IDs are
/// independently cross-checked against the supported config-split model.
R09ArtifactInspection reviewR09Artifact({required String artifactSha256,
    required int bytes, required List<R09ApkFacts> members,
    required InstallArtifactFormat format, required List<String> supportedAbis,
    required int sdk, required List<String> locales, required int? density,
    required String? expectedPackage, required List<String> installedSigners,
    required bool installedPackageObserved, required bool actionsDigestVerified,
    int? installedVersionCode, String? installedVersionName}) {
  if (!_digest.hasMatch(artifactSha256) || bytes <= 0 || bytes > r09InspectionMaxBytes ||
      members.isEmpty || members.length > r09InspectionMaxApks ||
      members.map((entry) => entry.path).toSet().length != members.length) {
    throw const FormatException('Invalid inspected artifact inventory');
  }
  final refusals = <String>{};
  final baseCandidates = members.where((entry) => entry.split == null).toList();
  final base = baseCandidates.length == 1 ? baseCandidates.single : null;
  if (base == null) refusals.add('r09ReviewBaseRequired');
  final splitIds = <String>{};
  for (final member in members) {
    final split = member.split;
    if (split != null && !splitIds.add(split)) refusals.add('r09ReviewSplitIdentity');
    if (base != null && (member.packageName != base.packageName || member.versionCode != base.versionCode)) {
      refusals.add('r09ReviewPackageMismatch');
    }

  }
  if (base != null && expectedPackage != null && base.packageName != expectedPackage) {
    refusals.add('r09ReviewPackageMismatch');
  }
  var selected = <String>[];
  if (base != null && format == InstallArtifactFormat.apk && members.length == 1) {
    selected = [base.path];
  } else {
    try {
      final plan = resolveInstallBundlePlan(members: members.map((entry) => InstallApkMember(
        path: entry.path, packageName: entry.packageName, versionCode: entry.versionCode,
        minSdkVersion: entry.minSdk, targetSdkVersion: entry.targetSdk, splitName: entry.split, configForSplit: entry.configForSplit,
        sha256: entry.sha256, signers: entry.signers, nativeAbis: entry.nativeAbis,
        requiredSplits: entry.requiredSplits, requiredSplitTypes: entry.requiredSplitTypes,
        splitTypes: entry.splitTypes, splitRequired: entry.splitRequired)).toList(), format: format,
        supportedAbis: supportedAbis, deviceSdkVersion: sdk,
        deviceLocales: locales, deviceDensityDpi: density, expectedPackageName: expectedPackage);
      selected = plan.sessionPaths;
    } on FormatException {
      refusals.add('r09ReviewBundleRefused');
    }
  }
  final chosen = members.where((entry) => selected.contains(entry.path)).toList();
  final chosenSplits = chosen.map((entry) => entry.split).whereType<String>().toSet();
  final chosenTypes = chosen.expand((entry) => entry.splitTypes).toSet();
  // Native libraries in each selected member must have a common supported ABI.
  var compatibleAbis = supportedAbis.toSet();
  for (final member in chosen) {
    if (member.minSdk != null && member.minSdk! > sdk) refusals.add('r09ReviewSdkMismatch');
    if (member.nativeAbis.isNotEmpty) {
      compatibleAbis = compatibleAbis.intersection(member.nativeAbis.toSet());
      if (compatibleAbis.isEmpty) refusals.add('r09ReviewAbiMismatch');
    }
    if ((member.splitRequired && chosenSplits.isEmpty) ||
        !chosenSplits.containsAll(member.requiredSplits) ||
        !chosenTypes.containsAll(member.requiredSplitTypes) ||
        (member.configForSplit != null && member.configForSplit != 'base' && !chosenSplits.contains(member.configForSplit))) {
      refusals.add('r09ReviewMissingSplits');
    }
    if (member.signers.isEmpty) {
      refusals.add('r09ReviewSignerUnavailable');
    } else if (base != null && !_sameSigners(member.signers, base.signers)) {
      refusals.add('r09ReviewSplitSignerMismatch');
    }
  }
  if (base != null && base.signers.isEmpty) refusals.add('r09ReviewSignerUnavailable');
  final signerStatus = base == null || base.signers.isEmpty ? 'r09ReviewSignerUnavailable' :
      !installedPackageObserved ? 'r09ReviewNoInstalledSigner' : installedSigners.isEmpty ?
      'r09ReviewInstalledSignerUnknown' : _sameSigners(base.signers, installedSigners) ?
      'r09ReviewSignerMatches' : 'r09ReviewSignerDiffers';
  if (signerStatus == 'r09ReviewSignerDiffers') refusals.add(signerStatus);
  return R09ArtifactInspection(artifactSha256: artifactSha256, bytes: bytes, members: members,
    selectedPaths: selected, refusals: refusals.toList(), signerStatus: signerStatus,
    actionsDigestVerified: actionsDigestVerified, installedVersionCode: installedVersionCode,
    installedVersionName: installedVersionName);
}

class R09PickerSelection {
  const R09PickerSelection(this.asset, this.inspection);
  final MapEntry<String, String> asset;
  final R09ArtifactInspection? inspection;
}

/// An inspection belongs to one exact release and asset, not to a filename.
class R09ReviewBinding {
  const R09ReviewBinding({required this.releaseKey, required this.digest});
  final String releaseKey, digest;
  bool matches(String currentRelease, String currentDigest) =>
      releaseKey == currentRelease && digest == currentDigest && _digest.hasMatch(digest);
}
