import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:obtainium/app_sources/apkcombo.dart';
import 'package:obtainium/app_sources/farsroid.dart';
import 'package:obtainium/app_sources/rustore.dart';
import 'package:obtainium/custom_errors.dart';
import 'package:obtainium/http/r08_apkmirror_budget.dart';
import 'package:obtainium/providers/source_provider.dart';
import 'package:obtainium/services/r08_source_policy.dart';
import 'package:obtainium/services/r08_apkmirror_discovery.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:obtainium/version/app_version.dart';

class _ComboFixture extends APKCombo {
  _ComboFixture(this.html);
  final String html;
  @override
  Future<http.Response> sourceRequest(String url, Map<String, dynamic> settings,
      {bool followRedirects = true, Object? postBody}) async =>
      http.Response(html, 200, request: http.Request('GET', Uri.parse(url)));
}

class _RuStoreRejected extends RuStore {
  @override
  Future<String?> tryInferringAppId(String standardUrl,
      {Map<String, dynamic> additionalSettings = const {}}) async => 'com.example';
  @override
  Future<http.Response> sourceRequest(String url, Map<String, dynamic> settings,
      {bool followRedirects = true, Object? postBody}) async =>
      http.Response('<html>expired</html>', 419);
}

class _FarsroidFixture extends Farsroid {
  final seen = <Uri>[];
  @override
  Future<http.Response> sourceRequest(String url, Map<String, dynamic> settings,
      {bool followRedirects = true, Object? postBody}) async {
    final uri = Uri.parse(url);
    seen.add(uri);
    return http.Response(seen.length == 1
      ? '<div class="download-links" data-post-id="12" data-post-version="1+2&amp;β"></div>'
      : jsonEncode({'data': {'content': '<a href="https://example.org/app.apk">APK</a>'}}),
      200, request: http.Request('GET', uri), headers: {'content-type': 'text/html; charset=utf-8'});
  }
}

class _FarsroidPublicFixture extends Farsroid {
  _FarsroidPublicFixture(this.html);
  final String html;
  int requests = 0;
  @override
  Future<http.Response> sourceRequest(String url, Map<String, dynamic> settings,
      {bool followRedirects = true, Object? postBody}) async {
    requests++;
    if (requests != 1) throw StateError('Unexpected legacy fallback');
    return http.Response(html, 200, request: http.Request('GET', Uri.parse(url)),
      headers: {'content-type': 'text/html; charset=utf-8'});
  }
}

String _farsroidPublicPage(String encoded) {
  final middle = encoded.length ~/ 2;
  return '<h3 class="version-name">نسخه 2.4</h3>'
      '<div id="secure-json"><span data-j="${encoded.substring(0, middle)}"></span>'
      '<span data-j="${encoded.substring(middle)}"></span></div>'
      '<div class="download-links" data-post-id="1" data-post-version="0.1"></div>';
}

const _farsroidSettings = <String, dynamic>{
  'apkFilterRegEx': '', 'invertAPKFilter': false, 'autoApkFilterByArch': false,
  'useFirstApkOfVersion': true,
};

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  test('GAP-04 independent owners persist server cooldown and pacing', () async {
    final root = await Directory.systemTemp.createTemp('mirror-budget-');
    addTearDown(() => root.delete(recursive: true));
    var now = DateTime.utc(2026, 11, 26);
    ApkMirrorRequestBudget makeBudget() => ApkMirrorRequestBudget(
      clock: () => now, wait: (duration) async { now = now.add(duration); },
      privateRoot: () async => root);
    final first = makeBudget();
    final starts = <DateTime>[];
    Future<http.Response> load() async {
      expect(ApkMirrorRequestBudget.ownsRequest, isTrue);
      starts.add(now);
      return http.Response('', 200);
    }
    final entered = Completer<void>();
    final finish = Completer<void>();
    final pending = first.request(() async {
      entered.complete();
      await finish.future;
      return load();
    });
    await entered.future;
    final other = makeBudget().request(load);
    expect(starts, isEmpty);
    finish.complete();
    await Future.wait([pending, other]);
    expect(starts.last.difference(starts.first), const Duration(seconds: 2));
    await makeBudget().request(() async => http.Response('', 429,
      headers: {'retry-after': '120'}));
    await expectLater(makeBudget().request(load), throwsA(isA<ApkMirrorRequestDeferred>()));
    now = now.add(const Duration(seconds: 120));
    await makeBudget().request(load);
    await expectLater(makeBudget().request(() async => throw StateError('connection lost')),
      throwsStateError);
    await expectLater(makeBudget().request(load), throwsA(isA<ApkMirrorRequestDeferred>()));
    expect(starts.length, 3);
    now = now.add(const Duration(minutes: 5));
    await File('${root.path}/apkmirror-budget-v1/state.json').writeAsString('{broken');
    await expectLater(makeBudget().request(load), throwsFormatException);
    expect(starts.length, 3);
  });
  test('GAP-04 mirror discovery verifies exact listing and rejects unrelated origin', () async {
    final seen = <Uri>[];
    final icons = <String, String>{};
    final result = await r08DiscoverApkMirror(['com.example.app'], (uri) async {
      seen.add(uri);
      if (uri.path == '/') {
        expect(uri.queryParameters['s'], 'com.example.app');
        return http.Response('<a href="https://evil.test/apk/a/b/">bad</a>'
          '<a href="/apk/company/app/release/">app</a>', 200);
      }
      expect(uri.toString(), 'https://www.apkmirror.com/apk/company/app/');
      return http.Response('<meta property="og:image" content="https://downloadr2.apkmirror.com/app.png">'
        '<a title="View on Play Store" href="https://play.google.com/store/apps/details?id=com.example.app">Play</a>', 200);
    }, resolvedIconUrls: icons);
    expect(seen.length, 2);
    expect(result, {'com.example.app': 'https://www.apkmirror.com/apk/company/app/'});
    expect(icons['com.example.app'], 'https://downloadr2.apkmirror.com/app.png');
  });
  test('GAP-04 blocked or ambiguous mirror pages remain unknown', () async {
    var calls = 0;
    final refused = await r08DiscoverApkMirror(['com.example.app', 'com.example.other'], (uri) async {
      calls++;
      return http.Response('', 403);
    }, hints: {'com.example.app': 'https://www.apkmirror.com/apk/company/app/'});
    expect(refused, isEmpty);
    expect(calls, 1);
    final ambiguous = await r08DiscoverApkMirror(['com.example.app'], (uri) async =>
      http.Response(uri.path == '/' ? '<a href="/apk/a/b/">1</a><a href="/apk/a/c/">2</a>' :
        '<a title="View on Play Store" href="https://play.google.com/store/apps/details?id=com.example.app">Play</a>', 200));
    expect(ambiguous, isEmpty);
    final bounded = <Uri>[];
    await r08DiscoverApkMirror(List.generate(50, (i) => 'com.example.p$i'), (uri) async {
      bounded.add(uri);
      return http.Response('', 200);
    });
    expect(bounded.length, r08MirrorDiscoveryMaxRequests);
  });
  test('GAP-04 Farsroid actual metadata path parses fixture and preserves query', () async {
    final source = _FarsroidFixture();
    final details = await source.getLatestAPKDetails('https://farsroid.com/example/', {
      'apkFilterRegEx': '', 'invertAPKFilter': false, 'autoApkFilterByArch': false,
      'useFirstApkOfVersion': true,
    });
    expect(source.seen.length, 2);
    expect(source.seen.last.queryParameters, {'post_id': '12', 'post_version': '1+2&β'});
    expect(details.version, '1+2&β');
    expect(details.apkUrls.single.value, 'https://example.org/app.apk');
  });
  test('FINAL-AUDIT-03 Farsroid public inventory preserves signed URL and selects version', () async {
    const signed = 'https://cdn.example.org/app-2.4.apk?z=%2B&token=a%2fb';
    final encoded = base64Encode(utf8.encode(jsonEncode([
      {'url': '/files/app-2.3.apk'},
      {'url': signed}, {'url': signed},
      {'url': 'http://cdn.example.org/unsafe.apk'},
      {'url': 'https://user@cdn.example.org/unsafe.apk'},
      {'url': 'https://cdn.example.org/image.png?name=fake.apk'},
    ])));
    final provider = _FarsroidPublicFixture(_farsroidPublicPage(encoded));
    final result = await provider.getLatestAPKDetails('https://farsroid.com/example/', _farsroidSettings);
    expect(provider.requests, 1);
    expect(result.version, '2.4');
    expect(result.apkUrls.single.key, 'app-2.4.apk');
    expect(result.apkUrls.single.value, signed);
    final all = await _FarsroidPublicFixture(_farsroidPublicPage(encoded))
        .getLatestAPKDetails('https://farsroid.com/example/',
            {..._farsroidSettings, 'useFirstApkOfVersion': false});
    expect(all.apkUrls.map((asset) => asset.value), [
      'https://farsroid.com/files/app-2.3.apk', signed,
    ]);
  });
  test('FINAL-AUDIT-03 invalid public inventory never falls back', () async {
    for (final encoded in ['!!!!', base64Encode(utf8.encode('{"url":"a.apk"}')),
      base64Encode(utf8.encode(jsonEncode([
        {'url': 'https://cdn.example.org/app.apk?a=1'},
        {'url': 'https://cdn.example.org/app.apk?a=2'},
      ]))), base64Encode(utf8.encode(jsonEncode(List.filled(513, {'url': null}))))]) {
      final provider = _FarsroidPublicFixture(_farsroidPublicPage(encoded));
      await expectLater(provider.getLatestAPKDetails('https://farsroid.com/example/', _farsroidSettings), throwsA(isA<NoAPKError>()));
      expect(provider.requests, 1);
    }
  });
  test('FINAL-AUDIT-03 public inventory bounds and type checks', () {
    final page = Uri.parse('https://farsroid.com/app/');
    expect(() => farsroidPublicAssetLinks([List.filled(2 * 1024 * 1024 + 1, 'A').join()], page), throwsFormatException);
    expect(() => farsroidPublicAssetLinks([base64Encode(utf8.encode('[42]'))], page), throwsFormatException);
    expect(farsroidPublicAssetLinks([base64Encode(utf8.encode(jsonEncode([
      {'url': 'https://cdn.example.org/file.apk#fragment'},
      {'url': 'https://cdn.example.org/file.jpg?apk=.apk'},
    ])))], page), isEmpty);
  });
  test('#336 Mozilla beta and alpha have numeric prerelease order', () {
    expect(compareVersionStrings('158.0b3', '158.0b4').relation,
        VersionRelation.older);
    expect(compareVersionStrings('158.0b4', '158.0').relation,
        VersionRelation.older);
    expect(compareVersionStrings('158.0a9', '158.0b1').relation,
        VersionRelation.older);
  });
  test('#353 filters asset label, not host or signed query', () {
    final rows = [const MapEntry('app.apk', 'https://github.com/a/app.apk?token=debug')];
    expect(filterApks(rows, 'github.com', true), rows);
    expect(filterApks(rows, 'debug', false), isEmpty);
    expect(filterApks(rows, r'\.apk$', false), rows);
  });
  test('#363 compatible ARM64 is preferred even if ARMv7 listed first', () async {
    const supported = ['armeabi-v7a', 'arm64-v8a'];
    expect(preferredSourceAbis(supported), ['arm64-v8a', 'armeabi-v7a']);
    expect(preferredSourceAbis(['armeabi-v7a']), ['armeabi-v7a']);
    expect(sourceAssetHasAbi('app-x86_64.apk', 'x86'), isFalse);
    final rows = [const MapEntry('app-armeabi-v7a.apk', 'https://example.org/a'),
      const MapEntry('app-arm64-v8a.apk', 'https://example.org/b')];
    expect(await ApkFilterService().filterApksByArch(rows, supported), [rows.last]);
  });
  test('#347 exact source acknowledgement overrides equal-name code tie-break', () {
    const url = 'https://f-droid.org/packages/net.osmand.plus/';
    const filename = 'net.osmand.plus_541003.apk';
    const asset = 'https://f-droid.org/repo/$filename';
    const app = App(id: 'net.osmand.plus', url: url, author: 'OsmAnd',
        name: 'OsmAnd', installedVersion: '5.4.10', latestVersion: '5.4.10',
        apkUrls: [MapEntry(filename, asset)], preferredApkIndex: 0,
        additionalSettings: {'versionDetection': 'standard', 'trackOnly': true,
          observedPackageIdKey: 'net.osmand.plus', observedVersionNameKey: '5.4.10',
          observedVersionCodeKey: 5410});
    final withCodes = app.copyWith(additionalSettings: {...app.additionalSettings,
      sourceVersionCodesKey: {'sourceUrl': url, 'overrideSource': app.overrideSource,
        'version': '5.4.10', 'codes': {filename: 541003}, 'assetUrls': {filename: asset}}});
    expect(versionDecisionForApp(withCodes).reason, 'selectedApkCode');
    final acknowledged = acknowledgeSourceRelease(withCodes);
    expect(acknowledged.installedVersion, '5.4.10');
    expect(versionDecisionForApp(acknowledged).reason, 'sourceAcknowledged');
    final changed = acknowledged.copyWith(additionalSettings: {...acknowledged.additionalSettings,
      observedVersionCodeKey: 5411});
    expect(versionDecisionForApp(changed).reason, isNot('sourceAcknowledged'));
  });
  test('#339 paced requests and server cooldown do not send extra HTTP', () async {
    var now = DateTime.utc(2026, 11, 24);
    final starts = <DateTime>[];
    final budget = ApkMirrorRequestBudget(clock: () => now,
      wait: (duration) async { now = now.add(duration); });
    Future<http.Response> ok() async { starts.add(now); return http.Response('rss', 200); }
    await Future.wait([budget.request(ok), budget.request(ok)]);
    expect(starts.last.difference(starts.first), const Duration(seconds: 2));
    await budget.request(() async => http.Response('', 429, headers: {'retry-after': '120'}));
    await expectLater(budget.request(ok), throwsA(isA<ApkMirrorRequestDeferred>()));
    expect(starts.length, 2);
    now = now.add(const Duration(seconds: 120));
    await budget.request(ok);
    expect(starts.length, 3);
    expect(ApkMirrorRequestBudget.appliesTo(Uri.parse('https://apkmirror.com.evil.org/a')), isFalse);
  });
  test('#333 single variant fallback preserves signed APKS URL', () async {
    const url = 'https://example.org/app.apks?sig=abc';
    final encoded = Uri.encodeQueryComponent(url);
    final source = _ComboFixture('<div id="best-variant-tab"><ul class="file-list">'
      '<li><a href="/r2?u=$encoded">Download</a></li></ul></div>');
    final rows = await source.getApkUrls('https://apkcombo.com/stremio/com.stremio.one', {});
    expect(rows.single.value, url);
    expect(rows.single.key, 'app.apks');
  });
  test('#345 rejected RuStore session is actionable, not JSON or success', () async {
    await expectLater(_RuStoreRejected().getLatestAPKDetails('https://rustore.ru/catalog/app/com.example', {}),
      throwsA(isA<ObtainiumError>().having((e) => e.message, 'message', contains('419'))));
  });
  test('#357 Farsroid query encoding preserves the exact provider version', () {
    final uri = farsroidDownloadBoxUri('12', '1+2&β');
    expect(uri.queryParameters, {'post_id': '12', 'post_version': '1+2&β'});
  });
  test('#368 decode outer add link exactly once and keep distinct warm links', () {
    const url = 'https://github.com/a/b?x=%2F&y=two';
    final cold = Uri.parse('obtainium://add/${Uri.encodeComponent(url)}');
    final warm = Uri.parse('obtainium://add?url=${Uri.encodeQueryComponent("https://example.org/b")}');
    expect(obtainiumAddUrl(cold), url);
    expect(obtainiumAddUrl(warm), 'https://example.org/b');
    expect(() => obtainiumAddUrl(Uri.parse('obtainium://add?url=file:///etc/a')), throwsFormatException);
    expect(() => obtainiumAddUrl(Uri.parse('obtainium://add?url=a&url=b')), throwsFormatException);
    final gate = IncomingSourceLinkGate();
    final now = DateTime.utc(2026, 11, 24);
    expect(gate.accept(cold, now), isTrue);
    expect(gate.accept(cold, now), isFalse);
    expect(gate.accept(warm, now), isTrue);
    expect(gate.accept(warm, now.add(const Duration(seconds: 6))), isTrue);
  });
}
