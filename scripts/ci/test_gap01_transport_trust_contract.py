"""GAP-01 static source wiring gates. Real HTTP and policy fixtures run in Flutter CI."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def text(path):return (ROOT/path).read_text()

class Gap01TransportTrust(unittest.TestCase):
 def test_all_shared_redirects_enforce_origin_boundary(self):
  service=text('lib/providers/source_provider.dart').split('class HttpService {',1)[1]
  for marker in ('validateHttpRequestUri(currentUrl)', 'validateHttpRedirect(currentUrl, nextUrl, method,', 'hasBody: postBody != null, insecureTls: insecureTls', 'crossedOrigin = true', 'crossOriginDownloadHeaders(requestHeaders)', '!crossedOrigin', 'r04ValidateArtifactRedirect(currentUrl, nextUrl)', 'request.followRedirects = false'):
   self.assertIn(marker,service)
  self.assertNotIn('crossedOrigin = false;',service.split('while (redirectCount < maxRedirects)',1)[1])
  policy=text('lib/http/origin_redirect_policy.dart')
  for marker in ('a.scheme == b.scheme && a.host == b.host && a.port == b.port', "from.scheme == 'https' && to.scheme != 'https'", 'hasBody ||', 'if (insecureTls)', "name == HttpHeaders.rangeHeader || name == 'if-range'"):
   self.assertIn(marker,policy)
 def test_probes_and_full_download_share_transport(self):
  code=text('lib/providers/apps_provider.dart')
  for fn in ('probeDownloadResponseMetadata','checkPartialDownloadHash','checkETagHeader','getDownloadSize','_downloadFile'):
   self.assertIn('HttpService().sourceRequestStreamResponse(', code.split('> '+fn+'(',1)[1].split('\n}\n',1)[0],fn)
 def test_auth_paths_and_html_asset_binding(self):
  gl=text('lib/app_sources/gitlab.dart');self.assertNotIn('private_token=',gl);self.assertIn("if (pat != null) 'PRIVATE-TOKEN': pat",gl);self.assertIn("sameRequestOrigin(uri, Uri.parse('https://${hosts[0]}'))",gl)
  gh=text('lib/app_sources/github.dart');self.assertIn('_canSendSourceToken(requestUri, additionalSettings)',gh);self.assertIn('sameRequestOrigin(uri, api)',gh)
  self.assertIn('getAssetRequestHeaders(app.additionalSettings, app.url, url)',text('lib/providers/apps_provider_install.dart'))
  self.assertIn("crossedOrigin ? {...additionalSettings, 'requestHeader': []}",text('lib/app_sources/html.dart'))
  vt=text('lib/providers/virustotal_provider.dart');self.assertGreaterEqual(vt.count('followRedirects = false'),2);self.assertIn('!isTrustedUploadUrl(uri)',vt)
 def test_discovery_never_promotes_to_verified(self):
  gh=text('lib/app_sources/github.dart');lookup=gh.split('Future<String> getAttestationStatusForSha256Digest(',1)[1].split('\n  @override',1)[0]
  self.assertNotIn('githubAttestationStatusVerified',lookup);self.assertIn('githubAttestationStatusPresent',lookup);self.assertIn("r'^[a-fA-F0-9]{64}$'",lookup)
  src=text('lib/providers/source_provider.dart');self.assertIn('value == githubAttestationStatusVerified || value == true',src);self.assertNotIn('githubAttestationStatusVerified,',src.split('validGitHubAttestationStatuses = {',1)[1].split('};',1)[0])
 def test_enforce_is_independent_of_pat_and_all_handoffs_guarded(self):
  install=text('lib/providers/apps_provider_install.dart');self.assertIn('_ensureGitHubAttestationPolicy(dir.appId);',install);self.assertIn('_ensureGitHubAttestationPolicy(file.appId);',install)
  for fn,marker in [('installer.installApk(', '_ensureGitHubAttestationPolicy(dir.appId);'),('activeInstaller.installApk(', '_ensureGitHubAttestationPolicy(file.appId);')]:
   prefix=install.split(fn,1)[0];self.assertIn(marker,prefix[-800:])
  gh=text('lib/app_sources/github.dart');self.assertIn('return configuredBuildVerificationMode(additionalSettings);',gh)
  for fn in ('lib/pages/add_app.dart','lib/pages/additional_options_page.dart'):
   self.assertNotIn('canVerifyAttestations',text(fn));self.assertIn('GitHub.configuredBuildVerificationMode',text(fn))
 def test_adversarial_fixtures_are_in_full_test_tree(self):
  t=text('test/gap01_transport_trust_test.dart')
  for marker in ('HttpServer.bind','/return','/cross','/blocked','probeDownloadResponseMetadata','checkPartialDownloadHash','checkETagHeader','getDownloadSize','githubAttestationStatusVerified'):
   self.assertIn(marker,t)
  self.assertIn('Execute full Flutter test suite',text('.github/workflows/obtainx-r00-flutter.yml'))
