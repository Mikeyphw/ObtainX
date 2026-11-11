#!/usr/bin/env python3
"""RT02F fail-closed external handoff and targeted CI contracts."""
from __future__ import annotations
import argparse
import re
from pathlib import Path
from obtainx_ci_policy import RISK_GLOBS

ROOT=Path(__file__).resolve().parents[2]
SOURCE='lib/services/third_party_install_evidence.dart'
EXTERNAL='lib/installers/external_installer.dart'
PROVIDER='lib/providers/apps_provider_install.dart'
TEST='test/r02f_external_handoff_test.dart'
FLUTTER='.github/workflows/obtainx-r00-flutter.yml'
SOURCE_CI='.github/workflows/obtainx-r00-contracts.yml'
POLICY='scripts/ci/obtainx_ci_policy.py'
DOC='docs/R02_RT02F_CI_AND_HANDOFF.md'
HEAVY=('.github/workflows/obtainx-r02-api36.yml',
       '.github/workflows/obtainx-r02-rt02.yml',
       '.github/workflows/obtainx-r02-rt02b.yml',
       '.github/workflows/obtainx-r02-rt02c.yml')
PATHS=(SOURCE,EXTERNAL,PROVIDER,TEST,FLUTTER,SOURCE_CI,POLICY,DOC,*HEAVY)

def inspect(root:Path=ROOT)->list[str]:
    problems=[]; txt={}
    for path in PATHS:
        f=root/path
        if not f.is_file() or f.is_symlink():
            problems.append('missing/linked RT02F source '+path);txt[path]=''
        else:txt[path]=f.read_text('utf8')
    def need(ok,msg):
        if not ok:problems.append(msg)
    need('return InstallResult.handedOff();' in txt[SOURCE] and
         'InstallResult.success()' not in txt[SOURCE], 'unverified external success introduced')
    need('classifyUnverifiedThirdPartyHandoff(changed)' in txt[EXTERNAL] and
         'return ok ? InstallResult.success()' not in txt[EXTERNAL],
         'external bridge bypasses unverified handoff classifier')
    provider=txt[PROVIDER]
    a=provider.find('if (result.isHandedOff) {',provider.find('Future<bool> installApkDir('))
    b=provider.find('if (result.isError) {',a)
    block=provider[a:b] if a>=0 and b>a else ''
    need('pendingInstallReleaseKey' in block and
         'if (pending != null)' in block and
         '_awaitThirdPartyInstallConfirmation(dir.appId)' in block,
         'external indicator must not resurrect after broadcast already confirmed pending')
    need('classifyUnverifiedThirdPartyHandoff(true)' in txt[TEST] and
         'classifyUnverifiedThirdPartyHandoff(false)' in txt[TEST] and
         'InstallResult.fromPlatformCode(null)' in txt[TEST],
         'missing cancellation/bridge outcome tests')
    need('flutter test --no-pub test/r02f_external_handoff_test.dart' in txt[FLUTTER],
         'full Flutter gate omitted RT02F regression fixture')
    need('obtainx_ci_policy.py plan' in txt[FLUTTER] and
         'needs.scope.outputs.full_flutter' in txt[FLUTTER] and
         'needs.scope.outputs.targeted_flutter' in txt[FLUTTER],
         'full vs targeted Flutter distinction missing')
    need('python3 -B scripts/ci/r02f_source_contract.py --check' in txt[SOURCE_CI] and
         "branches: [main]" in txt[SOURCE_CI] and
         "'feature/**'" not in txt[SOURCE_CI],
         'source contracts no longer mandatory or feature push duplicate resurrected')
    need('def classify(' in txt[POLICY] and 'run_git' in txt[POLICY] and
         "run_git('merge-base','--is-ancestor'" in txt[POLICY] and 'if not paths and not force:' in txt[POLICY],
         'exact SHA/source-only scope boundary weakened')
    for path in HEAVY:
        data=txt[path]
        need('  pull_request:\n    paths:' in data and
             '  workflow_dispatch:' in data, path+': selective/forced event route missing')
        for key in ('lib/installers/**','lib/providers/apps_provider_install.dart',
                    '.github/workflows/**','integration_test/**',
                    'lib/services/verified_obb_delivery.dart'):
            need("      - '"+key+"'" in data,path+': critical high-risk path missing '+key)
    need('not full Android runtime' in txt[DOC] and 'R03' in txt[DOC] and
         'AuroraStore-Standalone' in txt[DOC], 'scope and roadmap disclosure missing')
    return problems

def main()->int:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true');p.parse_args()
    issues=inspect()
    for item in issues:print('OX_RT02F_CONTRACT_REFUSED:',item)
    if issues:return 1
    print('OX_RT02F_SOURCE_AND_CI_ROUTING_PASS; RUNTIME_MATRIX=NOT_QUALIFIED')
    return 0
if __name__=='__main__':raise SystemExit(main())
