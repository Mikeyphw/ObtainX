"""Production wiring and locale evidence, not Flutter runtime acceptance."""
import collections
import json
import re
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]

def read(path): return (ROOT/path).read_text()
def locale(lang): return json.loads(read(f'assets/translations/{lang}.json'))
def flatten(data, prefix=''):
    for key, value in data.items():
        if isinstance(value, dict): yield from flatten(value, prefix+key+'.')
        else: yield prefix+key, value

def placeholders(text): return collections.Counter(re.findall(r'\{[^{}]*\}', text))

class R10Accessibility(unittest.TestCase):
    def test_swipe_production_and_persistence(self):
        settings=read('lib/providers/settings_provider.dart')
        self.assertIn('enum SwipeAction { update, pin, appOptions, delete, open, appInfo, edit, none, openSource }', settings)
        self.assertIn('SwipeAction.values[raw.clamp(0, SwipeAction.none.index)]',settings)
        apps=read('lib/pages/apps.dart')
        for token in ('_swipeThreshold.update(_dragOffset', 'context.read<SettingsProvider>().selectionClick()', 'R10SwipeThreshold.direction(_dragOffset', 'r10OpenSourceHomepage(app.url)', 'customSemanticsActions:', 'PopupMenuButton<SwipeAction>', 'widget.leftAction || action == widget.rightAction'):
            self.assertIn(token, apps)
        helper=read('lib/components/r10_accessibility.dart')
        self.assertIn("{'http', 'https'}",helper)
        self.assertIn('uri.userInfo.isNotEmpty',helper)
        self.assertIn('LaunchMode.externalApplication',helper)
    def test_custom_semantics_action_import(self):
        apps=read('lib/pages/apps.dart')
        self.assertIn("import 'package:flutter/semantics.dart' show CustomSemanticsAction;", apps)
        self.assertIn('CustomSemanticsAction(label: _actionLabel(action))', apps)
        self.assertIn('customSemanticsActions:', apps)
    def test_nav_focus_and_layout(self):
        home=read('lib/pages/home.dart')
        for token in ('R10NavigationStrip(', 'R10NavigationTarget(', 'ExcludeFocus(', 'ExcludeSemantics(', 'reduceMotion: reduceMotion', 'scrollable: true', 'r10SettingsActivityCenter'):
            self.assertIn(token,home)
        self.assertNotIn('FittedBox(fit: BoxFit.scaleDown, child: compositeRow)',home)
        helper=read('lib/components/r10_accessibility.dart')
        for token in ('minWidth: 48, minHeight: 48','Scrollable.ensureVisible', 'MediaQuery.disableAnimationsOf', 'constraints.maxWidth < 360 * textScale'):
            self.assertIn(token,helper)
        self.assertIn('itemHeight: null',read('lib/components/app_dropdown_field.dart'))
        self.assertIn('textScaler: mediaQuery.textScaler',read('lib/app_ui_scaling.dart'))
        app=read('lib/pages/app.dart')
        for token in ('R10PrimaryActions(', 'r10-open-source-homepage', 'r10OpenSourceHomepage(app.app.url)', 'r10CopyCertificate'):
            self.assertIn(token,app)
    def test_locale_audit_is_exact(self):
        report=json.loads(read('docs/R10_LOCALE_REVIEW.json'))
        en=dict(flatten(locale('en')))
        self.assertEqual(report['english_leaf_keys'],len(en))
        for lang, result in report['locales'].items():
            data=dict(flatten(locale(lang))); shared=en.keys() & data.keys()
            self.assertEqual(result['missing'],sorted(en.keys()-data.keys()))
            self.assertEqual(result['extra'],sorted(data.keys()-en.keys()))
            self.assertEqual(result['placeholder_mismatches'],[k for k in sorted(shared) if placeholders(en[k]) != placeholders(data[k])])
            self.assertEqual(result['blank'],[k for k in sorted(shared) if not data[k].strip()])
            self.assertFalse(result['placeholder_mismatches']);self.assertFalse(result['blank'])
        for lang in ('en','fr','ja','tr','pt','pt-BR'):
            for key in report['new_labels']:
                self.assertTrue(locale(lang)[key].strip())
        self.assertIn('useFallbackTranslations: true',read('lib/main.dart'))
