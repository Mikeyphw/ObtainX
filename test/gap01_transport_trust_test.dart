import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/app_sources/github.dart';
import 'package:obtainium/app_sources/gitlab.dart';
import 'package:obtainium/http/origin_redirect_policy.dart';
import 'package:obtainium/providers/apps_provider.dart';
import 'package:obtainium/providers/settings_provider.dart';
import 'package:obtainium/providers/source_provider.dart';
import 'package:obtainium/providers/virustotal_provider.dart';

class _RealHttp extends HttpOverrides {}

class _GitHub extends GitHub {
  @override
  Future<String?> getTokenIfAny(Map<String, dynamic> settings) async => 'fixture-secret';
}

class _GitLab extends GitLab {
  @override
  Future<String?> getPATIfAny(Map<String, dynamic> settings) async => 'fixture-secret';
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const secretHeaders = <String, String>{
    'Authorization': 'Bearer fixture-secret',
    'X-Vendor-Secret': 'fixture-secret',
    'Cookie': 'sid=fixture-secret',
    'User-Agent': 'fixture-secret',
    'Referer': 'https://example.invalid/fixture-secret',
    'Proxy-Authorization': 'fixture-secret',
  };
  test('real shared transport strips all custom credentials across origins, including return hops and probes', () async {
    await HttpOverrides.runWithHttpOverrides(() async {
      final a = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      final b = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      addTearDown(() async { await a.close(force: true); await b.close(force: true); });
      final originA = 'http://127.0.0.1:${a.port}';
      final originB = 'http://127.0.0.1:${b.port}';
      final seen = <String, List<Map<String, String>>>{};
      void record(HttpRequest request) {
        final headers = <String, String>{};
        request.headers.forEach((name, values) => headers[name] = values.join(','));
        (seen[request.uri.path] ??= []).add(headers);
      }
      Future<void> redirect(HttpRequest req, String target) async {
        req.response.statusCode = 307;
        req.response.headers.set(HttpHeaders.locationHeader, target);
        await req.response.close();
      }
      a.listen((req) async {
        record(req);
        switch (req.uri.path) {
          case '/start':
            req.response.cookies.add(Cookie('sameOrigin', 'fixture-secret'));
            await redirect(req, '/same');
          case '/same':
            await redirect(req, '$originB/cross');
          case '/post':
            await req.drain<void>();
            await redirect(req, '$originB/blocked');
          default:
            req.response.headers.set('etag', 'fixture-etag');
            req.response.contentLength = 4;
            req.response.add([1, 2, 3, 4]);
            await req.response.close();
        }
      });
      b.listen((req) async {
        record(req);
        req.response.cookies.add(Cookie('fromB', 'fixture-secret'));
        await redirect(req, '$originA/return');
      });
      final service = HttpService();
      final response = await service.request('GET', Uri.parse('$originA/start'),
        {...secretHeaders, 'Range': 'bytes=0-3', 'If-Range': 'fixture-etag'});
      expect(response.statusCode, 200);
      expect(response.bodyBytes, [1, 2, 3, 4]);
      expect(seen['/same']!.single['authorization'], 'Bearer fixture-secret');
      expect(seen['/same']!.single['cookie'], contains('sameOrigin=fixture-secret'));
      final metadata = await probeDownloadResponseMetadata('$originA/start', headers: secretHeaders);
      expect(metadata?.finalUri.toString(), '$originA/return');
      expect(await checkPartialDownloadHash('$originA/start', 4, headers: secretHeaders), startsWith('sha256:4:'));
      expect(await checkETagHeader('$originA/start', headers: secretHeaders), isNotNull);
      expect(await getDownloadSize('$originA/start', headers: secretHeaders), 4);
      for (final hop in ['/cross', '/return']) {
        expect(seen[hop], hasLength(5));
        for (final headers in seen[hop]!) {
          expect(headers.values.join(' '), isNot(contains('fixture-secret')));
          expect(headers['authorization'], isNull);
          expect(headers['cookie'], isNull);
          expect(headers['x-vendor-secret'], isNull);
        }
        expect(seen[hop]!.first['range'], 'bytes=0-3');
        expect(seen[hop]!.first['if-range'], 'fixture-etag');
      }
      await expectLater(service.request('POST', Uri.parse('$originA/post'), secretHeaders,
        postBody: {'credential': 'fixture-secret'}), throwsFormatException);
      expect(seen['/blocked'], isNull);
    }, _RealHttp());
  });

  test('origin policy rejects scheme downgrade, invalid destinations and cross-origin bodies or insecure TLS', () {
    final origin = Uri.parse('https://example.test/a');
    expect(sameRequestOrigin(origin, Uri.parse('https://example.test:443/b')), isTrue);
    expect(sameRequestOrigin(origin, Uri.parse('https://example.test:8443/b')), isFalse);
    expect(sameRequestOrigin(origin, Uri.parse('https://other.test/b')), isFalse);
    expect(sameRequestOrigin(origin, Uri.parse('http://example.test/b')), isFalse);
    for (final dest in ['http://example.test/b', 'https://user:pass@example.test/b', 'file:///tmp/a']) {
      expect(() => validateHttpRedirect(origin, Uri.parse(dest), 'GET'), throwsFormatException);
    }
    final other = Uri.parse('https://other.test/a');
    expect(() => validateHttpRedirect(origin, other, 'GET', hasBody: true), throwsFormatException);
    expect(() => validateHttpRedirect(origin, other, 'GET', insecureTls: true), throwsFormatException);
  });

  test('GitLab header stays on service origin and no token is injected into asset URL', () async {
    final source = _GitLab();
    expect((await source.getRequestHeaders({}, 'https://gitlab.com/api/v4/projects'))?['PRIVATE-TOKEN'], 'fixture-secret');
    for (final url in ['http://gitlab.com/a', 'https://gitlab.com:8443/a', 'https://gitlab.com.evil.test/a', 'https://storage.test/a']) {
      expect(await source.getRequestHeaders({}, url), isNull);
      expect(await source.assetUrlPrefetchModifier(url, 'https://gitlab.com/a/b', {}), url);
    }
  });

  test('enforce stays blocked for every discovery result, including legacy verified, without PAT', () {
    final source = _GitHub();
    final settings = SettingsProvider();
    for (final status in [null, githubAttestationStatusVerified, githubAttestationStatusPresent,
      githubAttestationStatusUnsupported, githubAttestationStatusError]) {
      final app = App(id: 'org.example.app', name: 'App', author: 'Example',
        url: 'https://github.com/example/app', latestVersion: '2.0', preferredApkIndex: 0,
        latestAttestationStatus: status,
        additionalSettings: {GitHub.buildVerificationModeKey: GitHub.buildVerificationEnforce});
      expect(githubAttestationEnforcementBlocksInstall(app, source, settings), isTrue);
      expect(githubAttestationEnforcementBlocksInstall(app.copyWith(additionalSettings: {
        GitHub.buildVerificationModeKey: GitHub.buildVerificationAudit}), source, settings), isFalse);
    }
    expect(githubAttestationStatusFromJsonValue(true), githubAttestationStatusError);
    expect(githubAttestationStatusFromJsonValue('verified'), githubAttestationStatusError);
    expect(GitHub.configuredBuildVerificationMode({GitHub.enforceAttestationsKey: true}), GitHub.buildVerificationEnforce);
  });

  test('VirusTotal upload destination must match exact HTTPS service', () {
    expect(VirusTotalScanner.isTrustedUploadUrl(Uri.parse('https://www.virustotal.com/api/v3/files')), isTrue);
    for (final url in ['http://www.virustotal.com/a', 'https://www.virustotal.com:8443/a',
      'https://www.virustotal.com.evil.test/a', 'https://user@www.virustotal.com/a']) {
      expect(VirusTotalScanner.isTrustedUploadUrl(Uri.parse(url)), isFalse);
    }
  });
}
