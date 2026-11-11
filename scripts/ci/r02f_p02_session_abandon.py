#!/usr/bin/env python3
"""RT02F P02: bounded real Android install-session abandonment acceptance.

Runs after RT02C's seven real cases in the SAME disposable API36 emulator.
Never installs to a personal device; does not claim app-UI cancellation, an
external backend result, or physical OBB qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

import r02_rt02_hosted as base
import r02_rt02c_hosted as rt02c

RECEIPT = 'r02f-p02-session-abandon.json'
CASES = (('standalone', ('base_v2.apk',)),
         ('split', ('base_v2.apk', 'config.x86_64.apk')))
SID = re.compile(r'^Success: created install session \[([1-9][0-9]{0,9})\]$')
SUCCESS = re.compile(r'^Success(?::.*)?$')
REMOTE_PREFIX = '/data/local/tmp/ox-rt02f-p02-'


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise base.Refused('RT02F P02: '+reason)


def sha(path: Path) -> str:
    # Fixture APKs are bounded by the existing fixture generator, not app data.
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_session_id(text: str) -> str:
    match = SID.fullmatch(text.strip())
    need(match is not None, 'Android install-create did not return exact session ID')
    return match.group(1)


def require_success(text: str, action: str) -> None:
    need(SUCCESS.fullmatch(text.strip()) is not None,
         'Android '+action+' did not confirm success')


def adb_phase(phase: str, *args: str, timeout: int = 45) -> str:
    """Expose the failing ADB operation, never a private device log or file."""
    print('OX_RT02F_P02_ANDROID_PHASE='+phase,flush=True)
    try:
        return base.adb(*args,timeout=timeout)
    except (base.Refused, OSError, TimeoutError) as exc:
        raise base.Refused('RT02F P02 ADB phase='+phase+
                           ' failed ('+type(exc).__name__+'); no acceptance') from exc


def package_session(phase: str, operation: str, *args: str, timeout: int = 45) -> str:
    """Android 16 canonical package manager shell, no retry of session writes."""
    need(operation in ('install-create','install-write','install-abandon'),
         'disallowed package session operation')
    return adb_phase(phase,'shell','cmd','package',operation,*args,timeout=timeout)


def artifact_inventory(fixtures: Path, head: str) -> dict:
    doc=json.loads((fixtures/'fixture_inventory.json').read_text('utf8'))
    need(doc.get('schema')==1 and doc.get('source_sha')==head and
         doc.get('fixture_package')==base.FIXTURE and
         doc.get('signed_with_ephemeral_ci_key') is True and
         doc.get('never_released') is True,'fixture manifest/source identity invalid')
    for _, names in CASES:
        for name in names:
            row=doc.get('files',{}).get(name,{})
            candidate=fixtures/name
            need(candidate.is_file() and candidate.stat().st_size>250 and
                 row.get('sha256')==sha(candidate) and
                 row.get('size')==candidate.stat().st_size and
                 row.get('version_code')==2,
                 'signed v2 APK fixture drift: '+name)
    return doc


def write_receipt(path: Path, body: dict) -> None:
    # No secrets, signing keys, application data, or device logs are published.
    path.write_text(json.dumps(body,sort_keys=True,indent=2)+'\n',encoding='utf8')


def run_case(fixtures: Path, kind: str, names: tuple[str,...], run_id: str) -> dict:
    need(kind in ('standalone','split') and names in (CASES[0][1],CASES[1][1]),
         'unexpected cancellation scenario')
    print('OX_RT02F_P02_ANDROID_PHASE=CHECK_V1_BEFORE_'+kind.upper(),flush=True)
    before=rt02c.baseline_v1(fixtures)
    need(before['installed_original_intact'] is True,'unverified baseline')
    total=sum((fixtures/n).stat().st_size for n in names)
    need(0<total<16*1024*1024,'session fixture size exceeds bounded limit')
    session=None
    remote=[]
    abandoned=False
    try:
        # No UI tap, install-commit, or successful update is permitted.
        session=parse_session_id(package_session('CREATE_'+kind.upper(),
            'install-create','-r','-t','--user','0','-S',str(total),timeout=40))
        for name in names:
            source=fixtures/name
            remote_path=REMOTE_PREFIX+run_id+'-'+kind+'-'+name
            need(re.fullmatch(r'/data/local/tmp/ox-rt02f-p02-[0-9]+-(?:standalone|split)-[a-zA-Z0-9_.-]+\.apk',remote_path)
                 is not None,'untrusted remote filename')
            remote.append(remote_path)
            adb_phase('STAGE_'+kind.upper()+'_'+name,'push',str(source),remote_path,timeout=90)
            digest=adb_phase('HASH_'+kind.upper()+'_'+name,
                             'shell','sha256sum',remote_path,timeout=30).split()
            need(len(digest)==2 and digest[0]==sha(source) and digest[1]==remote_path,
                 'staged APK bytes differ from CI fixture')
            part='base' if name=='base_v2.apk' else 'config.x86_64'
            result=package_session('WRITE_'+kind.upper()+'_'+name,
                        'install-write','-S',str(source.stat().st_size),
                        session,part,remote_path,timeout=80)
            require_success(result,'session install-write')
        # Explicit cancellation: do NOT execute pm install-commit.
        require_success(package_session('ABANDON_'+kind.upper(),
                         'install-abandon',session,timeout=50), 'install-abandon')
        abandoned=True
        print('OX_RT02F_P02_ANDROID_PHASE=CHECK_V1_AFTER_'+kind.upper(),flush=True)
        after=rt02c.baseline_v1(fixtures)
        need(after==before,'cancelled session modified installed v1 APK or version')
        print(f'OX_RT02F_P02_ANDROID_ABANDON_PASS scenario={kind} count={len(names)}',flush=True)
        return {'scenario':kind,'signed_member_count':len(names),
                'original_version_code':1,'original_base_sha256':before['base_sha256'],
                'original_installed_state_intact':True,
                'installer_session_abandoned':True,'install_commit_called':False,
                'installer_confirmation_count':0,
                'v2_member_sha256':[sha(fixtures/n) for n in names]}
    finally:
        errors=[]
        if session is not None and not abandoned:
            try:
                package_session('CLEANUP_ABANDON_'+kind.upper(),
                                'install-abandon',session,timeout=40)
            except Exception as exc:
                errors.append('session cleanup: '+type(exc).__name__)
        for path in remote:
            try:
                adb_phase('CLEANUP_STAGED_'+kind.upper(),
                          'shell','rm','-f',path,timeout=20)
            except Exception as exc:
                errors.append('staged fixture cleanup: '+type(exc).__name__)
        if errors:
            raise base.Refused('RT02F P02 cleanup refused: '+', '.join(errors))


def run(out: Path) -> int:
    head, run_id=base.host_check()  # exact checkout, API36, disposable emulator.
    need(re.fullmatch(r'[0-9]+',run_id) is not None,'invalid GitHub run ID')
    receipt=out/RECEIPT
    write_receipt(receipt, {'schema':1,'status':'NOT_RUN','source_sha':head,
                           'run_id':run_id,'hosted_emulator_only':True,
                           'physical_device_qualified':False,
                           'app_ui_cancel_qualified':False,
                           'other_installer_backends_qualified':False,
                           'obb_device_qualified':False,'release_qualified':False})
    fixtures=out/'fixtures'
    artifact_inventory(fixtures,head)
    # RT02C deliberately removes its v1 fixture in its finally block. P02
    # must establish a NEW, source-bound baseline; never skip RT02C's teardown.
    # This is only the already-verified disposable API36 emulator, never a user
    # device. No v2 install-commit is allowed in either abandonment scenario.
    rt02c.verify(out)
    inv=json.loads((fixtures/'fixture_inventory.json').read_text('utf8'))
    v1=fixtures/'base_v1.apk'
    row=inv.get('files',{}).get('base_v1.apk',{})
    need(inv.get('schema')==1 and inv.get('source_sha')==head and
         inv.get('fixture_package')==base.FIXTURE and
         inv.get('signed_with_ephemeral_ci_key') is True and
         inv.get('never_released') is True and
         v1.is_file() and not v1.is_symlink() and
         250<v1.stat().st_size<16*1024*1024 and
         row.get('sha256')==sha(v1) and row.get('size')==v1.stat().st_size and
         row.get('version_code')==1,
         'signed v1 baseline inventory invalid or source drift')
    print('OX_RT02F_P02_ANDROID_PHASE=CHECK_RT02C_TEARDOWN',flush=True)
    need(base.empty_or_expected_package() is True,
         'RT02C must leave its fixture absent before P02 independent staging')
    staged=False
    try:
        print('OX_RT02F_P02_ANDROID_PHASE=STAGE_FRESH_V1_BASELINE',flush=True)
        staged=True  # also clean up if Android install partially succeeds.
        install=adb_phase('STAGE_FRESH_V1_BASELINE','install','-t',str(v1),timeout=90)
        need(install.splitlines() and install.splitlines()[-1].strip()=='Success',
             'Android did not confirm disposable signed v1 fixture staging')
        print('OX_RT02F_P02_ANDROID_PHASE=CHECK_INITIAL_V1_BASELINE',flush=True)
        before=rt02c.baseline_v1(fixtures)
        results=[]
        for kind,names in CASES:
            results.append(run_case(fixtures,kind,names,run_id))
        print('OX_RT02F_P02_ANDROID_PHASE=CHECK_FINAL_V1_BASELINE',flush=True)
        need(rt02c.baseline_v1(fixtures)==before,'final Android package baseline changed')
        body={'schema':1,'status':'PASS_TWO_ABANDONED_ANDROID_SESSIONS',
              'source_sha':head,'run_id':run_id,'hosted_emulator_only':True,
              'physical_device_qualified':False,'app_ui_cancel_qualified':False,
              'other_installer_backends_qualified':False,'obb_device_qualified':False,
              'release_qualified':False,'cases':results,
              'original_base_sha256':before['base_sha256'],
              'original_version_code':1}
    finally:
        if staged:
            # Never leave even a disposable test package behind on a failed case.
            # Keep receipt NOT_RUN on any failure, including cleanup failure.
            print('OX_RT02F_P02_ANDROID_PHASE=CLEANUP_FRESH_V1_BASELINE',flush=True)
            try:
                cleanup=adb_phase('CLEANUP_FRESH_V1_BASELINE',
                                  'shell','pm','uninstall',base.FIXTURE,timeout=60)
                need(cleanup.splitlines() and cleanup.splitlines()[-1].strip()=='Success',
                     'P02 disposable v1 fixture uninstall did not confirm success')
            except base.Refused as error:
                # A failed/partial staging may already have left no package.
                # We may accept ONLY proven absence, never ambiguous leftovers.
                try:
                    need(base.empty_or_expected_package() is True,
                         'P02 fixture cleanup absence could not be proven')
                except base.Refused as check_error:
                    raise base.Refused('RT02F P02 fixture cleanup refused') from check_error
            need(base.empty_or_expected_package() is True,
                 'P02 v1 fixture remained after cleanup')
    # Publish PASS only after both sessions AND teardown were independently checked.
    write_receipt(receipt,body)
    print('OX_RT02F_P02_SOURCE_BOUND_ANDROID_ABANDON_PASS 2/2',flush=True)
    return 0


def verify(out: Path) -> int:
    head,run_id=base.identity_check()
    fixtures=out/'fixtures'
    artifact_inventory(fixtures,head)
    obj=json.loads((out/RECEIPT).read_text('utf8'))
    for k,v in {'schema':1,'status':'PASS_TWO_ABANDONED_ANDROID_SESSIONS',
                'source_sha':head,'run_id':run_id,'hosted_emulator_only':True,
                'physical_device_qualified':False,'app_ui_cancel_qualified':False,
                'other_installer_backends_qualified':False,'obb_device_qualified':False,
                'release_qualified':False,'original_version_code':1,
                'original_base_sha256':sha(fixtures/'base_v1.apk')}.items():
        need(obj.get(k)==v,'invalid source-bound cancellation receipt: '+k)
    rows=obj.get('cases')
    need(isinstance(rows,list) and len(rows)==2,'expected exactly two abandoned sessions')
    for row,(kind,names) in zip(rows,CASES):
        expected={'scenario':kind,'signed_member_count':len(names),
                  'original_version_code':1,'original_base_sha256':sha(fixtures/'base_v1.apk'),
                  'original_installed_state_intact':True,
                  'installer_session_abandoned':True,'install_commit_called':False,
                  'installer_confirmation_count':0,
                  'v2_member_sha256':[sha(fixtures/n) for n in names]}
        need(row==expected,'cancellation receipt is incomplete or altered: '+kind)
    print('OX_RT02F_P02_INDEPENDENT_SOURCE_BOUND_VERIFY_PASS',flush=True)
    return 0


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('run','verify'))
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    try:
        need(args.out.is_absolute() and args.out.is_dir(),'absolute existing receipt directory required')
        return run(args.out) if args.action=='run' else verify(args.out)
    except (OSError,ValueError,TypeError,base.Refused,TimeoutError) as exc:
        print('OX_RT02F_P02_REFUSED: '+str(exc),file=sys.stderr,flush=True)
        return 1

if __name__=='__main__':raise SystemExit(main())
