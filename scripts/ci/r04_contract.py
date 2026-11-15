#!/usr/bin/env python3
"""R04 source-native Actions security + CI enforcement contract."""
from __future__ import annotations
import argparse
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def verify(root:Path=ROOT)->int:
    def read(path):return (root/path).read_text(encoding='utf-8')
    service=read('lib/services/r04_github_actions.dart')
    github=read('lib/app_sources/github.dart')
    tests=read('test/r04_github_actions_test.dart')
    flutter=read('.github/workflows/obtainx-r00-flutter.yml')
    contracts=read('.github/workflows/obtainx-r00-contracts.yml')
    policy=read('scripts/ci/obtainx_ci_policy.py')
    docs=read('docs/R04_ACTIONS_CHANNEL.md')
    errors=[]
    def gate(condition,label):
        if not condition:errors.append(label)
    for marker in (
        "repoApi.scheme != 'https'", "repoApi.host != 'api.github.com'",
        "uri.host != repoApi.host", "maximumPages", "page == maximumPages",
        "r['status'] == 'completed'", "r['conclusion'] == 'success'",
        "r['head_branch'] == chosenBranch", "validWorkflows.containsKey",
        "_positiveInt(r['run_attempt'])", "_sha(r['head_sha'])",
        "raw['expired'] != false", "!expires.isAfter(current)",
        "size > maxArchiveBytes", "!isCandidateName(name)",
        "if (matches.length > 1)",
        "repoApi.replace(path: '${repoApi.path}/actions/artifacts/$id/zip')",
        "_artifactDigest(raw['digest'])", "archiveSha256",
        "chosenRunId == null || r['id'] == chosenRunId",
        "throw const R04ActionsFailure('pagination exceeded safe page budget')",
    ):
        gate(marker in service,'service lacks '+marker)
    gate("archiveSha256" in service and "NOT the contained APK" in service,
         'archive digest improperly conflated with APK signing')
    for marker in (
        "r04ModeReleases", "r04ModePrereleases", "r04ModeActions",
        "_fetchR04ActionsDetails(", "R04GitHubActionsCatalog(",
        "r04ArtifactNamePattern", "r04RunId", "r04Workflow", "r04Branch",
        "releaseSettings[r04PrereleaseOnlyKey] = true",
        "additionalSettings[r04PrereleaseOnlyKey] == true",
        "return APKDetails(", "archive.archiveUrl.toString()",
        "not an APK verification", "getAppNames(standardUrl)",
    ):
        gate(marker in github,'GitHub source missing '+marker)
    for marker in (
        "latest successful completed default-branch archive",
        "user branch and workflow ID", "manual run ID",
        "multiple Android archives", "non-Android artifacts",
        "pagination searches across 100-workflow",
        "pagination is fail-closed", "cross-origin API URL",
        "authentication and throttling", "failure and in-progress",
        "archive SHA-256 is not an APK hash",
    ):
        gate(marker in tests,'R04 mock HTTP coverage missing '+marker)
    gate('flutter test --no-pub test/r04_github_actions_test.dart' in flutter,
         'R04 dedicated Dart test missing from hosted Flutter job')
    gate('python3 -B scripts/ci/r04_contract.py --check' in contracts,
         'R04 source contract missing from hosted CI')
    for marker in ("'lib/services/r04_*'", "'lib/app_sources/github.dart'",
                   "'test/r04_*'", "'scripts/ci/r04_*'"):
        gate(marker in policy, 'R04 full CI risk scope missing '+marker)
    gate('return await _fetchR04ActionsDetails(' in github,
         'Actions source mode does not invoke the Actions catalog')
    for workflow_path in (
        '.github/workflows/obtainx-r02-api36.yml',
        '.github/workflows/obtainx-r02-rt02.yml',
        '.github/workflows/obtainx-r02-rt02b.yml',
        '.github/workflows/obtainx-r02-rt02c.yml',
    ):
        workflow=read(workflow_path)
        for marker in ("- 'lib/services/r04_*'", "- 'lib/app_sources/github.dart'",
                       "- 'test/r04_*'", "- 'scripts/ci/r04_*'"):
            gate(marker in workflow, workflow_path+' missing CI path '+marker)
    gate('NOT_QUALIFIED' in docs and 'R05' in docs,
         'R04 docs imply release-level proof without runtime acceptance')
    if errors:
        for error in errors:print('OX_R04_CONTRACT_REFUSED '+error,flush=True)
        return 1
    print('OX_R04_SOURCE_CONTRACT_PASS',flush=True)
    return 0

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args()
    raise SystemExit(verify(args.root))
