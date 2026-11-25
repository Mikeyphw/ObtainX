"""Targeted R08 wiring and CI scope checks; not Dart runtime acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import r07_workflow_contract as workflows

ROOT = Path(__file__).resolve().parents[2]
REQUIRED = {
    'lib/version/version_comparison.dart': ['final shortQualifier = RegExp', "shortQualifier.group(1) == 'a' ? 'alpha' : 'beta'"],
    'lib/version/app_version.dart': ['direct.relation != VersionRelation.newer) {', 'sourceAcknowledged'],
    'lib/providers/source_provider.dart': ['reg.hasMatch(element.key);', 'uri?.pathSegments', 'preferredSourceAbis(abis)', 'sourceAssetHasAbi(element.key, abi)', 'ApkMirrorRequestBudget.shared.request(loadResponse)', 'session.repositoryResponse(key, loadWithBudget'],
    'lib/http/source_request_session.dart': ['int? maxEntries', '_repositoryResponses.length >= maxEntries'],
    'lib/app_sources/fdroid.dart': ['preferredSourceAbis(supportedAbis)'],
    'lib/app_sources/apkmirror.dart': ['previous.url != standardUrl', 'filteredEntries.take(3)', 'filteredEntries.length > 3'],
    'lib/app_sources/apkcombo.dart': ['#best-variant-tab ul.file-list > li', "resolved.queryParametersAll['u']", "resolved.scheme != 'https'"],
    'lib/app_sources/rustore.dart': ['overallInfoResponse.statusCode == 419', 'downloadLinksResponse.statusCode == 419', 'links.length != 1'],
    'lib/app_sources/farsroid.dart': ['farsroidDownloadBoxUri(postId, version).toString()', "'post_version': version", 'data is Map'],
    'lib/pages/home.dart': ['await handleAddUrl(obtainiumAddUrl(uri))', 'IncomingSourceLinkGate()', 'linkGate.accept(uri, DateTime.now())', 'pendingLink = pendingLink.then'],
    'lib/components/version_regex_assist_dialog.dart': ['R10RegexPreview(', 'invert: widget.initialInvert'],
    'lib/components/r10_regex_preview.dart': ["filterApks([MapEntry(sample, '')], request.pattern, request.invert)", 'R10RegexPreviewStatus.ready'],
    'lib/http/r08_apkmirror_budget.dart': ['Duration(seconds: 2)', 'maxQueued = 32', 'await previous', 'retry-after', '_blockedUntil', 'done.complete()'],
    'lib/services/r08_source_policy.dart': ['preferredSourceAbis', 'sourceAssetHasAbi', 'obtainiumAddUrl', "link.queryParametersAll['url']", 'IncomingSourceLinkGate'],
    'test/r08_source_regressions_test.dart': ['#336', '#353', '#363', '#347', '#339', '#333', '#345', '#357', '#368'],
    'docs/R08_SOURCE_RELIABILITY.md': ['419', 'PARTIAL', 'CI24'],
}
FORBIDDEN = {
    'lib/providers/source_provider.dart': ['reg.hasMatch(element.key) || reg.hasMatch(element.value)'],
    'lib/version/app_version.dart': ['direct.relation != VersionRelation.newer &&\n      direct.relation != VersionRelation.same) {'],
    'lib/pages/home.dart': ['var initLinked = false;'],
}
RISK = ('lib/version/**', 'lib/app_sources/**', 'lib/http/r08_*', 'lib/services/r08_*',
        'lib/pages/home.dart', 'lib/components/version_regex_assist_dialog.dart',
        'test/r08_*', 'scripts/ci/r08_*', 'scripts/ci/test_r08_*')
STEPS = {
    'obtainx-r00-contracts.yml': 'python3 -B scripts/ci/r08_contract.py --check',
    'obtainx-r00-flutter.yml': 'flutter test --no-pub test/r08_source_regressions_test.dart',
}

def require(ok, message):
    if not ok: raise ValueError('R08_CONTRACT: ' + message)


def verify(root=ROOT):
    def read(p): return (root/p).read_text(encoding='utf-8')
    for p, tokens in REQUIRED.items():
        source = read(p)
        for token in tokens: require(token in source, p+' missing '+token)
    for p, tokens in FORBIDDEN.items():
        for token in tokens: require(token not in read(p), p+' obsolete branch remains')
    policy = read('scripts/ci/obtainx_ci_policy.py')
    for glob in RISK: require(repr(glob) in policy, 'classifier missing '+glob)
    for name in workflows.WORKFLOWS:
        doc = workflows.parse_workflow(read('.github/workflows/'+name), name)
        if name.startswith('obtainx-r02-'):
            require('paths' not in doc['on']['pull_request'] and 'scope' in doc['jobs'], name+' exact scope route missing')
        if name in STEPS:
            steps = [step for job in doc['jobs'].values() for step in job.get('steps', [])
                     if step.get('run')==STEPS[name]]
            require(len(steps)==1 and 'if' not in steps[0] and steps[0].get('continue-on-error',False) is False,
                    name+' R08 step missing or weakened')
    baseline = json.loads(read('docs/R00_BASELINE.json'))
    require(baseline['roadmap_sha256']==hashlib.sha256((root/'docs/ROADMAP.md').read_bytes()).hexdigest(), 'roadmap digest mismatch')
    require(workflows.verify(root)==6, 'six-workflow policy mismatch')
    return True

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true',required=True);p.parse_args()
    verify();print('OX_R08_SOURCE_WIRING_PASS; DART/HOSTED/DEVICE NOT_ATTESTED')
