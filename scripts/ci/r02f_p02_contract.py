#!/usr/bin/env python3
"""RT02F P02: source-gated API36 real session abandonment, not UI cancellation."""
from __future__ import annotations
import argparse
import ast
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
HOST='scripts/ci/r02f_p02_session_abandon.py'
TEST='scripts/ci/test_r02f_p02_contract.py'
WORKFLOW='.github/workflows/obtainx-r02-rt02c.yml'
SOURCE='.github/workflows/obtainx-r00-contracts.yml'
DOC='docs/R02_RT02F_P02_SESSION_ABANDON.md'
PATHS=(HOST,TEST,WORKFLOW,SOURCE,DOC)

def inspect(root:Path=ROOT)->list[str]:
    errors=[]; data={}
    for p in PATHS:
        file=root/p
        if not file.is_file() or file.is_symlink():
            errors.append('missing/linked P02 file '+p);data[p]=''
        else:data[p]=file.read_text('utf8')
    host=data[HOST];wf=data[WORKFLOW]
    anchors={
        HOST:("CASES = (('standalone', ('base_v2.apk',))",
              "('split', ('base_v2.apk', 'config.x86_64.apk'))",
              'base.host_check()', 'rt02c.verify(out)',
              'rt02c.baseline_v1(fixtures)',
              "base.adb('shell','pm','install-create'",
              "base.adb('shell','pm','install-write'",
              "base.adb('shell','pm','install-abandon'",
              "base.adb('shell','sha256sum'",
              'after==before', '0<total<16*1024*1024',
              "'installer_session_abandoned':True",
              "'install_commit_called':False",
              "'installer_confirmation_count':0",
              "'app_ui_cancel_qualified':False",
              "'other_installer_backends_qualified':False",
              "'physical_device_qualified':False",
              'def verify(out: Path) -> int:',
              "'status':'PASS_TWO_ABANDONED_ANDROID_SESSIONS'",
              'if __name__==\'__main__\':raise SystemExit(main())'),
        TEST:('test_contract_accepts_exact_source','test_cancel_session_parsing_negative',
              'test_source_mutation_rejected','test_contract_refuses_missing_emulator_script'),
        WORKFLOW:('python3 -B scripts/ci/r02_rt02c_hosted.py run --out',
                  'python3 -B scripts/ci/r02f_p02_session_abandon.py run --out',
                  'python3 -B scripts/ci/r02_rt02c_hosted.py verify --out',
                  'python3 -B scripts/ci/r02f_p02_session_abandon.py verify --out',
                  'r02f-p02-session-abandon.json',
                  'ReactiveCircus/android-emulator-runner@a421e43855164a8197daf9d8d40fe71c6996bb0d',
                  'if: always()',
                  'permissions:\n  contents: read'),
        SOURCE:('python3 -B scripts/ci/r02f_p02_contract.py --check',
                "python3 -m unittest discover -s scripts/ci -p 'test_*.py' -v"),
        DOC:('RT02F P02','API36','app UI cancellation remains unqualified',
             'physical-device','Gradle cache','R03'),
    }
    for rel,needles in anchors.items():
        for needle in needles:
            if needle not in data[rel]:errors.append(rel+': missing protected evidence '+needle)
    try:
        ast.parse(host)
        ast.parse(data[TEST])
    except SyntaxError:
        errors.append('RT02F P02 host or mutation test syntax invalid')
    # Existing RT02C runs first in the same emulator and remains mandatory.
    if not re.search(r"script: bash -c 'set -euo pipefail; python3 -B scripts/ci/r02_rt02c_hosted.py run --out [^\n]+; python3 -B scripts/ci/r02f_p02_session_abandon.py run --out",wf):
        errors.append('RT02F abandonment must run after RT02C in the SAME fail-closed emulator')
    if wf.count('ReactiveCircus/android-emulator-runner@')!=1:
        errors.append('RT02C/P02 must share exactly one emulator runner')
    if wf.count('python3 -B scripts/ci/r02f_p02_session_abandon.py run --out')!=1 or \
       wf.count('python3 -B scripts/ci/r02f_p02_session_abandon.py verify --out')!=1:
        errors.append('P02 run/verify cardinality unexpected')
    if "'pm','install-commit'" in host or 'install-commit' in re.sub(r'(?m)^\s*#.*$', '',host).replace("'install_commit_called':False",''):
        errors.append('P02 must not commit Android installation sessions')
    if host.count("'install_commit_called':False")!=2 or host.count("'installer_session_abandoned':True")!=2:
        errors.append('uncommitted/abandoned exact receipt asserts must exist in producer and verifier')
    if host.count("base.adb('shell','pm','install-abandon'")!=2:
        errors.append('successful abandon plus failure cleanup both mandatory')
    if "if session is not None and not abandoned:" not in host or \
       'for path in remote:' not in host or 'raise base.Refused' not in host:
        errors.append('abandoned session and remote staging cleanup unguarded')
    if "after==before" not in host or "rt02c.baseline_v1(fixtures)==before" not in host:
        errors.append('per-case/final installed APK byte proof missing')
    if "'source_sha':head" not in host or "'run_id':run_id" not in host:
        errors.append('receipt not bound to exact workflow source/run')
    if "'status':'PASS_TWO_ABANDONED_ANDROID_SESSIONS'" not in host:
        errors.append('two explicit Android sessions not required')
    return errors

def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    parser.parse_args()
    issues=inspect()
    for issue in issues:print('OX_RT02F_P02_SOURCE_REFUSED:',issue)
    if issues:return 1
    print('OX_RT02F_P02_SOURCE_CONTRACT_PASS; ANDROID_RUNTIME=NOT_PERFORMED',flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
