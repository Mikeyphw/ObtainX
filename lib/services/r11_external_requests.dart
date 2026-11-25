import 'dart:convert';
import 'package:android_intent_plus/android_intent.dart';
import 'package:crypto/crypto.dart';
import 'package:obtainium/providers/apps_provider.dart';
import 'package:obtainium/providers/source_provider.dart';

/// External identifiers refer to Android packages, never listing-key aliases.
/// Only bounded, syntactically valid package names enter the library resolver.
bool r11ValidPackage(String value) => value.length <= 255 &&
    RegExp(r'^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$')
        .hasMatch(value);

String? r11PackageFromLink(Uri uri) {
  if (uri.scheme != 'obtainium' || uri.host != 'open' ||
      uri.userInfo.isNotEmpty || uri.hasPort || uri.hasFragment ||
      (uri.path.isNotEmpty && uri.path != '/')) {
    return null;
  }
  final fields = uri.queryParametersAll;
  final ids = fields['id'];
  if (fields.length != 1 || ids == null || ids.length != 1 ||
      !r11ValidPackage(ids.single)) {
    return null;
  }
  return ids.single;
}

/// Snapshot only the identity needed to revalidate the user's selection.
/// Never return an arbitrary first match for a multi-source package.
List<App> r11PackageListings(AppListings listings, String package) =>
    r11ValidPackage(package)
        ? List<App>.unmodifiable(
            listings.listingsForPackage(package).map((entry) => entry.app.deepCopy()),
          )
        : const [];

App? r11ExactLiveListing(AppListings listings, App selected) {
  if (!listings.containsListingKey(selected.listingKey)) return null;
  final live = listings[selected.listingKey]?.app;
  if (live == null || live.id != selected.id || live.url != selected.url ||
      live.overrideSource != selected.overrideSource ||
      r11ChannelFingerprint(live) != r11ChannelFingerprint(selected)) {
    return null;
  }
  return live;
}

const r11TaskerPackage = 'net.dinglisch.android.taskerm';
const r11TaskerResultAction = 'dev.bikram.obtainx.AUTOMATION_RESULT';
const r11AppManagerPackage = 'io.github.muntashirakon.AppManager';

enum R11AutomationAction { check, download, state, receipt }

class R11AutomationRequest {
  const R11AutomationRequest(this.package, this.action, this.requestId);
  final String package;
  final R11AutomationAction action;
  final String requestId;

  static R11AutomationRequest? parse(Uri uri) {
    if (uri.scheme != 'obtainium' || uri.host != 'automation' ||
        uri.userInfo.isNotEmpty || uri.hasPort || uri.hasFragment ||
        (uri.path.isNotEmpty && uri.path != '/')) return null;
    final fields = uri.queryParametersAll;
    if (fields.length != 3 || fields.values.any((v) => v.length != 1)) {
      return null;
    }
    final package = fields['id']?.single;
    final action = fields['action']?.single;
    final request = fields['request']?.single;
    if (package == null || !r11ValidPackage(package) || request == null ||
        !RegExp(r'^[A-Za-z0-9_-]{1,64}$').hasMatch(request)) return null;
    for (final value in R11AutomationAction.values) {
      if (value.name == action) return R11AutomationRequest(package, value, request);
    }
    return null;
  }
}

/// Channel binding is independent of a release/run and never exports raw URLs.
String r11ChannelFingerprint(App app) => sha256.convert(utf8.encode(jsonEncode([
  app.url, app.overrideSource, app.additionalSettings['r04GitHubSourceMode'],
  app.additionalSettings['r04Branch'], app.additionalSettings['r04Workflow'],
  app.additionalSettings['includePrereleases'],
  app.additionalSettings['r04PrereleasesOnly'],
  app.additionalSettings['r04ArtifactNamePattern'],
  app.additionalSettings['filterReleaseTitlesByRegEx'],
  app.additionalSettings['filterAPKByRegEx'],
  app.additionalSettings['versionExtractionRegEx'],
]))).toString();

/// Only the known exported App Manager package is ever addressed. Implicit
/// app-manager links can otherwise be intercepted by an unrelated handler.
Future<bool> r11OpenAppManager(String package) async {
  if (!r11ValidPackage(package)) return false;
  final intent = AndroidIntent(
    action: 'android.intent.action.SHOW_APP_INFO',
    package: r11AppManagerPackage,
    arguments: {'android.intent.extra.PACKAGE_NAME': package},
  );
  try {
    if (await intent.canResolveActivity() != true) return false;
    await intent.launch();
    return true;
  } catch (_) {
    return false;
  }
}
