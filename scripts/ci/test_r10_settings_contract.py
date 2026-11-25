"""R10-F01 production navigation/translation and closed-world CI contracts."""
import json
import re
import unittest
from pathlib import Path
import obtainx_ci_policy as policy
ROOT = Path(__file__).resolve().parents[2]

class R10SettingsContract(unittest.TestCase):
    def setUp(self):
        self.page = (ROOT/'lib/pages/settings.dart').read_text()
        self.nav = (ROOT/'lib/widgets/r10_settings_navigation.dart').read_text()
    def test_search_opens_real_section(self):
        for token in ('await showDialog<String>', 'R10SettingsSearchDialog(',
                      'await openSection(key)', 'setSectionExpanded(key, true)',
                      'Scrollable.ensureVisible(anchor', 'if (!await confirmDiscardUnsavedChanges() || !mounted) return;',
                      'setState(() => _selectedCategory = key)',
                      'R10SettingsSearchEntry(category.key, tr(label), category.title)'):
            self.assertIn(token,self.page)
        self.assertIn('Navigator.of(context).pop(entry.section)',self.nav)
        self.assertNotIn('SettingsProvider',self.nav)
        self.assertNotIn('SharedPreferences',self.nav)
    def test_all_existing_sections_reused_and_advanced_grouping(self):
        for key in ('updates','integrations','warnings','sourceSpecific','themes','appearance','interaction','categories','about'):
            self.assertEqual(self.page.count("key: '"+key+"',"),1,key)
        for token in ("_expertSettings = {'integrations', 'warnings', 'sourceSpecific'}",
                      'buildGroupedSections(routine', 'buildGroupedSections(expert',
                      'for (final category in routine) buildCategoryTile(category)',
                      'for (final category in expert) buildCategoryTile(category)',
                      'collapsibleCard(category.key, category.widget)',
                      'selectedCategoryObj.widget', 'R05ExtraApprovalTile()', 'R07ActivityCenterPage()'):
            self.assertIn(token,self.page)
    def test_draft_preservation_and_hidden_controls(self):
        for token in ('ExcludeFocus(', 'ExcludeSemantics(', 'IgnorePointer(ignoring: !expanded',
                      'excluding: !expanded', '(_wasLargeScreen || !_hasUnsavedChanges)',
                      '_sourceSpecificKey.currentState?.discardChanges()',
                      '_integrationsKey.currentState?.discardChanges()'):
            self.assertIn(token,self.page)
    def test_motion_and_wrapping_focus(self):
        for token in ('sp.reduceVisualEffects || MediaQuery.disableAnimationsOf(context)',
                      'reducedMotion ? Duration.zero', 'MediaQuery.textScalerOf(context).scale(16)'):
            self.assertIn(token,self.page)
        for token in ('minHeight: 56','expanded: expanded','selected: selected','focusNode: focusNode',
                      'focusColor:', 'Expanded(child: Text(title', 'Semantics(liveRegion: true'):
            self.assertIn(token,self.nav)
        self.assertNotIn('TextOverflow.ellipsis',self.nav)
        self.assertNotIn('maxLines:',self.nav)
    def test_public_search_labels_exist(self):
        en=json.loads((ROOT/'assets/translations/en.json').read_text())
        labels=self.page.split('static const _searchLabels',1)[1].split('};',1)[0]
        keys=re.findall(r"'([^']+)'",labels)
        sections={'updates','themes','appearance','interaction','warnings','integrations','sourceSpecific','about'}
        self.assertTrue(set(keys)-sections)
        self.assertFalse(set(keys)-sections-en.keys())
        self.assertNotIn('getSettingString(',labels)
        self.assertNotIn('password',labels.lower())
    def test_new_locale_parity(self):
        for lang in ('en','fr','tr','ja','pt','pt-BR'):
            obj=json.loads((ROOT/f'assets/translations/{lang}.json').read_text())
            for key in ('Search','Routine','Expert','NoMatch','SearchHint','ActivityCenter'):
                self.assertTrue(obj['r10Settings'+key].strip(),(lang,key))
    def test_scoped_settings_impact(self):
        plan=policy.impact(['lib/pages/settings.dart','lib/widgets/r10_settings_navigation.dart','scripts/ci/test_r10_settings_contract.py'], 'a'*40,'b'*40,ROOT)
        self.assertTrue(plan['targeted_flutter'])
        self.assertFalse(plan['full_flutter'])
        self.assertFalse(any(plan['lanes'].values()))
        self.assertIn('test/r10_settings_navigation_test.dart',plan['tests'])
        self.assertFalse(plan['full_acceptance_possible'])
