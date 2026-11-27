import 'dart:convert';
import 'package:android_intent_plus/android_intent.dart';
import 'package:obtainium/providers/apps_provider.dart';
import 'package:obtainium/providers/settings_provider.dart';
import 'package:obtainium/providers/source_provider.dart';
import 'package:obtainium/services/r05_operation_journal.dart';
import 'package:obtainium/services/r11_external_requests.dart';
import 'package:obtainium/services/r07_operation_timeline.dart';
import 'package:obtainium/services/r11_history.dart';

/// Foreground, individually consented commands. Check is read-only discovery;
/// download queues an exact persisted intent for explicit Activity Center continuation.
/// It performs no transfer or installation from an incoming automation request.
Future<Map<String, Object?>> r11RunAutomation(
  AppsProvider provider, SettingsProvider settings,
  R11AutomationRequest request, App selection, {
  R07OperationTimeline? timeline,
  R05OperationJournal? journal,
  Future<App?> Function(App)? checkSource,
}) async {
  App? current() => settings.r11AutomationEnabled && provider.isForeground
      ? r11ExactLiveListing(provider.apps, selection) : null;
  final app = current();
  if (app == null || app.id != request.package) return {'status': 'refused'};
  final Map<String, Object?> result = {'status': 'ok', 'package': app.id,
    'listing': r11HistoryKey(app.listingKey), 'channel': r11ChannelFingerprint(app)};
  switch (request.action) {
    case R11AutomationAction.check:
      if (provider.updateCheckCompleter != null || provider.areDownloadsRunning()) {
        return {'status': 'busy'};
      }
      final fetched = await (checkSource == null
          ? provider.fetchUpdate(app.listingKey, exactListing: app)
          : checkSource(app));
      if (current() == null || fetched == null || fetched.id != app.id ||
          fetched.listingKey != app.listingKey ||
          r11ChannelFingerprint(fetched) != r11ChannelFingerprint(app)) {
        return {'status': 'notAvailable'};
      }
      result['updateAvailable'] = appUpdateIsUserVisible(fetched);
      result['persisted'] = false;
      break;
    case R11AutomationAction.download:
      if (provider.areDownloadsRunning() || provider.updateCheckCompleter != null ||
          app.settings.getBool('trackOnly') || app.allowIdChange || isTempId(app) ||
          app.apkUrls.isEmpty) {
        return {'status': 'refused'};
      }
      final confirmed = InstallReleaseSnapshot.fromApp(selection);
      final actual = InstallReleaseSnapshot.fromApp(app);
      if (!confirmed.belongsTo(app) || confirmed.version != actual.version ||
          confirmed.assetName != actual.assetName || confirmed.assetUrl != actual.assetUrl) {
        return {'status': 'listingChanged'};
      }
      final queue = timeline ?? R07OperationTimeline.instance;
      final intent = R07OperationIntent(kind: 'download', listingKey: app.listingKey,
        packageId: app.id, channel: r11ChannelFingerprint(app),
        release: downloadReleaseCacheKey(confirmed));
      final entry = (await queue.enqueue([intent])).single;
      final live = current();
      // Consent can be withdrawn during the SQLite write. Cancel only our
      // queued row, never a different request or an active transfer.
      if (live == null || live.settings.getBool('trackOnly') || live.allowIdChange ||
          downloadReleaseCacheKey(InstallReleaseSnapshot.fromApp(live)) != intent.release) {
        await queue.cancelQueued(entry.id);
        return {'status': 'refused'};
      }
      result['status'] = 'queuedNotInstalled';
      result['operation'] = entry.id;
      break;
    case R11AutomationAction.state:
      final entry = provider.apps[app.listingKey]!;
      result['installed'] = entry.installedInfo?.packageName == app.id;
      result['updateAvailable'] = appUpdateIsUserVisible(app);
      result['busy'] = entry.downloadProgress != null;
      result['observedFrom'] = 'currentLibrary';
      break;
    case R11AutomationAction.receipt:
      final records = await (journal ?? R05OperationJournal.instance).list();
      if (current() == null) return {'status': 'listingChanged'};
      final channel = r11ChannelFingerprint(app);
      final matching = records.where((r) => r.listingKey == app.listingKey &&
        r.packageId == app.id && r.channelFingerprint == channel);
      if (matching.isEmpty) return {'status': 'notFound'};
      result['receipt'] = r11PublicReceipt(matching.first);
      break;
  }
  return current() == null ? {'status': 'refused'} : result;
}

/// A request ID is correlation only, not caller authentication. No arbitrary
/// destination, URL, token, version string, filename or filesystem path leaves.
Future<void> r11SendTaskerResult(R11AutomationRequest request,
    Map<String, Object?> result) async {
  await AndroidIntent(action: r11TaskerResultAction, package: r11TaskerPackage,
    arguments: {'request': request.requestId, 'result': jsonEncode(result)}).sendBroadcast();
}
