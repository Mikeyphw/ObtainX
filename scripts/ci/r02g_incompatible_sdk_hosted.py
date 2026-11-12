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

def classify_install(result)->str:
    """ADB nonzero AND one exact PackageManager older-SDK code mandatory."""
    payload=(result.stdout+b'\n'+result.stderr).decode('utf8','replace')
    need(result.returncode!=0 and len(payload)<=65536,
         'Android installation unexpectedly succeeded or had unsafe output')
    codes=re.findall(r'INSTALL_(?:FAILED|PARSE_FAILED)_[A-Z0-9_]+',payload)
    need(codes==[EXPECTED] and re.search(r'\bSuccess\b',payload) is None,
         'Android refusal is not the exact incompatible-SDK error')
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
    source,run_id=base.host_check()
    need(out.is_absolute() and out.is_dir(),'absolute existing CI evidence folder required')
    receipt_file(out,baseline(source,run_id))
    inv=inventory(out,source)
    # Both previous real Android acceptance phases are hard prerequisites.
    rt02c.verify(out)
    p02.verify(out)
    need(base.empty_or_expected_package() is True,
         'previous R02 disposable fixture was not uninstalled')
    absent()
    print('OX_R02G_ANDROID_PHASE=INSTALL_MINSDK37_ON_API36',flush=True)
    attempted=False
    try:
        attempted=True
        result=base.command(['adb','-s',base.SERIAL,'install','-t','-r',
                             str(out/'fixtures'/fixture.NAME)],
                            timeout=90,allow_failure=True)
        category=classify_install(result)
        absent()
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
        receipt_file(out,proof)
        print('OX_R02G_ANDROID_REAL_INCOMPATIBLE_SDK_REJECTION_PASS',flush=True)
        return 0
    finally:
        if attempted:
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
        if args.action=='run' and args.out.is_dir() and (args.out/RECEIPT).is_file():
            try:
                obj=json.loads((args.out/RECEIPT).read_text('utf8'))
                obj['status']='FAILED';obj['failure_category']=type(exc).__name__
                receipt_file(args.out,obj)
            except (OSError,ValueError):pass
        print('OX_R02G_ANDROID_REFUSED: '+type(exc).__name__,file=sys.stderr,flush=True)
        return 1

if __name__=='__main__':raise SystemExit(main())
