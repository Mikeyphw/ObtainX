"""R09 source wiring and fail-closed CI routing; no Dart/runtime attestation."""
from pathlib import Path
import argparse, hashlib, json
import r07_workflow_contract as workflows
import obtainx_ci_policy as policy
ROOT = Path(__file__).resolve().parents[2]
REQUIRED = {
    'lib/pages/apps.dart': ('r09MatchesSearch(filter.searchQuery', 'r09PackageGroups(listedApps.map', 'r09ListingState(', 'AppsListGroupBy.package', "tr('r09CheckVisible')", 'getMassObtainFunction(updatesOnly: true)', "tr('r09EverythingCurrent')", "tr('r09ViewPresets')", 'searchQuery: _searchQuery.text.trim()', 'installedInfo?.versionName'),
    'lib/folders/app_folder.dart': ('r09MatchesSearch(searchQuery', "'searchQuery': searchQuery", "searchQuery: json['searchQuery']"),
    'lib/components/bulk_update_sheet.dart': ('r09SafeBulkSelection(selectedIds, packageByListing)', 'r09SelectListing(selectedIds, appId, packageByListing)', 'r09SafeBulkSelection({...selectedIds, ...groupIds}', 'r09ConflictingListings'),
    'lib/providers/apps_provider_install.dart': ('r09ChooseArtifact(urlsToSelectFrom', 'r09ActionsEligible(asset', 'r09SafeBulkSelection(appIds, packages)', 'r09ArtifactChoice(appFileUrl.key', 'downloadOnly: pickAnyAsset).eligible)) {\n      return null;\n    }'),
    'lib/components/app_detail_widgets.dart': ('r09ChooseArtifact(urlsToSelectFrom', 'r09ArtifactChoice(asset.key', 'r09ActionsEligible(asset', 'RadioGroup<int>', 'enabled: choice(entry.value).eligible', 'r09TrackedPackage', 'r09ZipDigest'),
    'lib/services/r09_discovery.dart': ('r04ValidateArchiveIdentity(', 'isConfigurationSplitApk(name)', 'hints.any(supportedAbis.contains)', 'preferredSourceAbis(abis)', 'counts[packageByListing[id]]'),
    'lib/services/r04_actions_archive_integrity.dart': ('final expected = r04ValidateArchiveIdentity(', 'expiresAt == null || !expiresAt.isAfter(now.toUtc())', 'sha256.bind(archive.openRead())'),
    'lib/widgets/r04_actions_history_dialog.dart': ('readOnly: true', 'enabled: !busy', 'if (row.canSelectAt(now())) {', 'Navigator.of(context).pop(row);\n                                } else {\n                                  setState(() {});', 'rows = const []; searched = false'),
    'lib/app_sources/github.dart': ("values['r09BoundSourceUrl']", 'repositoryUrl != boundRepository', 'chosen.canSelectAt(DateTime.now())'),
    'lib/components/generated_form_renderer.dart': ('formState.assistSourceUrl == boundUrl', "'r09BoundSourceUrl': ?boundUrl"),
    'lib/pages/add_app.dart': ('assistSourceUrl:',),
    'lib/pages/additional_options_page.dart': ('assistSourceUrl:',),
    'test/needs_attention_group_test.dart': ('R09 groups two sources by package', 'group.count, 2', 'r09CheckVisible', 'r09UpdateAll'),
    'test/r04_actions_history_test.dart': ('R09 history cannot select an expired artifact', 'readOnly, isTrue', 'clock = DateTime.utc(2026, 11, 19)'),
    'test/r09_discovery_test.dart': ('without URL secrets', 'smart folder search round trips', 'competing installable sources', 'wrong ABI and configuration splits', 'safe default respects eligible', 'exact repository, identity and expiry gate', 'distinguish actual recorded facts'),
}
RISK = ('lib/pages/apps.dart','lib/providers/settings_provider.dart','lib/folders/**','lib/components/bulk_update_sheet.dart','lib/components/app_detail_widgets.dart','lib/pages/additional_options_page.dart','lib/widgets/r04_actions_history_dialog.dart','lib/services/r09_*','test/r09_*','scripts/ci/r09_*','scripts/ci/test_r09_*','assets/translations/en.json')
STEPS = {'obtainx-r00-contracts.yml':'python3 -B scripts/ci/r09_contract.py --check','obtainx-r00-flutter.yml':'flutter test --no-pub test/r09_discovery_test.dart test/needs_attention_group_test.dart'}
def require(ok, label):
    if not ok: raise ValueError('R09: '+label)
def verify(root=ROOT):
    def read(path): return (root/path).read_text(encoding='utf-8')
    for path, tokens in REQUIRED.items():
        code=read(path)
        for token in tokens: require(token in code, path+' missing '+token)
    for glob in RISK: require(repr(glob) in read('scripts/ci/obtainx_ci_policy.py'), 'classifier missing '+glob)
    for name in workflows.WORKFLOWS:
        doc=workflows.parse_workflow(read('.github/workflows/'+name),name)
        if name.startswith('obtainx-r02-'):
            require('paths' not in doc['on']['pull_request'] and 'scope' in doc['jobs'], name+' exact scope route missing')
        if name in STEPS:
            rows=[s for j in doc['jobs'].values() for s in j.get('steps',[]) if s.get('run')==STEPS[name]]
            require(len(rows)==1 and 'if' not in rows[0] and rows[0].get('continue-on-error',False) is False, name+' weakened R09 gate')
    require(workflows.verify(root)==6,'six required workflows')
    baseline=json.loads(read('docs/R00_BASELINE.json'))
    require(baseline['roadmap_sha256']==hashlib.sha256((root/'docs/ROADMAP.md').read_bytes()).hexdigest(),'roadmap digest')
    return True
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true',required=True);p.parse_args()
    verify();print('OX_R09_SOURCE_WIRING_PASS; DART/HOSTED/DEVICE NOT_ATTESTED')
