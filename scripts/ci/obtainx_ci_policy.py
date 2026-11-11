#!/usr/bin/env python3
"""ObtainX PR scope router: targeted checks vs exact-SHA full Android gates.

Inspired by AuroraStore-Standalone's targeted+full gate split. Unlike Aurora's
integrated master branch, ObtainX has stacked PRs, so compare exact PR BASE and
HEAD. A skipped heavy workflow is NOT runtime qualification.
"""
from __future__ import annotations
import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHA = re.compile(r'^[0-9a-f]{40}$')
RISK_GLOBS = (
    'lib/installers/**',
    'lib/providers/apps_provider_install.dart',
    'lib/providers/apps_provider_updates.dart',
    'lib/providers/installer_provider.dart',
    'lib/providers/external_install_bridge.dart',
    'lib/services/install_bundle_plan.dart',
    'lib/services/verified_obb_delivery.dart',
    'lib/services/artifact_file_work.dart',
    'integration_test/**',
    'android/**',
    '.github/workflows/**',
    'scripts/ci/r02_rt02**',
    'scripts/ci/obtainx_ci_policy.py',
    'scripts/ci/*optimization*',
    'scripts/ci/r00_source_contract.py',
    'pubspec.yaml',
    'pubspec.lock',
    'docs/SECURITY_RELEASE_POLICY.md',
)

def classify(paths: list[str], *, force: bool = False) -> dict:
    if not paths and not force:
        raise ValueError('empty change inventory cannot be marked safe')
    if any(not p or p.startswith('/') or '\\' in p or p.split('/').count('..')
           for p in paths):
        raise ValueError('invalid changed-file inventory')
    risky = sorted(p for p in paths if any(fnmatch.fnmatchcase(p, g) for g in RISK_GLOBS))
    dart = sorted(p for p in paths if p.endswith('.dart') and p.startswith(('lib/', 'test/', 'integration_test/')))
    unknown = sorted(p for p in paths if p.startswith('.github/') and not p.startswith('.github/workflows/'))
    # Unknown configuration is conservative; never accidentally skip compilation.
    full = bool(force or risky or unknown)
    targeted = bool(dart) and not full
    return {'full_flutter':full,'targeted_flutter':targeted,'source_contracts':True,
            'risk_paths':risky + unknown,'changed_files':len(paths),
            'reason':'manual' if force else ('high-risk' if full else ('dart-targeted' if targeted else 'source-only'))}

def run_git(*args: str, root: Path = ROOT) -> bytes:
    p = subprocess.run(['git', *args],cwd=root,stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    if p.returncode:
        raise RuntimeError('CI_SCOPE_REFUSED: git command failed: ' + ' '.join(args[:2]))
    return p.stdout

def paths_between(base: str, head: str, *, root: Path = ROOT) -> list[str]:
    if not SHA.fullmatch(base) or not SHA.fullmatch(head) or base == head:
        raise ValueError('CI_SCOPE_REFUSED: invalid or identical source SHAs')
    actual=run_git('rev-parse','HEAD',root=root).decode().strip()
    if actual != head:
        raise RuntimeError('CI_SCOPE_REFUSED: checkout not exact expected HEAD')
    run_git('merge-base','--is-ancestor',base,head,root=root)
    raw=run_git('diff','--name-only','-z','--no-renames',base,head,root=root)
    paths=[x.decode('utf8','strict') for x in raw.split(b'\0') if x]
    if not paths:
        raise RuntimeError('CI_SCOPE_REFUSED: no changed files')
    return paths

def run_targeted_flutter(paths: list[str]) -> None:
    plan=classify(paths)
    if not plan['targeted_flutter']:
        raise RuntimeError('CI_SCOPE_REFUSED: targeted Flutter not selected')
    subprocess.run(['flutter','analyze','integration_test','lib','test'],check=True)
    selected=sorted({p for p in paths if p.startswith('test/') and
                     p.endswith('_test.dart') and (ROOT / p).is_file()})
    if not selected:
        selected=['test/installed_version_reconciliation_test.dart',
                  'test/r02_install_bundle_plan_test.dart']
    for path in selected:
        subprocess.run(['flutter','test','--no-pub',path],check=True)
    print('OX_CI_TARGETED_FLUTTER_PASS: '+str(len(selected))+' tests; full Android NOT qualified',flush=True)

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['plan','run-flutter'])
    parser.add_argument('--base',required=True)
    parser.add_argument('--head',required=True)
    parser.add_argument('--manual',action='store_true')
    parser.add_argument('--github-output')
    a=parser.parse_args()
    changed=paths_between(a.base,a.head)
    result=classify(changed,force=a.manual)
    print('OX_CI_SCOPE_PLAN: '+json.dumps(result,sort_keys=True),flush=True)
    if a.command=='run-flutter':
        run_targeted_flutter(changed)
        return 0
    if a.github_output:
        with open(a.github_output,'a',encoding='utf8') as output:
            for field in ('full_flutter','targeted_flutter'):
                output.write(field+'='+str(result[field]).lower()+'\n')
    return 0

if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (ValueError,RuntimeError,subprocess.CalledProcessError) as e:
        print('OX_CI_SCOPE_REFUSED: '+str(e),file=sys.stderr)
        raise SystemExit(1)
