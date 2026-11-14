#!/usr/bin/env python3
"""Check the six mandatory hosted installer workflows against one source policy.

Pure source checks: no GitHub API, no Android, no Flutter/Gradle. In CI, this
runs before expensive device work. A missing/skipped run is never qualification.
"""
from __future__ import annotations
import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = 'scripts/ci/obtainx_ci_required_workflows.json'
SCOPE = 'scripts/ci/obtainx_ci_policy.py'
CONTRACTS = '.github/workflows/obtainx-r00-contracts.yml'
ANDROID = (
    '.github/workflows/obtainx-r02-api36.yml',
    '.github/workflows/obtainx-r02-rt02.yml',
    '.github/workflows/obtainx-r02-rt02b.yml',
    '.github/workflows/obtainx-r02-rt02c.yml',
)
REQUIRED = (
    ('ObtainX R00 / Source and Contract Integrity', '.github/workflows/obtainx-r00-contracts.yml'),
    ('ObtainX R00 / Hosted Flutter Qualification', '.github/workflows/obtainx-r00-flutter.yml'),
    ('ObtainX R02 / API 36 Hosted Emulator Bootstrap', ANDROID[0]),
    ('ObtainX R02 / RT02 Real System Installer API36', ANDROID[1]),
    ('ObtainX R02 / RT02B Negative Installer API36', ANDROID[2]),
    ('ObtainX R02 / RT02C Archive-to-Installer API36', ANDROID[3]),
)
GROUPS = (
    'scripts/ci/r02f_p02_*',
    'scripts/ci/r02f_p03_*',
    'scripts/ci/r02f_p04b_*',
    'scripts/ci/r02f_p04_*',
    'lib/services/r02f_p04_backend_availability.dart',
    'scripts/ci/r02g_*',
)

def read(root: Path, name: str) -> str:
    f = root / name
    if not f.is_file() or f.is_symlink() or f.stat().st_size > 100_000:
        raise ValueError('missing, symlinked or oversized source: ' + name)
    return f.read_text('utf-8')

def inspect(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        p = json.loads(read(root, POLICY))
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError) as e:
        return ['invalid mandatory workflow policy: ' + type(e).__name__]
    expected_workflows = [dict(name=name, path=path, scope='required') for name,path in REQUIRED]
    if (type(p) is not dict or set(p) != {'schema','purpose','path_groups','workflows','qualification'}
        or p.get('schema') != 1 or p.get('workflows') != expected_workflows
        or p.get('path_groups') != list(GROUPS)):
        errors.append('policy workflow inventory/order or risk path drift')
    q = p.get('qualification') if isinstance(p,dict) else None
    expected_q = dict(require_all_exact_head_success=True, missing_is_not_qualified=True,
                      failure_is_not_qualified=True, release_qualified=False,
                      physical_device_qualified=False)
    if type(q) is not dict or q != expected_q:
        errors.append('policy weakens exact-head success or qualification scope')
    for name,path in REQUIRED:
        try:
            w=read(root,path)
        except (ValueError,OSError,UnicodeError) as e:
            errors.append(str(e)); continue
        if not w.startswith('name: '+name+'\n'):
            errors.append('workflow display name drift: '+path)
        if '  pull_request:' not in w or '  workflow_dispatch:' not in w:
            errors.append('workflow trigger missing: '+path)
        if 'permissions:\n  contents: read' not in w:
            errors.append('workflow permissions changed: '+path)
        if path in ANDROID:
            for glob in GROUPS:
                if w.count("      - '"+glob+"'") != 1:
                    errors.append('Android PR path coverage missing/duplicated: '+path+' '+glob)
            if "      - '.github/workflows/**'" not in w:
                errors.append('workflow policy edits do not trigger Android gate: '+path)
            if "github.event_name != 'pull_request'" not in w:
                errors.append('Android event safety gate changed: '+path)
    try:
        s=read(root,SCOPE)
        for glob in GROUPS:
            if s.count("    '"+glob+"',") != 1:
                errors.append('scope router lacks high-risk installer path: '+glob)
        if 'full = bool(force or risky or unknown)' not in s:
            errors.append('scope router high-risk decision modified')
        cs=read(root,CONTRACTS)
        if cs.count('python3 -B scripts/ci/obtainx_ci6_contract.py --check') != 1:
            errors.append('mandatory R00 CI6 source check missing')
    except (ValueError,OSError,UnicodeError) as e:
        errors.append(str(e))
    return errors

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--check',action='store_true')
    ap.parse_args()
    issues=inspect()
    for item in issues: print('OX_CI6_REFUSED '+item,file=sys.stderr)
    if issues: return 2
    print('OX_CI6_REQUIRED_SIX_WORKFLOW_POLICY_PASS; hosted runtime not performed',flush=True)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
