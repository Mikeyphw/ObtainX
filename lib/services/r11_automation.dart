import 'dart:convert';
import 'package:android_intent_plus/android_intent.dart';
import 'package:obtainium/providers/apps_provider.dart';
import 'package:obtainium/providers/settings_provider.dart';
import 'package:obtainium/providers/source_provider.dart';
import 'package:obtainium/services/r05_operation_journal.dart';
import 'package:obtainium/services/r11_external_requests.dart';
import 'package:obtainium/services/r11_history.dart';

/// Foreground, individually consented commands. Check is read-only discovery;
/// download uses the existing persisted transfer engine, never an installer.
Future<Map<String, Object?>> r11RunAutomation(
  AppsProvider provider, SettingsProvider settings,
  R11AutomationRequest request, App selection,
) async {
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
      final fetched = await provider.fetchUpdate(app.listingKey, exactListing: app);
      if (current() == null || fetched == null || fetched.id != app.id) {
        return {'status': 'notAvailable'};
      }
      result['updateAvailable'] = appUpdateIsUserVisible(fetched);
      result['persisted'] = false;
      break;
    case R11AutomationAction.download:
      if (provider.areDownloadsRunning() || provider.updateCheckCompleter != null ||
          app.settings.getBool('trackOnly') || app.allowIdChange || isTempId(app) ||
          app.apkUrls.isEmpty) return {'status': 'refused'};
      final confirmed = InstallReleaseSnapshot.fromApp(selection);
      final actual = InstallReleaseSnapshot.fromApp(app);
      if (!confirmed.belongsTo(app) || confirmed.version != actual.version ||
          confirmed.assetName != actual.assetName || confirmed.assetUrl != actual.assetUrl) {
        return {'status': 'listingChanged'};
      }
      await provider.downloadApp(selection, allowUserInteraction: true,
        preserveListingIdentity: true, allowExternalContinuation: () => current() != null);
      if (current() == null) return {'status': 'listingChanged'};
      result['status'] = 'downloadedNotInstalled';
      break;
    case R11AutomationAction.state:
      final entry = provider.apps[app.listingKey]!;
      result['installed'] = entry.installedInfo?.packageName == app.id;
      result['updateAvailable'] = appUpdateIsUserVisible(app);
      result['busy'] = entry.downloadProgress != null;
      result['observedFrom'] = 'currentLibrary';
      break;
    case R11AutomationAction.receipt:
      final records = await R05OperationJournal.instance.list();
      if (current() == null) return {'status': 'listingChanged'};
      final matching = records.where((r) => r.listingKey == app.listingKey &&
        r.packageId == app.id);
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
