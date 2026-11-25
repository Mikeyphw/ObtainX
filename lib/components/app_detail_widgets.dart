import 'package:easy_localization/easy_localization.dart';
import 'package:flutter/material.dart';
import 'package:obtainium/components/ui_widgets.dart';
import 'package:obtainium/custom_errors.dart';
import 'package:obtainium/providers/apps_provider.dart';
import 'package:obtainium/providers/settings_provider.dart';
import 'package:obtainium/providers/source_provider.dart';
import 'package:obtainium/services/r09_discovery.dart';
import 'package:obtainium/theme/app_dialog_theme.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher_string.dart';

String appInstalledVersionText(App? app) {
  final installed = app?.installedVersion;
  if (installed == null) return tr('notInstalled');
  final upToDate = installed == app?.latestVersion;
  return '$installed ${tr('installed')}${upToDate ? ' / ${tr('latest')}' : ''}';
}

class AppInfoDialog extends StatelessWidget {
  final AppInMemory app;
  final AppsProvider appsProvider;

  const AppInfoDialog({
    super.key,
    required this.app,
    required this.appsProvider,
  });

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final isTV = context.read<SettingsProvider>().isTV;
    return AlertDialog(
      scrollable: true,
      title: Text(app.name),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (app.icon != null)
            Center(child: AppIcon(bytes: app.icon, size: 56, radius: 14))
          else
            const SizedBox.shrink(),
          const SizedBox(height: 12),
          Text(
            app.name,
            style: textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
          ),
          Text(
            tr('byX', args: [app.author]),
            style: textTheme.bodyMedium?.copyWith(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
          ),
          Text(
            app.app.url,
            style: textTheme.labelSmall?.copyWith(
              decoration: TextDecoration.underline,
            ),
          ),
          Text(app.app.id, style: textTheme.labelSmall),
          const SizedBox(height: 8),
          Text(appInstalledVersionText(app.app), style: textTheme.bodyMedium),
          Text(
            tr(
              'lastUpdateCheckX',
              args: [
                app.app.lastUpdateCheck
                        ?.toLocal()
                        .toString()
                        .split('.')
                        .first ??
                    tr('never'),
              ],
            ),
            style: textTheme.bodySmall,
          ),
        ],
      ),
      actions: [
        FilledButton.tonal(
          autofocus: isTV,
          onPressed: () => Navigator.of(context).pop(),
          child: Text(tr('continue')),
        ),
      ],
    );
  }
}

class AppFilePicker extends StatefulWidget {
  const AppFilePicker({
    super.key,
    required this.app,
    this.initVal,
    this.archs,
    this.pickAnyAsset = false,
  });

  final App app;
  final MapEntry<String, String>? initVal;
  final List<String>? archs;
  final bool pickAnyAsset;

  @override
  State<AppFilePicker> createState() => _AppFilePickerState();
}

class _AppFilePickerState extends State<AppFilePicker> {
  MapEntry<String, String>? fileUrl;

  @override
  Widget build(BuildContext context) {
    final isTV = context.read<SettingsProvider>().isTV;
    var urlsToSelectFrom = widget.app.apkUrls;
    if (widget.pickAnyAsset) {
      urlsToSelectFrom = [...urlsToSelectFrom, ...widget.app.otherAssetUrls];
    }
    final archs = widget.archs ?? const <String>[];
    bool allowed(MapEntry<String, String> asset) => widget.pickAnyAsset ||
        r09ActionsEligible(asset, widget.app.additionalSettings, widget.app.url, DateTime.now());
    R09ArtifactChoice choice(MapEntry<String, String> asset) {
      final result = r09ArtifactChoice(asset.key, archs, downloadOnly: widget.pickAnyAsset);
      return allowed(asset) ? result : R09ArtifactChoice(false, result.abiHints,
          result.role, 'r09ExpiredOrUnbound');
    }
    fileUrl = r09ChooseArtifact(urlsToSelectFrom, archs, fileUrl ?? widget.initVal,
        downloadOnly: widget.pickAnyAsset, allowed: allowed);
    String details(MapEntry<String, String> asset) {
      final info = choice(asset);
      final preferred = widget.app.preferredApkIndex;
      final knownSize = preferred >= 0 && preferred < widget.app.apkUrls.length &&
          widget.app.apkUrls[preferred].key == asset.key &&
          widget.app.apkUrls[preferred].value == asset.value ? widget.app.apkSizeBytes : null;
      final evidence = widget.app.additionalSettings['r04ActionsArchiveEvidence'];
      final trust = evidence is Map && evidence['sourceUrl'] == widget.app.url &&
          evidence['archiveUrl'] == asset.value && evidence['archiveName'] == asset.key
          ? '\n${tr('r09ZipDigest')}: ${evidence['archiveSha256'] ?? tr('unknown')}\n'
            '${tr('r09Expires')}: ${evidence['expiresAt'] ?? tr('unknown')}'
          : '';
      return '${tr(info.role)} · ${tr(info.reason)}\n'
          '${tr('r09AbiHint')}: ${info.abiHints.isEmpty ? tr('unknown') : info.abiHints.join(', ')}\n'
          '${tr('r09ArtifactSize')}: ${knownSize == null ? tr('unknown') : '$knownSize B'}$trust';
    }
    return AlertDialog(
      scrollable: true,
      title: Text(
        widget.pickAnyAsset
            ? tr('selectX', args: [lowerCaseIfEnglish(tr('releaseAsset'))])
            : tr('pickAnAPK'),
      ),
      content: urlsToSelectFrom.isEmpty
          ? Text(tr('r09NoSource'))
          : RadioGroup<int>(
              groupValue: fileUrl == null ? null : urlsToSelectFrom.indexWhere(
                (asset) => asset.key == fileUrl?.key && asset.value == fileUrl?.value),
              onChanged: (int? val) {
                if (val != null && val >= 0 && val < urlsToSelectFrom.length &&
                    choice(urlsToSelectFrom[val]).eligible) {
                  setState(() { fileUrl = urlsToSelectFrom[val]; });
                }
              },
              child: Column(
                children: [
                  urlsToSelectFrom.length > 1
                      ? Text(
                          tr(
                            'appHasMoreThanOnePackage',
                            args: [widget.app.finalName],
                          ),
                        )
                      : const SizedBox.shrink(),
                  Text('${tr('r09TrackedPackage')}: ${widget.app.id} · ${widget.app.latestVersion}\n${tr('r09MetadataPending')}'),
                  const SizedBox(height: 16),
                  if (isTV)
                    ...urlsToSelectFrom.asMap().entries.map(
                      (entry) => ListTile(
                        autofocus: choice(entry.value).eligible && fileUrl?.key == entry.value.key && fileUrl?.value == entry.value.value,
                        leading: choice(entry.value).eligible ? Radio<int>(value: entry.key) : const Icon(Icons.block),
                        title: Text(entry.value.key),
                        subtitle: Text(details(entry.value)),
                        enabled: choice(entry.value).eligible,
                        selected: fileUrl?.key == entry.value.key && fileUrl?.value == entry.value.value,
                        onTap: choice(entry.value).eligible ? () {
                          setState(() { fileUrl = entry.value; });
                        } : null,
                      ),
                    )
                  else
                    ...urlsToSelectFrom.asMap().entries.map(
                      (entry) => RadioListTile<int>(
                        title: Text(entry.value.key),
                        subtitle: Text(details(entry.value)),
                        enabled: choice(entry.value).eligible,
                        value: entry.key,
                      ),
                    ),
                  if (widget.archs != null) const SizedBox(height: 16),
                  if (widget.archs != null)
                    Text(
                      widget.archs!.length == 1
                          ? tr('deviceSupportsXArch', args: [widget.archs![0]])
                          : tr('deviceSupportsFollowingArchs') +
                                list2FriendlyString(
                                  widget.archs!.map((e) => '\'$e\'').toList(),
                                ),
                      style: const TextStyle(
                        fontStyle: FontStyle.italic,
                        fontSize: 12,
                      ),
                    ),
                ],
              ),
            ),
      actions: [
        TextButton(
          onPressed: () {
            Navigator.of(context).pop(null);
          },
          child: Text(tr('cancel')),
        ),
        FilledButton(
          autofocus: isTV && fileUrl == null,
          onPressed: fileUrl != null && choice(fileUrl!).eligible
              ? () {
                  final selected = fileUrl;
                  if (selected == null || !choice(selected).eligible) {
                    setState(() {});
                    return;
                  }
                  context.read<SettingsProvider>().selectionClick();
                  Navigator.of(context).pop(selected);
                }
              : null,
          child: Text(tr('continue')),
        ),
      ],
    );
  }
}

class APKOriginWarningDialog extends StatefulWidget {
  const APKOriginWarningDialog({
    super.key,
    required this.sourceUrl,
    required this.apkUrl,
  });

  final String sourceUrl;
  final String apkUrl;

  @override
  State<APKOriginWarningDialog> createState() => _APKOriginWarningDialogState();
}

class _APKOriginWarningDialogState extends State<APKOriginWarningDialog> {
  bool _dontShowAgain = false;

  @override
  Widget build(BuildContext context) {
    final isTV = context.read<SettingsProvider>().isTV;
    return AlertDialog(
      scrollable: true,
      title: Text(tr('warning')),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            tr(
              'sourceIsXButPackageFromYPrompt',
              args: [
                Uri.parse(widget.sourceUrl).host,
                Uri.parse(widget.apkUrl).host,
              ],
            ),
          ),
          const SizedBox(height: 8),
          CheckboxListTile(
            autofocus: isTV,
            contentPadding: EdgeInsets.zero,
            controlAffinity: ListTileControlAffinity.leading,
            value: _dontShowAgain,
            onChanged: (v) => setState(() => _dontShowAgain = v ?? false),
            title: Text(tr('dontShowAgain')),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () {
            Navigator.of(context).pop(null);
          },
          child: Text(tr('cancel')),
        ),
        FilledButton(
          autofocus: !isTV,
          onPressed: () {
            final sp = context.read<SettingsProvider>();
            sp.selectionClick();
            if (_dontShowAgain) {
              sp.hideAPKOriginWarning = true;
            }
            Navigator.of(context).pop(true);
          },
          child: Text(tr('continue')),
        ),
      ],
    );
  }
}

/// What the user chose in a [MalwareScanWarningDialog].
enum MalwareScanDialogChoice {
  /// Abandon this install.
  cancelInstall,

  /// Install despite the flagged/failed scan.
  installAnyway,

  /// Ask VirusTotal about the same APK again. Offered for a failed scan only -
  /// a real detection is not going to change on a retry.
  retryScan,
}

/// Shown before installing an APK that VirusTotal flagged (or that could not be
/// scanned). Pops a [MalwareScanDialogChoice]; a null result (dismissed without
/// a choice) must be treated as [MalwareScanDialogChoice.cancelInstall]. (Fork
/// feature re-homed here from the pre-merge apps_provider.)
class MalwareScanWarningDialog extends StatelessWidget {
  const MalwareScanWarningDialog({
    super.key,
    required this.appName,
    required this.status,
    required this.detail,
    required this.reportUrl,
  });

  final String appName;
  final String status;
  final String? detail;
  final String? reportUrl;

  @override
  Widget build(BuildContext context) {
    final bool flagged = status == malwareScanStatusFlagged;
    // A failed scan means VirusTotal never returned a verdict at all, so asking
    // again can still produce one - and cancelling keeps the downloaded APK, so
    // a retry (here or later) costs no bandwidth. Neither applies to a real
    // detection, so a flagged APK gets no retry.
    final bool scanFailed = !flagged;
    return AlertDialog(
      scrollable: true,
      title: Text(
        tr(flagged ? 'malwareScanFlaggedTitle' : 'malwareScanErrorTitle'),
      ),
      contentPadding: appDialogContentPadding,
      content: Text(
        detail ??
            tr(flagged ? 'malwareScanFlaggedTitle' : 'malwareScanErrorTitle'),
      ),
      actions: [
        if (scanFailed)
          TextButton(
            onPressed: () {
              hapticSelection();
              Navigator.of(context).pop(MalwareScanDialogChoice.retryScan);
            },
            child: Text(tr('virusTotalRetryScan')),
          ),
        if (reportUrl != null)
          TextButton(
            onPressed: () {
              launchUrlString(reportUrl!, mode: LaunchMode.externalApplication);
            },
            child: Text(tr('virusTotalViewReport')),
          ),
        TextButton(
          onPressed: () {
            Navigator.of(context).pop(MalwareScanDialogChoice.cancelInstall);
          },
          child: Text(tr('cancelInstall')),
        ),
        TextButton(
          onPressed: () {
            hapticSelection();
            Navigator.of(context).pop(MalwareScanDialogChoice.installAnyway);
          },
          style: TextButton.styleFrom(
            foregroundColor: Theme.of(context).colorScheme.error,
          ),
          child: Text(tr('installAnyway')),
        ),
      ],
    );
  }
}
