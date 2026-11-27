import 'package:easy_localization/easy_localization.dart';
import 'package:flutter/material.dart';
import 'package:obtainium/components/ui_widgets.dart';
import 'package:obtainium/custom_errors.dart';
import 'package:obtainium/providers/apps_provider.dart';
import 'package:obtainium/providers/settings_provider.dart';
import 'package:obtainium/providers/source_provider.dart';
import 'package:obtainium/services/r09_discovery.dart';
import 'package:obtainium/services/r09_artifact_inspection.dart';
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
    this.inspectCandidate,
  });

  final App app;
  final MapEntry<String, String>? initVal;
  final List<String>? archs;
  final bool pickAnyAsset;
  final Future<R09ArtifactInspection> Function(MapEntry<String, String>, CancellationToken, void Function(double?, int?, int?))? inspectCandidate;

  @override
  State<AppFilePicker> createState() => _AppFilePickerState();
}

class _AppFilePickerState extends State<AppFilePicker> {
  MapEntry<String, String>? fileUrl;
  bool initialized = false;
  final reviews = <(String, String), R09ArtifactInspection>{};
  final failures = <(String, String)>{};
  CancellationToken? token;
  double? progress;
  (String, String) keyOf(MapEntry<String, String> asset) => (asset.key, asset.value);
  bool get busy => token != null;

  @override
  void dispose() {
    token?.cancel();
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant AppFilePicker oldWidget) {
    super.didUpdateWidget(oldWidget);
    // The review cache belongs to this exact immutable listing/release, not
    // a reused widget or a filename. Cancel stale work before clearing it.
    if (!identical(oldWidget.app, widget.app) ||
        oldWidget.pickAnyAsset != widget.pickAnyAsset) {
      token?.cancel();
      reviews.clear();
      failures.clear();
      initialized = false;
      fileUrl = null;
    }
  }

  bool inspectionAllowed(MapEntry<String, String> asset) =>
      !widget.pickAnyAsset && widget.app.apkUrls.where((entry) =>
        keyOf(entry) == keyOf(asset)).length == 1 &&
      r09ActionsEligible(asset, widget.app.additionalSettings,
        widget.app.url, DateTime.now());

  Future<void> inspect(MapEntry<String, String> asset) =>
      inspectBatch([asset], selectIfEmpty: true);

  /// Explicit batches only. Each candidate runs through the same real
  /// download/manifest/signer review, in sequence and under one cancellation
  /// token. A new batch is a separate user action; no surprise downloads.
  Future<void> inspectBatch(List<MapEntry<String, String>> requested,
      {bool selectIfEmpty = false}) async {
    final callback = widget.inspectCandidate;
    if (callback == null || busy || requested.isEmpty ||
        requested.length > r09ComparisonBatchLimit) {
      return;
    }
    final listing = widget.app;
    final active = CancellationToken();
    setState(() {
      token = active;
      progress = null;
    });
    bool current() => mounted && identical(token, active) &&
        identical(widget.app, listing) && !active.isCancelled;
    try {
      for (final asset in requested) {
        if (!current()) break;
        if (!inspectionAllowed(asset)) continue;
        final key = keyOf(asset);
        setState(() {
          progress = null;
          reviews.remove(key);
          failures.remove(key);
        });
        try {
          final result = await callback(asset, active, (_, received, total) {
            if (!current()) return;
            setState(() => progress = received != null && total != null && total > 0
                ? (received / total).clamp(0.0, 1.0).toDouble() : null);
          });
          if (!current()) break;
          if (!inspectionAllowed(asset)) continue;
          setState(() {
            reviews[key] = result;
            if (selectIfEmpty && result.eligible && fileUrl == null) {
              fileUrl = asset;
            }
          });
        } catch (_) {
          if (current()) {
            setState(() => failures.add(key));
          }
        }
      }
    } finally {
      if (mounted && identical(token, active)) {
        setState(() { token = null; progress = null; });
      }
    }
  }

  String reviewDetails(R09ArtifactInspection result) {
    final lines = <String>[
      tr(result.eligible ? 'r09ReviewCompatible' : 'r09ReviewIncompatible'),
      '${tr('r09ArtifactSize')}: ${result.bytes} B',
      '${tr(result.actionsDigestVerified ? 'r09ReviewActionsDigest' : 'r09ReviewLocalDigest')}: ${result.artifactSha256}',
      tr(result.signerStatus),
      tr('r10CertificateHint'),
      if (result.installedVersionCode != null)
        "${tr('installed')}: ${result.installedVersionName ?? tr('unknown')} (${result.installedVersionCode})",
      ...result.refusals.map((reason) => tr(reason)),
    ];
    for (final member in result.members) {
      lines.addAll([
        '${member.name} · ${tr(result.selectedPaths.contains(member.path) ? 'r09ReviewSelected' : 'r09ReviewNotSelected')}',
        '${member.packageName} · ${member.versionName ?? tr('unknown')} (${member.versionCode})',
        '${tr('r09ReviewMinSdk')}: ${member.minSdk ?? tr('unknown')} · ${member.split ?? tr('r09ReviewBase')}',
        '${tr('r09ReviewNativeAbi')}: ${member.nativeAbis.isEmpty ? tr('r09ReviewNoNativeLibs') : member.nativeAbis.join(', ')}',
        '${tr('r09ReviewLocalDigest')}: ${member.sha256}',
        '${tr('r09ReviewCertificates')}: ${member.signers.isEmpty ? tr('unknown') : member.signers.join(', ')}',
      ]);
    }
    return lines.join('\n');
  }


  @override
  Widget build(BuildContext context) {
    final isTV = context.read<SettingsProvider>().isTV;
    var urlsToSelectFrom = widget.app.apkUrls;
    if (widget.pickAnyAsset) {
      urlsToSelectFrom = [...urlsToSelectFrom, ...widget.app.otherAssetUrls];
    }
    final archs = widget.archs ?? const <String>[];
    bool allowed(MapEntry<String, String> asset) => widget.pickAnyAsset ||
        inspectionAllowed(asset);
    R09ArtifactChoice choice(MapEntry<String, String> asset) {
      final result = r09ArtifactChoice(asset.key, archs, downloadOnly: widget.pickAnyAsset);
      if (!allowed(asset)) return R09ArtifactChoice(false, result.abiHints, result.role, 'r09ExpiredOrUnbound');
      final review = reviews[keyOf(asset)];
      if (review != null) {
        return R09ArtifactChoice(review.eligible, review.members.where((m) => review.selectedPaths.contains(m.path)).expand((m) => m.nativeAbis).toSet().toList(), result.role, review.eligible ? 'r09ReviewCompatible' : 'r09ReviewIncompatible');
      }
      if (failures.contains(keyOf(asset))) return R09ArtifactChoice(false, result.abiHints, result.role, 'r09ReviewFailed');
      return result;
    }
    if (!initialized) {
      fileUrl = r09ChooseArtifact(urlsToSelectFrom, archs, widget.initVal,
          downloadOnly: widget.pickAnyAsset, allowed: allowed, evaluatedChoice: choice);
      initialized = true;
    } else if (fileUrl != null && (!choice(fileUrl!).eligible ||
        !urlsToSelectFrom.any((asset) => keyOf(asset) == keyOf(fileUrl!)))) {
      fileUrl = null;
    }
    String details(MapEntry<String, String> asset) {
      final reviewed = reviews[keyOf(asset)];
      if (reviewed != null) {
        return allowed(asset) ? reviewDetails(reviewed) : '${tr("r09ExpiredOrUnbound")}\n${reviewDetails(reviewed)}';
      }
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
    final inspectable = urlsToSelectFrom.where(inspectionAllowed).toList();
    final pending = inspectable.where((asset) =>
        !reviews.containsKey(keyOf(asset)) && !failures.contains(keyOf(asset))).toList();
    final compared = inspectable.where((asset) => reviews.containsKey(keyOf(asset))).length;
    final failed = inspectable.where((asset) => failures.contains(keyOf(asset))).length;
    Widget row(MapEntry<int, MapEntry<String, String>> entry) => Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (isTV)
          ListTile(
            autofocus: !busy && choice(entry.value).eligible && fileUrl?.key == entry.value.key && fileUrl?.value == entry.value.value,
            leading: choice(entry.value).eligible ? Radio<int>(value: entry.key) : const Icon(Icons.block),
            title: Text(entry.value.key), subtitle: Text(details(entry.value)),
            enabled: choice(entry.value).eligible && !busy,
            selected: fileUrl?.key == entry.value.key && fileUrl?.value == entry.value.value,
            onTap: !busy && choice(entry.value).eligible ? () => setState(() => fileUrl = entry.value) : null,
          )
        else
          RadioListTile<int>(title: Text(entry.value.key), subtitle: Text(details(entry.value)),
            enabled: choice(entry.value).eligible && !busy, value: entry.key),
        if (widget.inspectCandidate != null)
          Padding(padding: const EdgeInsets.only(left: 16, bottom: 8), child: OutlinedButton(
            onPressed: !busy && inspectionAllowed(entry.value) ? () => inspect(entry.value) : null,
            child: Text(tr('r09ReviewInspect')),
          )),
      ],
    );
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
                if (!busy && val != null && val >= 0 && val < urlsToSelectFrom.length &&
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
                  if (widget.inspectCandidate != null) ...[
                    Text(tr('r09ReviewExplanation')),
                    if (urlsToSelectFrom.length > 1) ...[
                      Text(tr('r09ComparisonSummary', args: [
                        '$compared', '${inspectable.length}', '$failed',
                        '${urlsToSelectFrom.length - inspectable.length}',
                      ])),
                      Text(tr('r09ComparisonExplanation')),
                      OutlinedButton(
                        onPressed: busy || pending.isEmpty ? null : () => inspectBatch(
                          pending.take(r09ComparisonBatchLimit).toList()),
                        child: Text(tr('r09ComparisonNext')),
                      ),
                    ],
                  ],
                  if (busy) LinearProgressIndicator(value: progress),
                  ...urlsToSelectFrom.asMap().entries.map(row),
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
            if (busy) { token?.cancel(); } else { Navigator.of(context).pop(null); }
          },
          child: Text(tr(busy ? 'r09ReviewCancel' : 'cancel')),
        ),
        FilledButton(
          autofocus: isTV && fileUrl == null,
          onPressed: !busy && fileUrl != null && choice(fileUrl!).eligible
              ? () {
                  final selected = fileUrl;
                  if (selected == null || !choice(selected).eligible) {
                    setState(() {});
                    return;
                  }
                  context.read<SettingsProvider>().selectionClick();
                  Navigator.of(context).pop(R09PickerSelection(selected, reviews[keyOf(selected)]));
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
