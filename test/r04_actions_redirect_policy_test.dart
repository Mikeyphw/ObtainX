import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/services/r04_actions_redirect_policy.dart';

void main() {
  final api = Uri.parse('https://api.github.com/repos/o/r/actions/artifacts/41/zip');
  test('canonical GitHub artifact download and API metadata are distinct', () {
    expect(r04IsCanonicalArtifactDownload(api), isTrue);
    expect(r04IsCanonicalArtifactDownload(Uri.parse('http://api.github.com/repos/o/r/actions/artifacts/41/zip')), isFalse);
    expect(r04IsCanonicalArtifactDownload(Uri.parse('$api?token=secret')), isFalse);
    expect(r04IsCanonicalArtifactDownload(Uri.parse('https://attacker.invalid/repos/o/r/actions/artifacts/41/zip')), isFalse);
    expect(r04IsActionsMetadataApi(Uri.parse('https://api.github.com/repos/o/r/actions/runs')), isTrue);
  });

  test('signed object-store HTTPS redirects accepted without broad subdomains', () {
    for (final host in ['pipelines.actions.githubusercontent.com',
      'objects.githubusercontent.com', 'productionresults.blob.core.windows.net']) {
      r04ValidateArtifactRedirect(api, Uri.parse('https://$host/temporary?sig=safe'));
    }
    for (final uri in [
      'https://githubusercontent.com.attacker.invalid/signed',
      'https://blob.core.windows.net.attacker.invalid/a',
      'http://objects.githubusercontent.com/download',
      'https://user:pass@objects.githubusercontent.com/a',
      'https://example.com/a',
    ]) {
      expect(() => r04ValidateArtifactRedirect(api, Uri.parse(uri)),
        throwsA(isA<R04ActionsRedirectFailure>()));
    }
  });

  test('PAT, cookie, proxy auth and custom secrets never reach artifact host', () {
    final result = r04ArtifactStorageHeaders({
      HttpHeaders.authorizationHeader: 'Bearer sensitive',
      HttpHeaders.cookieHeader: 'session=sensitive',
      'Proxy-Authorization': 'Basic sensitive',
      'X-Private-Token': 'sensitive',
      'X-GitHub-Api-Version': '2026-03-10',
      HttpHeaders.acceptHeader: 'application/vnd.github+json',
      HttpHeaders.rangeHeader: 'bytes=3-',
      'If-Range': 'etag',
    });
    expect(result[HttpHeaders.authorizationHeader], isNull);
    expect(result[HttpHeaders.cookieHeader], isNull);
    expect(result['Proxy-Authorization'], isNull);
    expect(result['X-Private-Token'], isNull);
    expect(result[HttpHeaders.acceptHeader], 'application/octet-stream');
    expect(result[HttpHeaders.rangeHeader], 'bytes=3-');
    expect(result['if-range'], 'etag');
    expect(result.values.join('|'), isNot(contains('sensitive')));
  });
}
