/// Pure discovery decisions shared by app lists, smart folders and bulk review.
library;

import 'install_bundle_plan.dart';
import 'r08_source_policy.dart';
import 'r04_actions_archive_integrity.dart';

bool r09MatchesSearch(String query, {required String name,
  required String packageId, required String source, required String sourceUrl,
  required Iterable<String> categories}) {
  final fields = [name, packageId, source, Uri.tryParse(sourceUrl)?.host ?? '',
    ...categories].map((s) => s.toLowerCase()).toList();
  return query.trim().toLowerCase().split(RegExp(r'\s+'))
      .where((token) => token.isNotEmpty)
      .every((token) => fields.any((field) => field.contains(token)));
}

String r09ChannelLabel(Map<String, dynamic> settings) {
  final mode = settings['r04GitHubSourceMode'];
  if (mode == 'actions') {
    final branch = settings['r04Branch']?.toString() ?? '';
    return branch.isEmpty ? 'Actions' : 'Actions · $branch';
  }
  if (mode == 'prereleases' || settings['r04PrereleasesOnly'] == true) return 'Prereleases';
  if (settings['includePrereleases'] == true) return 'Includes prereleases';
  return mode == 'releases' ? 'Releases' : '';
}

Map<String, List<int>> r09PackageGroups(Iterable<String> packageIds) {
  final groups = <String, List<int>>{};
  var index = 0;
  for (final id in packageIds) {
    groups.putIfAbsent(id, () => <int>[]).add(index++);
  }
  return groups;
}

/// Never silently choose among competing installable listings. Track-only
/// entries are excluded from [packageByListing] by the caller.
Set<String> r09SafeBulkSelection(Iterable<String> requested,
    Map<String, String> packageByListing) {
  final selected = requested.toSet();
  final counts = <String, int>{};
  for (final id in selected) {
    final package = packageByListing[id];
    if (package != null) counts[package] = (counts[package] ?? 0) + 1;
  }
  return selected.where((id) => (counts[packageByListing[id]] ?? 0) <= 1).toSet();
}

Set<String> r09SelectListing(Set<String> selected, String id,
    Map<String, String> packageByListing) {
  final package = packageByListing[id];
  return {...selected.where((other) => package == null ||
    packageByListing[other] != package), id};
}

/// Classify from actual recorded facts. Never infer a successful check.
String r09ListingState({required bool needsAttention, required bool noSource,
    required bool checked, required bool trackOnly, required bool updateAvailable,
    required bool installed, required bool equivalentVersion}) {
  if (needsAttention) return 'r09NeedsAttention';
  if (noSource) return 'r09NoSource';
  if (!checked) return 'r09NotChecked';
  if (trackOnly) return 'r09OnlyTrack';
  if (updateAvailable) return 'r09UpdateAvailable';
  if (!installed) return 'notInstalled';
  return equivalentVersion ? 'r09Current' : 'r09StateUncertain';
}

class R09ArtifactChoice {
  const R09ArtifactChoice(this.eligible, this.abiHints, this.role, this.reason);
  final bool eligible;
  final List<String> abiHints;
  final String role;
  final String reason;
}

R09ArtifactChoice r09ArtifactChoice(String name, List<String> supportedAbis,
    {bool downloadOnly = false}) {
  final hints = const ['arm64-v8a', 'armeabi-v7a', 'armeabi', 'x86_64', 'x86']
      .where((abi) => sourceAssetHasAbi(name, abi)).toList();
  final format = installArtifactFormat(name);
  if (format == null) {
    // A source may use an extensionless label; preserve its existing eligibility.
    return R09ArtifactChoice(true, hints, 'r09RoleUnknown', 'r09MetadataPending');
  }
  final split = format == InstallArtifactFormat.apk && isConfigurationSplitApk(name);
  final role = split ? 'r09RoleSplit' : format == InstallArtifactFormat.apk
      ? 'r09RoleApk' : 'r09RoleArchive';
  if (!downloadOnly && split) {
    return R09ArtifactChoice(false, hints, role, 'r09SplitNeedsBase');
  }
  if (!downloadOnly && hints.isNotEmpty && supportedAbis.isNotEmpty &&
      !hints.any(supportedAbis.contains)) {
    return R09ArtifactChoice(false, hints, role, 'r09AbiMismatch');
  }
  return R09ArtifactChoice(true, hints, role, 'r09MetadataPending');
}

bool r09ActionsEligible(MapEntry<String, String> asset,
    Map<String, dynamic> settings, String sourceUrl, DateTime now) {
  if (settings['r04GitHubSourceMode'] != 'actions') return true;
  try {
    r04ValidateArchiveIdentity(additionalSettings: settings, sourceUrl: sourceUrl,
      selectedAssetUrl: asset.value, selectedAssetName: asset.key, now: now);
    return true;
  } on R04ArchiveIntegrityFailure {
    return false;
  }
}

MapEntry<String, String>? r09ChooseArtifact(List<MapEntry<String, String>> assets,
    List<String> abis, MapEntry<String, String>? preferred,
    {bool downloadOnly = false, bool Function(MapEntry<String, String>)? allowed}) {
  final eligible = assets.where((a) => (allowed?.call(a) ?? true) && r09ArtifactChoice(a.key, abis,
      downloadOnly: downloadOnly).eligible).toList();
  for (final asset in eligible) {
    if (asset.key == preferred?.key && asset.value == preferred?.value) return asset;
  }
  if (eligible.isEmpty) return null;
  for (final abi in preferredSourceAbis(abis)) {
    for (final asset in eligible) {
      if (sourceAssetHasAbi(asset.key, abi)) return asset;
    }
  }
  return eligible.first;
}
