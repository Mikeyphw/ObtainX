import 'dart:async';
import 'dart:convert';

import 'package:easy_localization/easy_localization.dart';
import 'package:obtainium/app_sources/html.dart';
import 'package:obtainium/components/generated_form_model.dart';
import 'package:obtainium/custom_errors.dart';
import 'package:obtainium/providers/logs_provider.dart';
import 'package:obtainium/providers/source_provider.dart';
import 'package:obtainium/services/html_parse_isolate.dart';

/// Preserve spaces, plus signs, ampersands and Unicode in provider metadata.
Uri farsroidDownloadBoxUri(String postId, String version) => Uri.https(
    'farsroid.com', '/api/download-box/',
    {'post_id': postId, 'post_version': version});

// The public page embeds its download inventory as base64-encoded UTF-8 JSON.
// This is metadata, not authorization or proof of APK identity. Bound both
// the encoded inventory and the number of rows before inspecting asset URLs.
const _farsroidMetadataLimit = 2 * 1024 * 1024;
const _farsroidAssetLimit = 512;

List<MapEntry<String, String>> farsroidPublicAssetLinks(
    Iterable<String> chunks, Uri page) {
  final encoded = StringBuffer();
  for (final chunk in chunks) {
    if (chunk.isEmpty || encoded.length + chunk.length > _farsroidMetadataLimit) {
      throw const FormatException('Invalid Farsroid public inventory size');
    }
    encoded.write(chunk);
  }
  if (encoded.isEmpty) {
    throw const FormatException('Missing Farsroid public inventory');
  }
  final decoded = jsonDecode(utf8.decode(base64Decode(encoded.toString())));
  if (decoded is! List || decoded.length > _farsroidAssetLimit) {
    throw const FormatException('Invalid Farsroid public inventory');
  }
  final assets = <String, String>{};
  for (final row in decoded) {
    if (row is! Map) {
      throw const FormatException('Invalid Farsroid public asset row');
    }
    final raw = row['url'];
    if (raw == null || raw == '') continue;
    if (raw is! String || raw.length > 8192 ||
        RegExp(r'[\\\x00-\x20\x7f]').hasMatch(raw)) {
      throw const FormatException('Invalid Farsroid public asset URL');
    }
    final reference = Uri.tryParse(raw);
    if (reference == null) continue;
    final resolved = page.resolveUri(reference);
    if (resolved.scheme != 'https' || resolved.host.isEmpty ||
        resolved.userInfo.isNotEmpty || resolved.hasFragment ||
        !AppSource.isApkOrContainerFile(resolved.path) ||
        resolved.pathSegments.isEmpty) {
      continue;
    }
    final name = resolved.pathSegments.last;
    if (name.isEmpty || name.contains(RegExp(r'[/\\\x00-\x1f\x7f]'))) continue;
    // Keep absolute signed URLs byte-for-byte, including query ordering.
    final url = reference.hasScheme ? raw : resolved.toString();
    final previous = assets[name];
    if (previous != null && previous != url) {
      throw const FormatException('Conflicting Farsroid public asset identity');
    }
    assets[name] = url;
  }
  return assets.entries.toList();
}

class Farsroid extends AppSource {
  Farsroid() {
    hosts = ['farsroid.com'];
    name = 'Farsroid';
    // 'releaseTitleAsVersion' is offered via the unified versionStringSource
    // dropdown, not a standalone switch (parity with fork main).
    showReleaseTitleAsVersionToggle = true;
  }

  @override
  List<List<GeneratedFormItem>>
  get additionalSourceAppSpecificSettingFormItems => [
    [
      GeneratedFormSwitch(
        'useFirstApkOfVersion',
        label: tr('useFirstApkOfVersion'),
        value: true,
      ),
    ],
  ];

  @override
  String sourceSpecificStandardizeURL(String url, {bool forSelection = false}) {
    return standardizeUrlWithRegex(
      url,
      subdomainPrefix: r'([^\.]+\.)?',
      pathPattern: r'/[^/]+',
    );
  }

  @override
  Future<APKDetails> getLatestAPKDetails(
    String standardUrl,
    Map<String, dynamic> additionalSettings,
  ) async {
    try {
      final String appName = Uri.parse(standardUrl).pathSegments.last;

      final res = await sourceRequest(standardUrl, additionalSettings);
      if (res.statusCode != 200) {
        throw getObtainiumHttpError(res);
      }
      if (res.bodyBytes.length > 8 * 1024 * 1024) {
        throw const FormatException('Farsroid page exceeds metadata budget');
      }
      final html = await parseHtmlOffIsolate(res.body);
      final publicInventory = html.querySelectorAll('#secure-json');
      String version;
      List<MapEntry<String, String>> apkLinks;
      if (publicInventory.isNotEmpty) {
        // Presence of the current format is authoritative. A malformed
        // inventory must not be mistaken for an older successful listing.
        if (publicInventory.length != 1) throw NoReleasesError();
        final page = res.request?.url;
        if (page == null || page.scheme != 'https' || page.userInfo.isNotEmpty ||
            page.port != 443 ||
            !(page.host == 'farsroid.com' || page.host.endsWith('.farsroid.com'))) {
          throw NoReleasesError();
        }
        final versionText = html.querySelector('h3.version-name')?.text.trim();
        if (versionText == null || versionText.isEmpty || versionText.length > 512) {
          throw NoVersionError();
        }
        version = versionText.split(RegExp(r'\s+')).last;
        try {
          apkLinks = farsroidPublicAssetLinks(
            publicInventory.single.querySelectorAll('[data-j]')
                .map((node) => node.attributes['data-j'] ?? ''), page);
        } on FormatException {
          // Do not log malformed metadata or attempt the old endpoint.
          throw NoAPKError();
        }
      } else {
        final dlinks = html.querySelectorAll('.download-links');
        if (dlinks.isEmpty) {
          throw NoReleasesError();
        }
        final postId = dlinks.first.attributes['data-post-id'] ?? '';
        version = dlinks.first.attributes['data-post-version'] ?? '';

        if (postId.isEmpty || version.isEmpty) {
          throw NoVersionError();
        }

        final res2 = await sourceRequest(
          farsroidDownloadBoxUri(postId, version).toString(),
          additionalSettings,
        );
        if (res2.statusCode != 200) {
          throw getObtainiumHttpError(res2);
        }
        if (res2.bodyBytes.length > 8 * 1024 * 1024) {
          throw const FormatException('Farsroid legacy metadata exceeds budget');
        }
        Map<String, dynamic>? farsroidJson;
        try {
          farsroidJson = jsonDecode(res2.body) as Map<String, dynamic>?;
        } catch (e) {
          unawaited(
            LogsProvider().add(
              'Failed to decode Farsroid JSON (${e.runtimeType})',
              level: LogLevel.error,
            ),
          );
          throw NoAPKError();
        }
        final data = farsroidJson?['data'];
        final content = data is Map ? data['content'] : null;
        final html2 = content is String ? content : '';
        if (html2.isEmpty) {
          throw NoAPKError();
        }
        final requestUrl = res2.request?.url;
        if (requestUrl == null) throw NoAPKError();
        apkLinks =
            (await grabLinksCommon(html2, requestUrl, {
                  ...additionalSettings,
                  'skipSort': true,
                }))
                .map((l) => MapEntry(Uri.parse(l.key).pathSegments.last, l.key))
                .toList();
      }

      apkLinks = filterApks(
        apkLinks,
        additionalSettings['apkFilterRegEx'],
        additionalSettings['invertAPKFilter'],
      );
      if (apkLinks.isEmpty) {
        throw NoAPKError();
      }
      if (additionalSettings['autoApkFilterByArch'] == true) {
        apkLinks = await filterApksByArch(apkLinks);
      }
      if (apkLinks.isEmpty) throw NoAPKError();
      if (additionalSettings['useFirstApkOfVersion'] == true) {
        apkLinks = [publicInventory.isEmpty ? apkLinks.first : apkLinks.firstWhere(
          (link) => link.key.toLowerCase().contains(version.toLowerCase()),
          orElse: () => apkLinks.first,
        )];
      }

      if (additionalSettings['releaseTitleAsVersion'] == true) {
        if (apkLinks.length != 1) {
          throw NoVersionError();
        }
        version = apkLinks.single.key;
      }

      return APKDetails(version, apkLinks, AppNames(name, appName));
    } catch (e) {
      rethrowOrWrapError(e);
    }
  }
}
