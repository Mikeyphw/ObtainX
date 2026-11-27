/// Bounded, credential-free APKMirror discovery using public listing pages.
/// A missing or blocked response is unknown, not evidence of nonexistence.
library;

import 'package:http/http.dart' as http;
import 'package:obtainium/app_sources/apkmirror.dart';
import 'package:obtainium/http/r08_apkmirror_budget.dart';
import 'package:obtainium/services/html_parse_isolate.dart';

const r08MirrorDiscoveryMaxRequests = 8;
const r08MirrorDiscoveryMaxListings = 3;

Uri? r08MirrorListingUri(Uri candidate) {
  if (!ApkMirrorRequestBudget.appliesTo(candidate)) return null;
  final parts = candidate.pathSegments.where((part) => part.isNotEmpty).toList();
  if (parts.length < 3 || parts.first != 'apk' ||
      parts.skip(1).take(2).any((part) => !RegExp(r'^[a-zA-Z0-9._-]+$').hasMatch(part) || part == '.' || part == '..')) {
    return null;
  }
  return Uri.https('www.apkmirror.com', '/apk/${parts[1]}/${parts[2]}/');
}

Future<List<Uri>> r08MirrorListingCandidates(String html, Uri page) async {
  final doc = await parseHtmlOffIsolate(html);
  final urls = <Uri>{};
  for (final link in doc.querySelectorAll('a[href]')) {
    final href = link.attributes['href'];
    final candidate = href == null ? null : Uri.tryParse(href);
    if (candidate == null) continue;
    final listing = r08MirrorListingUri(page.resolveUri(candidate));
    if (listing != null) urls.add(listing);
    if (urls.length > r08MirrorDiscoveryMaxListings) break;
  }
  return urls.toList();
}

Future<Map<String, String?>> r08DiscoverApkMirror(
    List<String> packages, Future<http.Response> Function(Uri) fetch, {
    Map<String, String?>? hints, Map<String, String>? resolvedIconUrls,
    bool Function()? shouldAbort, void Function(int, int)? onProgress,
    }) async {
  final result = <String, String?>{};
  var remaining = r08MirrorDiscoveryMaxRequests;
  var stopped = false;
  Future<http.Response?> request(Uri uri) async {
    if (remaining == 0 || stopped || shouldAbort?.call() == true) return null;
    remaining--;
    try {
      final response = await fetch(uri);
      if (const {403, 429, 503}.contains(response.statusCode)) stopped = true;
      return response.statusCode == 200 ? response : null;
    } catch (_) {
      // Network, storage, rate or provider errors are not negative matches.
      stopped = true;
      return null;
    }
  }
  onProgress?.call(0, packages.length);
  for (final package in packages.toSet()) {
    if (remaining == 0 || stopped || shouldAbort?.call() == true) break;
    if (!RegExp(r'^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$').hasMatch(package)) continue;
    final search = Uri.https('www.apkmirror.com', '/', {
      'post_type': 'app_release', 'searchtype': 'apk', 's': package,
    });
    final hinted = Uri.tryParse(hints?[package] ?? '');
    final hint = hinted == null ? null : r08MirrorListingUri(hinted);
    final candidates = <Uri>{?hint};
    final page = await request(search);
    if (page != null) candidates.addAll(await r08MirrorListingCandidates(page.body, search));
    final confirmed = <Uri, String?>{};
    var complete = page != null && candidates.length <= r08MirrorDiscoveryMaxListings;
    for (final candidate in candidates.take(r08MirrorDiscoveryMaxListings)) {
      if (remaining == 0 || stopped || shouldAbort?.call() == true) {
        complete = false;
        break;
      }
      final listing = await request(candidate);
      if (listing == null) {
        complete = false;
        continue;
      }
      if (await apkMirrorPackageFromListingPageHtml(listing.body) == package) {
        final raw = await iconUrlFromApkMirrorAppPageHtml(listing.body, candidate.toString());
        final icon = Uri.tryParse(raw ?? '');
        confirmed[candidate] = icon != null && icon.scheme == 'https' &&
            icon.userInfo.isEmpty && icon.host.isNotEmpty ? icon.toString() : null;
      }
    }
    if (complete && !stopped && shouldAbort?.call() != true && confirmed.length == 1) {
      final match = confirmed.entries.single;
      result[package] = match.key.toString();
      if (match.value != null) resolvedIconUrls?[package] = match.value!;
      onProgress?.call(result.length, packages.length);
    }
  }
  return result;
}
