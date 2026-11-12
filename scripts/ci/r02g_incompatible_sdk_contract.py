#!/usr/bin/env python3
"""R02G P01 source contract: Android 37 min-SDK refusal on disposable API36.

Source compliance is not Android runtime acceptance. Only exact real emulator
and independently verified receipt may assert the scoped Android proof.
"""
from __future__ import annotations
import argparse
import ast
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
FIX='scripts/ci/r02g_incompatible_sdk_fixture.py'
HOST='scripts/ci/r02g_incompatible_sdk_hosted.py'
TEST='scripts/ci/test_r02g_incompatible_sdk_contract.py'
WF='.github/workflows/obtainx-r02-rt02c.yml'
SOURCE='.github/workflows/obtainx-r00-contracts.yml'
DOC='docs/R02G_P01_INCOMPATIBLE_SDK_ACCEPTANCE.md'
PATHS=(FIX,HOST,TEST,WF,SOURCE,DOC)

# Protected behavioral evidence; no single printed PASS marker is sufficient.
REQUIRED={
    FIX:("PACKAGE = 'dev.bikram.obtainx.rt02g.future_sdk'",
         "MIN_SDK = 37",'android:minSdkVersion="37"',
         "'--min-sdk-version','37'", "sdkVersion:'37'",'fixture_inventory.json',
         "'ephemeral_ci_signing':True",'for f in (key,xml,unsigned,aligned):f.unlink(missing_ok=True)',
         "'GITHUB_ACTIONS')=='true'", "'never_released':True"),
    HOST:("EXPECTED='INSTALL_FAILED_OLDER_SDK'",'base.host_check()',
          'rt02c.verify(out)','p02.verify(out)','absent()',
          "'adb','-s',base.SERIAL,'install','-t','-r'",
          'result.returncode!=0','codes==[EXPECTED]',
          'package_absent_after',"'release_qualified':False",
          "'app_ui_cancel_qualified':False",'fixture_sha256',
          "'status':'PASS_ANDROID_MINSDK37_REJECTED_ON_API36'",
          'base.identity_check()', 'obj==expected',
          "'physical_device_qualified':False"),
    TEST:('test_valid_source','test_exact_platform_refusal_only',
          'test_unexpected_success_refused','test_missing_sdk_refusal_refused',
          'test_modified_receipt_refused','test_fixture_requires_min37',
          'test_fixture_signing_key_cleanup','test_removed_hosted_gate_refused'),
    WF:("      - 'scripts/ci/r02g_*'",
        'python3 -B scripts/ci/r02g_incompatible_sdk_contract.py --check',
        "-p 'test_r02g_incompatible_sdk_contract.py'",
        'python3 -B scripts/ci/r02g_incompatible_sdk_fixture.py --out',
        'python3 -B scripts/ci/r02g_incompatible_sdk_hosted.py run --out',
        'python3 -B scripts/ci/r02g_incompatible_sdk_hosted.py verify --out',
        'rt02g_inventory.json','r02g-incompatible-sdk.json',
        'ReactiveCircus/android-emulator-runner@a421e43855164a8197daf9d8d40fe71c6996bb0d',
        'permissions:\n  contents: read','if: always()',
        "'system-images;android-36;google_apis;x86_64'"),
    SOURCE:('python3 -B scripts/ci/r02g_incompatible_sdk_contract.py --check',
            "python3 -m unittest discover -s scripts/ci -p 'test_*.py' -v"),
    DOC:('R02G P01','API36','Android 37','not full R02','Shizuku',
          'Dhizuku','OBB','user-facing import','R03'),
}

def inspect(root:Path=ROOT)->list[str]:
    errors=[];docs={}
    for path in PATHS:
        f=root/path
        if not f.is_file() or f.is_symlink():
            errors.append('missing or linked R02G source '+path);docs[path]=''
        else:
            docs[path]=f.read_text('utf8')
    for path,tokens in REQUIRED.items():
        for token in tokens:
            if token not in docs[path]:
                errors.append('R02G protected source evidence absent: '+path+' / '+token)
    for path in (FIX,HOST,TEST):
        try:ast.parse(docs[path],filename=path)
        except SyntaxError:errors.append('R02G source syntax invalid: '+path)
    wf=docs[WF]
    run_a='python3 -B scripts/ci/r02_rt02c_hosted.py run --out'
    run_b='python3 -B scripts/ci/r02f_p02_session_abandon.py run --out'
    run_c='python3 -B scripts/ci/r02g_incompatible_sdk_hosted.py run --out'
    verify_a='python3 -B scripts/ci/r02_rt02c_hosted.py verify --out'
    verify_b='python3 -B scripts/ci/r02f_p02_session_abandon.py verify --out'
    verify_c='python3 -B scripts/ci/r02g_incompatible_sdk_hosted.py verify --out'
    for token in (run_a,run_b,run_c,verify_a,verify_b,verify_c):
        if wf.count(token)!=1:errors.append('R02G exactly one mandatory phase missing: '+token)
    script_line=next((line for line in wf.splitlines() if line.strip().startswith("script: bash -c 'set -euo pipefail; ")), '')
    if not (script_line and all(x in script_line for x in (run_a,run_b,run_c)) and
            script_line.index(run_a)<script_line.index(run_b)<script_line.index(run_c) and
            script_line.rstrip().endswith("'")):
        errors.append('R02G must execute after RT02C and P02 in SAME fail-closed emulator')
    if not (verify_a in wf and verify_b in wf and verify_c in wf and
            wf.index(verify_a)<wf.index(verify_b)<wf.index(verify_c)):
        errors.append('independent verification chain must preserve prerequisite order')
    if wf.count('ReactiveCircus/android-emulator-runner@')!=1:
        errors.append('R02G must not introduce a second emulator')
    if ('test -c /dev/kvm' not in wf or 'api-level: 36' not in wf or
        'target: google_apis' not in wf or 'arch: x86_64' not in wf):
        errors.append('verified API36 emulator boot requirements missing')
    if ('continue-on-error: true' in wf or
         re.search(r'(?i)gh\s+release\s+create|flutter\s+build\s+apk.*--release',wf)):
        errors.append('R02G cannot suppress failures or publish releases')
    prep=wf.find('      - name: Compile and verify signed APK and archive before emulator boot')
    fixture=wf.find('python3 -B scripts/ci/r02g_incompatible_sdk_fixture.py --out')
    emulator=wf.find('      - name: Real Android archive update sessions and two extraction refusals')
    if not 0<=prep<fixture<emulator:
        errors.append('minSdk37 fixture must be signed BEFORE emulator boot')
    evidence=wf.find('      - name: Publish minimized emulator-only evidence even on failure')
    if evidence<0 or wf.find('r02g-incompatible-sdk.json',evidence)<evidence or \
       wf.find('rt02g_inventory.json',evidence)<evidence:
        errors.append('bounded R02G failure artifact upload absent')
    host=docs[HOST]
    if host.find('rt02c.verify(out)')<0 or host.find('p02.verify(out)')<host.find('rt02c.verify(out)') or \
       host.find('attempted=True')<host.find('p02.verify(out)'):
        errors.append('R02G real test may run before prerequisite verified device gates')
    return errors

def main()->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check',action='store_true');ap.parse_args()
    errors=inspect()
    for e in errors:print('OX_R02G_SOURCE_REFUSED: '+e,flush=True)
    if errors:return 1
    print('OX_R02G_SOURCE_CONTRACT_PASS; REAL_ANDROID_RUNTIME=NOT_PERFORMED',flush=True)
    return 0
if __name__=='__main__':raise SystemExit(main())
