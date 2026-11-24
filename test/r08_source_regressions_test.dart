import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:obtainium/app_sources/apkcombo.dart';
import 'package:obtainium/app_sources/farsroid.dart';
import 'package:obtainium/app_sources/rustore.dart';
import 'package:obtainium/custom_errors.dart';
import 'package:obtainium/http/r08_apkmirror_budget.dart';
import 'package:obtainium/providers/source_provider.dart';
import 'package:obtainium/services/r08_source_policy.dart';
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

void main() {
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
    final app = App(id: 'net.osmand.plus', url: url, author: 'OsmAnd',
        name: 'OsmAnd', installedVersion: '5.4.10', latestVersion: '5.4.10',
        apkUrls: [const MapEntry(filename, asset)], preferredApkIndex: 0,
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
