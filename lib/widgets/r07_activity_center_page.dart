/// R07 Activity Center: one view over R03/R05 state, never an install authority.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:easy_localization/easy_localization.dart';
import 'package:share_plus/share_plus.dart';
import 'package:obtainium/services/r11_history.dart';
import 'package:obtainium/services/r11_external_requests.dart';

import 'package:flutter/material.dart';
import 'package:obtainium/providers/apps_provider.dart';
import 'package:obtainium/services/r05_operation_journal.dart';
import 'package:obtainium/services/r03_download_history.dart';
import 'package:obtainium/services/r05_operation_receipt.dart';
import 'package:obtainium/services/r07_activity_catalog.dart';
import 'package:obtainium/services/r07_operation_timeline.dart';
import 'package:provider/provider.dart';

class R07ActivityCenterPage extends StatefulWidget {
  const R07ActivityCenterPage({super.key, this.packageId, this.listingKey, this.operationId, this.catalog});
  final String? packageId;
  final String? listingKey;
  /// A notification is never allowed to resolve by package or latest attempt.
  final String? operationId;
  /// Injected only by isolated widget tests; normal app reads existing journals.
  final R07ActivityCatalog? catalog;

  @override
  State<R07ActivityCenterPage> createState() => _R07ActivityCenterPageState();
}

class _R07ActivityCenterPageState extends State<R07ActivityCenterPage>
    with WidgetsBindingObserver {
  late final R07ActivityCatalog _catalog;
  late Future<List<R07ActivityRecord>> _entries;
  Timer? _tick;
  bool _busy = false;
  String _filter = 'all';
  String _channel = 'all';
  static const int _pageSize = 50;
  int _historyLimit = _pageSize;
  String? _historyChannel(R07ActivityRecord entry) =>
      entry.install?.channelFingerprint ?? entry.download?.historyBinding?.channel ?? entry.timeline?.intent.channel;

  @override
  void initState() {
    super.initState();
    _catalog = widget.catalog ?? R07ActivityCatalog();
    WidgetsBinding.instance.addObserver(this);
    _load();
    // R03 persists confirmed chunks, not each in-memory byte callback.
    // Provider notifications update live progress between these snapshots.
    _tick = Timer.periodic(const Duration(seconds: 4), (_) {
      if (mounted && !_busy) setState(_load);
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && mounted && !_busy) {
      setState(_load);
    }
  }

  @override
  void dispose() {
    _tick?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  void _load() {
    final provider = context.read<AppsProvider>();
    _entries = () async {
      final durable = await _catalog.load(trackedPackages: {
        for (final listing in provider.apps.values)
          listing.listingKey: listing.app.id,
      }, historyLimit: _historyLimit + 1, packageId: widget.packageId,
        listingKey: widget.listingKey, operationId: widget.operationId,
        channel: _channel, filter: _filter);
      // Current provider tokens are the only authority for cancel actions.
      // Never associate an old R03 job fingerprint with a newer transfer.
      final live = <R07ActivityRecord>[
        for (final listing in provider.apps.values)
          if (listing.downloadProgress != null)
            R07ActivityRecord(
              id: 'live:${listing.listingKey}', kind: 'live',
              stage: switch (listing.downloadProgress) {
                -1 => 'installing',
                -2 => 'scanning',
                -3 => 'flagged',
                -4 => 'handedOff',
                -5 => 'recovered',
                _ => 'downloading',
              },
              title: listing.app.finalName,
              listingKey: listing.listingKey, packageId: listing.app.id,
              updatedUtc: DateTime.now().toUtc(),
            ),
      ];
      return List<R07ActivityRecord>.unmodifiable([...live, ...durable]);
    }();
  }

  Future<void> _refresh({bool reconcile = false}) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      if (reconcile) {
        // R05/R02 own recovery and independent Android package verification.
        await context.read<AppsProvider>().reconcileR05OperationReceipts();
      }
      if (mounted) setState(_load);
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Recheck failed; no operation was marked successful.'),
        ));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  bool _matchesListing(R07ActivityRecord entry, AppsProvider provider) {
    final key = entry.listingKey;
    if (key == null || !provider.apps.containsListingKey(key)) return false;
    final live = provider.apps[key]!.app;
    if (live.id != entry.packageId) return false;
    final channel = _historyChannel(entry);
    if (entry.install == null && entry.download == null && entry.timeline == null) return true;
    // A historical filename association is for display only. An unknown or
    // stale channel cannot authorize current operations.
    return entry.historyIntegrityKnown && channel != null &&
        channel == r11ChannelFingerprint(live) &&
        (entry.timeline == null || entry.timeline!.intent.release ==
            downloadReleaseCacheKey(InstallReleaseSnapshot.fromApp(live))) &&
        (entry.download == null || entry.download!.historyBinding?.releaseFingerprint ==
            downloadReleaseCacheKey(InstallReleaseSnapshot.fromApp(live))) &&
        (entry.install == null ||
            entry.install!.releaseFingerprint == downloadReleaseCacheKey(InstallReleaseSnapshot.fromApp(live)));
  }

  Set<R07ActivityAction> _actions(
      R07ActivityRecord entry, AppsProvider provider) {
    final matching = _matchesListing(entry, provider);
    final live = matching && provider.apps[entry.listingKey]!.downloadProgress != null &&
        provider.apps[entry.listingKey]!.downloadProgress! >= 0;
    final prep = matching && provider.canCancelInstallPreparation(entry.listingKey!);
    final installed = matching &&
        provider.apps[entry.listingKey]!.installedInfo?.packageName == entry.packageId;
    return r07AllowedActions(entry, listingMatches: matching,
        liveDownload: live, cancellableInstall: prep,
        independentlyInstalled: installed);
  }

  String _explanation(R07ActivityRecord entry) {
    final raw = entry.reason?.toLowerCase() ?? '';
    if (raw.contains('sign') || raw.contains('certif')) {
      return 'Signature mismatch: review the installed signer and source. Never bypass verification.';
    }
    if (raw.contains('abi') || raw.contains('incompatib')) {
      return 'Incompatible device ABI: choose a build for this device.';
    }
    if (raw.contains('sdk') || raw.contains('android version')) {
      return 'Android SDK requirement not met: review the package requirements.';
    }
    if (raw.contains('split')) {
      return 'Split APK set requires all compatible splits; review the selection.';
    }
    if (raw.contains('expir') || raw.contains('404')) {
      return 'Build artifact expired or unavailable: refresh its source release.';
    }
    if (raw.contains('429') || raw.contains('rate limit')) {
      return 'Source rate limit: retry after the server allows requests.';
    }
    if (raw.contains('regex') || raw.contains('filter')) {
      return 'Invalid filter: check the source configuration before retrying.';
    }
    if (entry.stage == 'unknown' || entry.stage == 'handedOff' ||
        entry.stage == 'awaitingApproval') {
      return 'Android confirmation is not independently established. Review the package and installer state; do not infer success.';
    }
    return entry.reason ??
        (entry.kind == 'download' ? 'Download state from its persisted R03 record.' :
            'Only a separately verified Android install can be confirmed.');
  }

  String _details(R07ActivityRecord entry) {
    final receipt = entry.install;
    if (receipt != null) {
      return 'Attempt: ${receipt.id}\n'
          'Parent attempt: ${receipt.parentAttemptId ?? '-'}\n'
          'Operation: ${receipt.timelineId ?? '-'}\n'
          'Listing: ${receipt.listingKey}\n'
          'Historical channel: ${receipt.channelFingerprint ?? tr('r11UnknownChannel')}\n'
          '${tr('r11HistoricalOnly')}\n'
          'Package: ${receipt.packageId}\n'
          'Source: ${receipt.sourceHost ?? 'not recorded'}\n'
          'Branch/workflow: ${receipt.sourceBranch ?? '-'} / ${receipt.workflow ?? '-'}\n'
          'Run/attempt/artifact: ${receipt.runId ?? '-'} / ${receipt.runAttempt ?? '-'} / ${receipt.artifactId ?? '-'}\n'
          'Commit: ${receipt.commitSha ?? 'not recorded'}\n'
          'Downloaded digest: ${receipt.downloadSha256 ?? 'not recorded'}\n'
          'Installed signer: ${receipt.installedSignerSha256 ?? 'not verified'}\n'
          'Backend: ${receipt.backend}\n'
          'Files: ${receipt.fileNames.length}\n'
          'Status: ${receipt.stage.name}\n'
          'Verified exact bytes: ${receipt.exactBytesConfirmed ? receipt.verifiedUtc : 'not verified'}\n\n'
          '${_explanation(entry)}';
    }
    if (entry.kind == 'integrity') return entry.reason ?? entry.title;
    final operation = entry.timeline;
    if (operation != null) {
      return 'Operation: ${operation.id}\nKind: ${operation.intent.kind}\n'
          'Listing: ${operation.intent.listingKey}\nRelease: ${operation.intent.release}\n'
          'Parent: ${operation.intent.parentId ?? '-'}\nTransfer: ${operation.transferId ?? '-'}\n'
          'Installation receipt: ${operation.attemptId ?? '-'}\nStage: ${operation.stage}\n'
          'Source checks finished: ${entry.batchCompleted ?? '-'} / ${entry.batchTotal ?? '-'}\n'
          'Reason: ${operation.reason ?? '-'}\nNo installation is confirmed by this timeline.';
    }
    if (entry.kind == 'live') {
      return 'Current provider operation: ${entry.id}\n'
          'Stage: ${entry.stage}\n'
          'This row is live in-memory state, not durable R03/R05 proof.';
    }
    return 'Download fingerprint: ${entry.id}\n'
        'Source: ${entry.sourceHost ?? 'not recorded'}\n'
        'Historical channel: ${_historyChannel(entry) ?? tr('r11UnknownChannel')}\n'
        '${tr('r11HistoricalOnly')}\n'
        'Stage: ${entry.stage}\n'
        'Verified bytes: ${entry.verifiedBytes ?? 'unknown'}\n'
        'Expected total: ${entry.totalBytes ?? 'unknown'}\n'
        'Digest: ${entry.download?.finalDigest ?? 'not verified'}\n\n'
        '${_explanation(entry)}';
  }

  Future<void> _review(R07ActivityRecord entry) async {
    await _refresh(reconcile: true);
    if (!mounted) return;
    await showDialog<void>(context: context, builder: (dialog) => AlertDialog(
      title: Text('Review ${entry.packageId ?? entry.title}'),
      content: SingleChildScrollView(child: SelectableText(_details(entry))),
      actions: [TextButton(onPressed: () => Navigator.pop(dialog),
          child: const Text('Close'))],
    ));
    // R07 cannot safely recreate a consumed Android pending-intent token.
    // A separate retry must be explicitly requested as a fresh attempt.
  }

  Future<void> _resume(R07ActivityRecord entry, AppsProvider provider) async {
    final queued = entry.timeline;
    if (queued != null) {
      if (!_actions(entry, provider).contains(R07ActivityAction.resume)) return;
      final approved = await showDialog<bool>(context: context, builder: (dialog) => AlertDialog(
        title: Text('Continue exact queued ${queued.intent.kind}?'),
        content: const Text('Continue the same persisted operation. Current source identity and all required approval checks still apply.'),
        actions: [TextButton(onPressed: () => Navigator.pop(dialog, false), child: Text(tr('cancel'))),
          FilledButton(onPressed: () => Navigator.pop(dialog, true), child: Text(tr('continue')))],
      ));
      if (!mounted || approved != true || !_actions(entry, provider).contains(R07ActivityAction.resume)) return;
      setState(() => _busy = true);
      try {
        switch (queued.intent.kind) {
          case 'check':
            await provider.checkUpdates(specificIds: [queued.intent.listingKey], resumeQueued: queued);
            break;
          case 'download':
            await provider.downloadApp(provider.apps[queued.intent.listingKey]!.app,
              queuedIntent: queued, allowUserInteraction: true, preserveListingIdentity: true,
              allowExternalContinuation: () => _matchesListing(entry, provider));
            break;
          case 'install':
            await provider.downloadAndInstallLatestApps([queued.intent.listingKey], context, resumeQueued: queued);
            break;
          default:
            throw StateError('Unknown queue kind');
        }
      } catch (_) {
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Queued operation could not continue. Review its exact status.')));
      } finally {
        if (mounted) setState(() { _busy = false; _load(); });
      }
      return;
    }
    final record = entry.download;
    if (record == null || !_actions(entry, provider).contains(R07ActivityAction.resume)) return;
    final approved = await showDialog<bool>(context: context, builder: (dialog) => AlertDialog(
      title: const Text('Resume verified transfer?'),
      content: const Text('Continue the same verified bytes and release. If the server or receipt changed, resume stops without starting a new installation.'),
      actions: [TextButton(onPressed: () => Navigator.pop(dialog, false), child: Text(tr('cancel'))),
        FilledButton(onPressed: () => Navigator.pop(dialog, true), child: Text(tr('continue')))],
    ));
    if (!mounted || approved != true || !_actions(entry, provider).contains(R07ActivityAction.resume)) return;
    final app = provider.apps[entry.listingKey]!.app;
    setState(() => _busy = true);
    try {
      await provider.downloadApp(app, allowUserInteraction: true,
        preserveListingIdentity: true, resumeRecord: record,
        allowExternalContinuation: () => _matchesListing(entry, provider));
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('The retained transfer could not resume. No new install was authorized.')));
    } finally {
      if (mounted) setState(() { _busy = false; _load(); });
    }
  }

  Future<void> _retry(R07ActivityRecord entry, AppsProvider provider) async {
    if (!_actions(entry, provider).contains(R07ActivityAction.retry)) {
      return;
    }
    final key = entry.listingKey;
    if (key == null) return;
    final pending = (await R05OperationJournal.instance.list()).where((x) =>
        x.listingKey == key && x.id != entry.install?.id &&
        (x.stage == R05InstallStage.pending ||
         x.stage == R05InstallStage.awaitingApproval ||
         x.stage == R05InstallStage.handedOff)).toList();
    if (!mounted) return;
    if (pending.isNotEmpty || !_matchesListing(entry, provider)) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Another active attempt or changed listing blocks retry.'),
      ));
      return;
    }
    final approved = await showDialog<bool>(context: context,
      builder: (dialog) => AlertDialog(
        title: const Text('Start a new attempt?'),
        content: const Text('This repeats the normal source download and install flow. It does not resolve or overwrite the previous receipt; Android approvals remain required.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialog, false),
              child: const Text('Not now')),
          FilledButton(onPressed: () => Navigator.pop(dialog, true),
              child: const Text('Continue')),
        ],
      ));
    if (approved != true || !mounted || !_matchesListing(entry, provider)) return;
    setState(() => _busy = true);
    try {
      await provider.downloadAndInstallLatestApps(<String>[key], context, retryParent: entry.install);
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('New attempt could not finish; inspect its recorded status.'),
        ));
      }
    } finally {
      if (mounted) setState(() { _busy = false; _load(); });
    }
  }

  Future<void> _cancel(R07ActivityRecord entry, AppsProvider provider) async {
    if (!_actions(entry, provider).contains(R07ActivityAction.cancel)) return;
    final key = entry.listingKey!;
    if (entry.timeline != null) {
      try {
        await R07OperationTimeline.instance.cancelQueued(entry.timeline!.id);
      } catch (_) {
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Queue ownership changed; no active operation was cancelled.')));
      }
    } else if (entry.kind == 'live') {
      provider.cancelDownload(key);
    } else if (entry.kind == 'install') {
      final unique = await R05OperationJournal.instance.uniqueUnresolved(key);
      if (unique?.id != entry.install?.id || !_matchesListing(entry,provider)) {
        return; // Never cancel another attempt through a listing-only token.
      }
      if (!provider.cancelInstallPreparation(key)) return;
    } else {
      return; // R03 history is not the active provider-owned transfer.
    }
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Cancel requested. Final status still requires confirmation.'),
      ));
      await _refresh();
    }
  }

  Widget _entryTile(R07ActivityRecord entry, AppsProvider provider) {
    final actions = _actions(entry, provider);
    final live = _matchesListing(entry, provider)
        ? provider.apps[entry.listingKey]!.downloadProgress : null;
    // Live bytes are an estimate. Persisted R03 chunks are authoritative;
    // transfer progress never becomes installer confirmation.
    final fraction = entry.progress;
    final label = entry.kind == 'integrity' ? 'History warning' :
        entry.kind == 'download' ? 'Download' :
        entry.kind == 'timeline' ? 'Operation: ${entry.timeline!.intent.kind}' :
        entry.kind == 'live' ? 'Current operation' : 'Installation';
    final status = entry.stage == 'confirmed' ? 'Confirmed on device' :
        entry.stage == 'handedOff' ? 'Android handoff — not confirmed' :
        entry.stage == 'unknown' ? 'Outcome unknown' :
        entry.stage == 'awaitingApproval' ? 'Approval needs review' :
        entry.stage == 'ready' ? 'Verified download ready' : entry.stage;
    Widget action(R07ActivityAction x) {
      final text = switch (x) {
        R07ActivityAction.review => 'Review',
        R07ActivityAction.resume => 'Resume',
        R07ActivityAction.retry => 'Retry',
        R07ActivityAction.cancel => 'Cancel',
        R07ActivityAction.open => 'Open',
        R07ActivityAction.details => 'Details',
      };
      return TextButton(
        key: ValueKey('r07-${x.name}-${entry.id}'),
        onPressed: _busy ? null : () async {
          // Re-check policy at click time; don't act on a stale build.
          if (!_actions(entry, provider).contains(x)) return;
          switch (x) {
            case R07ActivityAction.review:
            case R07ActivityAction.details:
              await _review(entry);
              break;
            case R07ActivityAction.resume:
              await _resume(entry, provider);
              break;
            case R07ActivityAction.retry:
              await _retry(entry, provider);
              break;
            case R07ActivityAction.cancel:
              await _cancel(entry, provider);
              break;
            case R07ActivityAction.open:
              if (_actions(entry, provider).contains(R07ActivityAction.open)) {
                await packageManager.openApp(entry.packageId!);
              }
              break;
          }
        },
        child: Text(text),
      );
    }
    return Card(
      key: ValueKey('r07-record-${entry.id}'),
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Semantics(
            label: '$label ${entry.title}, $status',
            child: ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Icon(entry.stage == 'confirmed' ? Icons.verified_rounded :
                entry.needsReview ? Icons.pending_actions_rounded :
                entry.kind == 'download' ? Icons.download_rounded :
                Icons.receipt_long_rounded),
              title: Text(entry.title, maxLines: 2, overflow: TextOverflow.ellipsis),
              subtitle: Text('$label · $status\n${entry.updatedUtc.toLocal()}'),
              isThreeLine: true,
              onTap: () => _review(entry),
            ),
          ),
          if (entry.kind == 'download') ...[
            if (fraction != null)
              LinearProgressIndicator(value: fraction,
                  semanticsLabel: 'Verified download progress'),
            if (fraction == null && (live != null || !entry.isFinished))
              const LinearProgressIndicator(semanticsLabel: 'Download progress indeterminate'),
            const SizedBox(height: 5),
            Text('Verified ${entry.verifiedBytes ?? 'unknown'} bytes'
              '${entry.totalBytes == null ? ' · Total unknown' : ' / ${entry.totalBytes} bytes'}',
              style: Theme.of(context).textTheme.bodySmall),
          ],
          if (entry.kind == 'live')
            Text('Current app state only; no durable completion claimed.',
                style: Theme.of(context).textTheme.bodySmall),
          if (entry.reason != null || entry.needsReview)
            Padding(padding: const EdgeInsets.symmetric(vertical: 4),
              child: Text(_explanation(entry),
                style: Theme.of(context).textTheme.bodySmall)),
          Wrap(spacing: 4, runSpacing: 4, children: [
            for (final x in R07ActivityAction.values)
              if (actions.contains(x)) action(x),
          ]),
        ]),
      ),
    );
  }

  Future<void> _exportHistory(AppsProvider provider, String channel) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final records = await _catalog.load(trackedPackages: {
        for (final listing in provider.apps.values) listing.listingKey: listing.app.id,
      }, packageId: widget.packageId, listingKey: widget.listingKey,
        operationId: widget.operationId, channel: channel, filter: _filter);
      if (records.any((entry) => entry.kind == 'integrity')) {
        throw StateError('History export scope could not be read completely');
      }
      final data = Uint8List.fromList(utf8.encode(jsonEncode(r11PublicHistory(records))));
      await SharePlus.instance.share(ShareParams(files: [
        XFile.fromData(data, mimeType: 'application/json'),
      ], fileNameOverrides: ['obtainx-history.json']));
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(tr('r11HistoryFailed'))));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _pruneHistory(String selectedChannel, AppsProvider provider) async {
    if (_busy) return;
    final days = await showDialog<int>(context: context, builder: (dialog) => SimpleDialog(
      title: Text(tr('r11Retention')),
      children: [
        Padding(padding: const EdgeInsets.all(16), child: Text(tr('r11RetentionHelp'))),
        for (final days in [30, 90, 365]) SimpleDialogOption(
          onPressed: () => Navigator.pop(dialog, days),
          child: Text(tr('r11RetentionDays', args: ['$days'])),
        ),
        SimpleDialogOption(onPressed: () => Navigator.pop(dialog), child: Text(tr('cancel'))),
      ],
    ));
    if (!mounted || days == null) return;
    final cutoff = DateTime.now().toUtc().subtract(Duration(days: days));
    final channel = selectedChannel == 'all' ? null : selectedChannel;
    setState(() => _busy = true);
    try {
      final preview = await R05OperationJournal.instance.previewTerminalBefore(cutoff,
        listingKey: widget.listingKey, packageId: widget.packageId, channel: channel);
      final transfers = R03DownloadHistory(cache: provider.apkDir);
      final downloadPreview = await transfers.previewTerminalBefore(cutoff,
        listingKey: widget.listingKey, packageId: widget.packageId, channel: channel);
      if (!mounted) return;
      final approved = await showDialog<bool>(context: context, builder: (dialog) => AlertDialog(
        title: Text(tr('r11RetentionConfirm')),
        content: Text('${tr('r11RetentionDays', args: ['$days'])}\n'
          'Package: ${widget.packageId ?? tr('r11AllChannels')}\n'
          'Listing: ${widget.listingKey ?? tr('r11AllChannels')}\n'
          '${channel == null ? tr('r11AllChannels') : channel == 'unknown' ? tr('r11UnknownChannel') : channel}\n'
          '${tr('r11RetentionPreview', args: ['${preview.entries.length}', '${downloadPreview.entries.length}'])}'),
        actions: [TextButton(onPressed: () => Navigator.pop(dialog, false), child: Text(tr('cancel'))),
          FilledButton(onPressed: preview.entries.isEmpty && downloadPreview.entries.isEmpty ? null : () => Navigator.pop(dialog, true), child: Text(tr('delete')))],
      ));
      if (!mounted || approved != true) return;
      var count = 0;
      try {
        count = await R05OperationJournal.instance.pruneTerminalBefore(cutoff,
          listingKey: widget.listingKey, packageId: widget.packageId, channel: channel, preview: preview);
        count += await transfers.prune(downloadPreview);
      } catch (_) {
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Retention stopped after a history change or I/O error. At least $count receipts removed; review the refreshed history.')));
        return;
      }
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(tr('r11RetentionResult', args: ['$count']))));
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(tr('r11HistoryFailed'))));
    } finally {
      if (mounted) setState(() { _busy = false; _load(); });
    }
  }

  @override
  Widget build(BuildContext context) => Consumer<AppsProvider>(
    builder: (context, provider, _) => Scaffold(
      appBar: AppBar(title: Text(widget.packageId == null ?
          'Activity Center' : 'Activity: ${widget.packageId}'), actions: [
        IconButton(tooltip: 'Reconcile installed packages',
          icon: const Icon(Icons.refresh_rounded),
          onPressed: _busy ? null : () => _refresh(reconcile: true)),
      ]),
      body: FutureBuilder<List<R07ActivityRecord>>(
        future: _entries,
        builder: (context, snapshot) {
          if (snapshot.hasError) {
            return Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
              const Text('Activity receipts could not be read. Evidence was not erased.'),
              TextButton(onPressed: () => _refresh(), child: const Text('Retry reading')),
            ]));
          }
          if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
          final warnings = snapshot.data!.where((x) => x.kind == 'integrity').toList();
          final scoped = snapshot.data!.where((x) {
            if (x.kind == 'integrity') return false;
            if (widget.operationId != null && widget.operationId != x.id) return false;
            if (widget.packageId != null && widget.packageId != x.packageId) return false;
            if (widget.listingKey != null && widget.listingKey != x.listingKey) return false;
            return switch (_filter) {
              'review' => x.needsReview,
              'done' => x.isFinished,
              _ => true,
            };
          }).toList();
          final channels = <String>{'all', _channel, ..._catalog.availableChannels, for (final item in scoped)
            if (item.install != null || item.download != null || item.timeline != null) _historyChannel(item) ?? 'unknown'};
          final channel = channels.contains(_channel) ? _channel : 'all';
          final items = scoped.where((x) => channel == 'all' ||
            ((x.install != null || x.download != null || x.timeline != null) && (_historyChannel(x) ?? 'unknown') == channel)).toList();
          final ongoing = items.where((entry) => !entry.isFinished).toList();
          final finished = items.where((entry) => entry.isFinished).toList();
          final visible = [...ongoing, ...finished.take(_historyLimit)];
          final liveCheck = widget.operationId == null &&
              widget.packageId == null && provider.updateCheckCompleter != null;
          return RefreshIndicator(
            onRefresh: () => _refresh(reconcile: true),
            child: CustomScrollView(slivers: [
              SliverToBoxAdapter(child: Column(children: [
                for (final warning in warnings) ListTile(
                  leading: const Icon(Icons.warning_amber_rounded),
                  title: Text(warning.title), subtitle: Text(warning.reason ?? ''),
                ),
                if (liveCheck) ListTile(
                  key: const ValueKey('r07-live-check'),
                  leading: const CircularProgressIndicator(),
                  title: const Text('Checking app sources'),
                  subtitle: Text(() {
                    final activeChecks = items.where((x) => x.timeline?.intent.kind == 'check' && !x.isFinished).toList();
                    if (activeChecks.isEmpty) return 'Preparing durable check queue';
                    final check = activeChecks.first;
                    return '${check.batchCompleted ?? 0} / ${check.batchTotal ?? 0} source checks finished';
                  }()),
                ),
                if (widget.operationId == null) ...[
                  Padding(padding: const EdgeInsets.all(12), child: Text(tr('r11HistoricalOnly'))),
                  Padding(padding: const EdgeInsets.symmetric(horizontal: 12), child: DropdownButton<String>(
                    isExpanded: true, value: channel,
                    items: [for (final value in channels) DropdownMenuItem(value: value,
                      child: Text(value == 'all' ? tr('r11AllChannels') : value == 'unknown'
                        ? tr('r11UnknownChannel') : value, overflow: TextOverflow.ellipsis))],
                    onChanged: _busy ? null : (value) { if (value != null) setState(() {
                      _channel = value; _historyLimit = _pageSize; _load();
                    }); },
                  )),
                  Wrap(spacing: 8, children: [
                    TextButton.icon(onPressed: _busy ? null : () => _exportHistory(provider, channel),
                      icon: const Icon(Icons.share), label: Text(tr('r11ExportHistory'))),
                    if (widget.packageId == null || widget.listingKey != null)
                      TextButton.icon(onPressed: _busy || warnings.isNotEmpty ? null : () => _pruneHistory(channel, provider),
                        icon: const Icon(Icons.delete_outline), label: Text(tr('r11Retention'))),
                  ]),
                ],
                if (widget.operationId == null)
                  Padding(padding: const EdgeInsets.all(8), child: SegmentedButton<String>(
                    showSelectedIcon: false,
                    segments: const [
                      ButtonSegment(value: 'all', label: Text('All')),
                      ButtonSegment(value: 'review', label: Text('Review')),
                      ButtonSegment(value: 'done', label: Text('Finished')),
                    ],
                    selected: {_filter},
                    onSelectionChanged: (value) => setState(() {
                      _filter = value.first; _historyLimit = _pageSize; _load();
                    }),
                  )),
              ])),
              if (items.isEmpty)
                SliverFillRemaining(hasScrollBody: false,
                  child: Center(child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Text(widget.operationId == null ?
                      'No matching activity records. Pull down to recheck.' :
                      'This exact operation was not found. No other attempt was substituted.'),
                  )))
              else SliverList.builder(
                itemCount: visible.length,
                itemBuilder: (context, index) => _entryTile(visible[index], provider),
              ),
              if (finished.length > _historyLimit)
                SliverToBoxAdapter(child: TextButton(
                  onPressed: () => setState(() { _historyLimit += _pageSize; _load(); }),
                  child: Text(tr('r11HistoryMore')),
                )),
            ]),
          );
        },
      ),
    ),
  );
}
