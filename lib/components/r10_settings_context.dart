import 'package:easy_localization/easy_localization.dart';
import 'package:flutter/material.dart';
import 'package:obtainium/components/generated_form_model.dart';

/// Only established tuning controls are reset. Source and artifact identities,
/// credentials, security policy, tracking policy and unknown future fields are
/// deliberately preserved, including their unsaved draft values.
const r10ResettableOptionKeys = <String>{
  'skipUpdateNotifications',
  'versionStringSource',
  'versionExtractionRegEx',
  'matchGroupToUse',
  'versionDetection',
  'apkFilterRegEx',
  'invertAPKFilter',
  'autoApkFilterByArch',
  'refreshBeforeDownload',
  'includeZips',
  'zippedApkFilterRegEx',
  'includeTarballs',
  'tarballedApkFilterRegEx',
  'fallbackToOlderReleases',
  'includePrereleases',
  'verifyLatestTag',
  'filterReleaseTitlesByRegEx',
  'filterReleaseNotesByRegEx',
  'filterVersionsByRegEx',
  'sortMethodChoice',
  'useLatestAssetDateAsReleaseDate',
  'trySelectingSuggestedVersionCode',
  'autoSelectHighestVersionCode',
  'pickHighestVersionCode',
  'stayOneVersionBehind',
  'useFirstApkOfVersion',
  'defaultPseudoVersioningMethod',
};

List<List<GeneratedFormItem>> r10ResetOptionDraft({
  required List<List<GeneratedFormItem>> items,
  required Map<String, dynamic> defaults,
  required Map<String, dynamic> current,
}) {
  final result = cloneFormItems(items);
  for (final item in result.expand((row) => row)) {
    if (item is GeneratedFormSectionHeader) continue;
    final value = current.containsKey(item.key) ? current[item.key] : item.value;
    final defaultValue = defaults[item.key];
    final canReset = r10ResettableOptionKeys.contains(item.key) &&
        defaults.containsKey(item.key) &&
        !(item is GeneratedFormTextField && (item.password || item.required)) &&
        !(item is GeneratedFormSwitch && item.disabled) &&
        !(item is GeneratedFormDropdown &&
            (item.disabledOptKeys?.contains(defaultValue) == true ||
                item.opts?.any((option) => option.key == defaultValue) != true));
    item.value = canReset ? defaultValue : value;
  }
  return result;
}

String r10InstallerExplanationKey(String mode) => switch (mode) {
  'system' => 'r10InstallerSystemHint',
  'shizuku' => 'r10InstallerShizukuHint',
  'dhizuku' => 'r10InstallerDhizukuHint',
  'external' => 'r10InstallerExternalHint',
  _ => 'r10InstallerUnknownHint',
};

/// Visible, wrapping and screen-reader-readable help, without hiding existing
/// controls or claiming the selected backend is currently authorized.
class R10ContextHint extends StatelessWidget {
  const R10ContextHint(this.messageKey, {super.key});
  final String messageKey;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 8),
    child: Text(
      tr(messageKey),
      style: Theme.of(context).textTheme.bodySmall?.copyWith(
        color: Theme.of(context).colorScheme.onSurfaceVariant,
      ),
    ),
  );
}
