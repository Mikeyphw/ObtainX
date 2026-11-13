#!/usr/bin/env python3
"""R02G P01 real Android 16 incompatible-SDK rejection after RT02C and P02.

One disposable CI APK with Android minSdk=37 is attempted on API36.
Exact PackageManager refusal and package absence are independently verified.
No personal devices, app-UI claims, third-party installer claims or releases.
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
import r02f_p02_session_abandon as p02
import r02g_incompatible_sdk_fixture as fixture

RECEIPT='r02g-incompatible-sdk.json'
EXPECTED='INSTALL_FAILED_OLDER_SDK'
# This is a mandatory failure to install a disposable fixture, never a successful install.
DIAGNOSTIC_TAG='OX_R02G_ANDROID_DIAGNOSTIC'
PHASES=('HOSTED_SOURCE_PREFLIGHT','PREREQUISITE_RECEIPTS','PREINSTALL_ABSENCE',
        'INSTALL_MINSDK37_ON_API36','CLASSIFY_ANDROID_REFUSAL',
        'POSTINSTALL_ABSENCE','PRIOR_FIXTURE_ABSENCE','RECEIPT_COMMIT',
        'CLEANUP_CHECK')
_current_phase=PHASES[0]

class Refused(RuntimeError):pass

def need(ok:bool,why:str)->None:
    if not ok:raise Refused('R02G incompatible-SDK refusal: '+why)

def sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def inventory(out:Path,source:str)->dict:
    f=out/'fixtures'/fixture.INVENTORY
    need(f.is_file() and not f.is_symlink(),'missing R02G fixture inventory')
    obj=json.loads(f.read_text('utf8'))
    artifact=out/'fixtures'/fixture.NAME
    expected={'schema':1,'source_sha':source,'fixture_package':fixture.PACKAGE,
              'file':fixture.NAME,'sha256':sha(artifact),
              'size':artifact.stat().st_size,'min_sdk_version':37,
              'device_sdk_expected':36,'ephemeral_ci_signing':True,
              'never_released':True}
    need(obj==expected and 250<expected['size']<8*1024*1024 and
         artifact.is_file() and not artifact.is_symlink(),
         'signed incompatible fixture identity/bytes invalid')
    return obj

def absent()->bool:
    """Require BOTH exact PackageManager inventory and APK-path absence."""
    p=base.command(['adb','-s',base.SERIAL,'shell','pm','path',fixture.PACKAGE],
                   timeout=30,allow_failure=True)
    a=p.stdout.decode('utf8','replace').strip()
    b=p.stderr.decode('utf8','replace').strip()
    need(p.returncode in (0,1) and not a and not b,
         'incompatible package has installed APK paths or ambiguous pm error')
    names=base.adb('shell','cmd','package','list','packages','--user','0',
                   fixture.PACKAGE,timeout=30).splitlines()
    need('package:'+fixture.PACKAGE not in names and
         not any(x.strip()=='package:'+fixture.PACKAGE for x in names),
         'incompatible fixture package unexpectedly installed')
    return True

def install_diagnostics(result)->dict:
    """Bounded, redacted ADB telemetry: never retain command paths or raw output."""
    out=result.stdout.decode('utf8','replace')
    err=result.stderr.decode('utf8','replace')
    pieces=[out,err]
    pattern=r'INSTALL_(?:FAILED|PARSE_FAILED)_[A-Z0-9_]+'
    codes=[re.findall(pattern, part) for part in pieces]
    observed=sorted(set(code for seq in codes for code in seq))
    # Only enum-like Android rejection tokens escape the private stderr/stdout.
    return {'exit_nonzero':result.returncode!=0,
            'stdout_bytes':len(result.stdout),'stderr_bytes':len(result.stderr),
            'codes':observed[:4], 'code_occurrences':sum(map(len,codes)),
            'stdout_codes':len(codes[0]),'stderr_codes':len(codes[1])}

def classify_install(result)->str:
    """Require a real nonzero ADB failure carrying *only* OLDER_SDK.

    Platform-tools versions sometimes mirror one PackageManager Failure line in
    both streams. Permit at most one canonical code in each stream, if the same
    exact older-SDK code appears and at least one stream carries a Failure [...]
    wrapper. Never accept a duplicated unframed string, two errors in the same
    stream, any conflicting error, or text claiming success.
    """
    payload=(result.stdout+b'\n'+result.stderr).decode('utf8','replace')
    diag=install_diagnostics(result)
    print(DIAGNOSTIC_TAG+' phase=CLASSIFY_ANDROID_REFUSAL rc_nonzero='+
          str(int(diag['exit_nonzero']))+' codes='+(','.join(diag['codes']) or 'none')+
          ' code_occurrences='+str(diag['code_occurrences'])+
          ' stdout_bytes='+str(diag['stdout_bytes'])+
          ' stderr_bytes='+str(diag['stderr_bytes']),flush=True)
    need(result.returncode!=0,'ADB_INSTALL_EXIT_ZERO_REFUSED')
    need(len(result.stdout)+len(result.stderr)<=65536,'ADB_INSTALL_RESPONSE_UNBOUNDED')
    need(re.search(r'\bSuccess\b',payload) is None,'ADB_INSTALL_SUCCESS_MARKER_REFUSED')
    codes=re.findall(r'INSTALL_(?:FAILED|PARSE_FAILED)_[A-Z0-9_]+',payload)
    if codes==[EXPECTED]:
        return EXPECTED
    # ADB may echo the same canonical Android response to both output streams.
    # This is NOT authorization to ignore an unrelated/second error category.
    one_per_stream=(diag['stdout_codes']==1 and diag['stderr_codes']==1)
    same_error=(codes==[EXPECTED,EXPECTED] and diag['codes']==[EXPECTED])
    framed=('Failure ['+EXPECTED) in payload
    need(same_error and one_per_stream and framed,
         'ADB_INSTALL_ERROR_CATEGORY_MISMATCH')
    return EXPECTED


def receipt_file(out:Path,body:dict)->None:
    (out/RECEIPT).write_text(json.dumps(body,indent=2,sort_keys=True)+'\n',encoding='utf8')

def baseline(source:str,run:str)->dict:
    return {'schema':1,'status':'NOT_RUN','source_sha':source,'run_id':run,
            'hosted_emulator_only':True,'physical_device_qualified':False,
            'user_facing_import_qualified':False,'app_ui_cancel_qualified':False,
            'obb_device_qualified':False,'other_installer_backends_qualified':False,
            'release_qualified':False,'publication_allowed':False}

def run(out:Path)->int:
    global _current_phase
    _current_phase='HOSTED_SOURCE_PREFLIGHT'
    source,run_id=base.host_check()
    need(out.is_absolute() and out.is_dir(),'absolute existing CI evidence folder required')
    receipt_file(out,baseline(source,run_id))
    inv=inventory(out,source)
    # Both previous real Android acceptance phases are hard prerequisites.
    _current_phase='PREREQUISITE_RECEIPTS'
    rt02c.verify(out)
    p02.verify(out)
    _current_phase='PREINSTALL_ABSENCE'
    need(base.empty_or_expected_package() is True,
         'previous R02 disposable fixture was not uninstalled')
    absent()
    print('OX_R02G_PREINSTALL_PACKAGE_ABSENT_PASS',flush=True)
    _current_phase='INSTALL_MINSDK37_ON_API36'
    print('OX_R02G_ANDROID_PHASE=INSTALL_MINSDK37_ON_API36',flush=True)
    attempted=False
    try:
        attempted=True
        result=base.command(['adb','-s',base.SERIAL,'install','-t','-r',
                             str(out/'fixtures'/fixture.NAME)],
                            timeout=90,allow_failure=True)
        _current_phase='CLASSIFY_ANDROID_REFUSAL'
        category=classify_install(result)
        print('OX_R02G_EXACT_OLDER_SDK_ERROR_PASS',flush=True)
        _current_phase='POSTINSTALL_ABSENCE'
        absent()
        print('OX_R02G_POSTINSTALL_PACKAGE_ABSENT_PASS',flush=True)
        _current_phase='PRIOR_FIXTURE_ABSENCE'
        need(base.empty_or_expected_package() is True,
             'incompatible SDK attempt mutated the earlier test package')
        proof={**baseline(source,run_id),
               'status':'PASS_ANDROID_MINSDK37_REJECTED_ON_API36',
               'fixture_package':fixture.PACKAGE,'fixture_sha256':inv['sha256'],
               'min_sdk_version':37,'device_sdk_version':36,
               'android_rejection_code':category,'adb_install_exit_nonzero':True,
               'package_absent_after':True,'prior_fixture_absent':True,
               'install_backend':'Android PackageManager adb install',
               'installer_dialog_approvals':0}
        # Admit only after independent package absence is verified.
        _current_phase='RECEIPT_COMMIT'
        receipt_file(out,proof)
        print('OX_R02G_ANDROID_REAL_INCOMPATIBLE_SDK_REJECTION_PASS',flush=True)
        return 0
    finally:
        if attempted:
            # Preserve original failing phase, even if a cleanup probe follows.
            # Cleanup even after an unexpected install; no user package touched.
            p=base.command(['adb','-s',base.SERIAL,'shell','pm','path',fixture.PACKAGE],
                           timeout=30,allow_failure=True)
            if p.stdout.strip().startswith(b'package:'):
                base.adb('shell','pm','uninstall',fixture.PACKAGE,timeout=60)
                absent()
                # An unexpected install is NEVER accepted, even after cleanup.
                raise Refused('forbidden fixture installation required cleanup')

def verify(out:Path)->int:
    source,run_id=base.identity_check()
    inv=inventory(out,source)
    obj=json.loads((out/RECEIPT).read_text('utf8'))
    expected={**baseline(source,run_id),
              'status':'PASS_ANDROID_MINSDK37_REJECTED_ON_API36',
              'fixture_package':fixture.PACKAGE,'fixture_sha256':inv['sha256'],
              'min_sdk_version':37,'device_sdk_version':36,
              'android_rejection_code':EXPECTED,'adb_install_exit_nonzero':True,
              'package_absent_after':True,'prior_fixture_absent':True,
              'install_backend':'Android PackageManager adb install',
              'installer_dialog_approvals':0}
    need(obj==expected,'missing/modified source-bound Android incompatible SDK proof')
    print('OX_R02G_INDEPENDENT_SOURCE_BOUND_ANDROID_RECEIPT_PASS',flush=True)
    return 0

def main()->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action',choices=('run','verify'))
    ap.add_argument('--out',required=True,type=Path)
    args=ap.parse_args()
    try:
        return run(args.out) if args.action=='run' else verify(args.out)
    except (OSError,ValueError,TypeError,Refused,base.Refused) as exc:
        # Category + finite allowlisted phase only. Never print ADB text, paths,
        # system output, signer data, or a raw exception message to public CI.
        phase=_current_phase if _current_phase in PHASES else 'HOSTED_SOURCE_PREFLIGHT'
        reason=str(exc) if isinstance(exc,Refused) else type(exc).__name__
        category=(reason if re.fullmatch(r'[A-Z][A-Z0-9_]{2,70}',reason)
                  else 'SOURCE_OR_ANDROID_STATE_REFUSED')
        if args.action=='run' and args.out.is_dir() and (args.out/RECEIPT).is_file():
            try:
                obj=json.loads((args.out/RECEIPT).read_text('utf8'))
                obj['status']='FAILED'
                obj['failure_category']=category
                obj['failure_phase']=phase
                receipt_file(args.out,obj)
            except (OSError,ValueError):pass
        print('OX_R02G_ANDROID_REFUSED phase='+phase+' category='+category,
              file=sys.stderr,flush=True)
        return 1

if __name__=='__main__':raise SystemExit(main())
