"""Source wiring evidence, not Flutter runtime acceptance."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

class SettingsContextContract(unittest.TestCase):
    def read(self, path):
        return (ROOT/path).read_text()
    def test_reset_staged_and_protected(self):
        page = self.read('lib/pages/additional_options_page.dart')
        reset = page.split('Future<void> _resetDraft()',1)[1].split('Future<void> _onSave()',1)[0]
        for token in ('showDialog<bool>', 'confirmed != true', 'r10ResetOptionDraft(', '_formRevision++', '_sourceDefaults'):
            self.assertIn(token, reset)
        self.assertNotIn('saveApps(',reset)
        self.assertIn('key: ValueKey(_formRevision)', page)
        helper = self.read('lib/components/r10_settings_context.dart')
        keys = helper.split('const r10ResettableOptionKeys',1)[1].split('};',1)[0]
        for field in ('trackOnly','overrideSource','githubPAT','enforceAttestations','enableVirusTotalScan'):
            self.assertNotIn(repr(field),keys)
        self.assertIn('item.password || item.required',helper)
        self.assertIn('item.disabledOptKeys?.contains(defaultValue)',helper)
    def test_real_preview_route(self):
        dialog = self.read('lib/components/version_regex_assist_dialog.dart')
        preview = self.read('lib/components/r10_regex_preview.dart')
        for token in ('_effectivePatch()', 'widget.patch(patch)', 'R10RegexPreview(', 'initialInvert', 'initialMatchGroup'):
            self.assertIn(token,dialog)
        for token in ('Isolate.spawn(', 'Isolate.immediate', 'Duration(seconds: 1)', 'Duration(milliseconds: 180)', 'generation != _generation', 'extractVersion(request.pattern, request.group, sample)', "filterApks([MapEntry(sample, '')]", '.take(40)'):
            self.assertIn(token,preview)
        self.assertNotIn('http.get(',preview)
    def test_contextual_help_routes_and_locale_parity(self):
        routes = {
          'lib/pages/settings.dart': ['r10InstallerExplanationKey(sp.installerMode)', 'r10TokenHint', 'r10ProxyTokenHint', 'r10VirusTotalHint'],
          'lib/pages/add_app.dart': ['r10SourceOverrideHint'],
          'lib/pages/app.dart': ['r10CertificateHint'],
          'lib/components/app_detail_widgets.dart': ['r10CertificateHint'],
          'lib/components/version_regex_assist_dialog.dart': ['r10VersionDetectionHint','r10VersionSourceHint'],
        }
        for path,tokens in routes.items():
            for token in tokens: self.assertIn(token,self.read(path))
        paths = list(routes) + ['lib/components/r10_regex_preview.dart','lib/components/r10_settings_context.dart','lib/pages/additional_options_page.dart']
        keys = {k for path in paths for k in re.findall(r"'(r10[A-Z][A-Za-z]+)'",self.read(path))}
        for lang in ('en','fr','ja','tr','pt','pt-BR'):
            data=json.loads(self.read('assets/translations/'+lang+'.json'))
            for key in keys: self.assertTrue(data[key].strip(),(lang,key))
            self.assertEqual(data['r10RegexCount'].count('{}'),2)
