#!/usr/bin/env python3
"""RT02C hosted archive-to-StockInstaller tests; no end-user import/release claim.

ADB stages only an exact disposable v1 baseline. Each positive journey extracts
an archive and invokes production StockInstaller from a Flutter integration test.
PackageManager proves v2 base+split hashes afterwards. Negatives reject before
install and retain the v1 baseline. No raw private logs or fixture APKs uploaded.
"""
from __future__ import annotations
import argparse
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import r02_rt02_hosted as base
from r02_rt02c_fixture import POSITIVE,NEGATIVE,NAMES

CASES=POSITIVE+NEGATIVE
RECEIPT='rt02c-receipt.json'
PHASES=('FLUTTER_STARTING','GRADLE_BUILD','TEST_APK_INSTALL',
        'DART_TEST_STARTED','STOCK_INSTALLER_CALL','STOCK_INSTALLER_RETURNED',
        'PREINSTALL_REFUSED','ANDROID_V1_BASELINE_VERIFIED',
        'ANDROID_V2_SPLIT_VERIFIED')
class Refused(RuntimeError):pass

def need(ok:bool,why:str)->None:
    if not ok:raise Refused(why)

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()

def filename(case:str)->str:
    need(case in CASES,'unapproved RT02C case')
    return 'bundle.'+case if case in POSITIVE else ('blocked-traversal.apks' if case=='traversal' else 'ambiguous-base.apkm')

def stage(log:Path)->str:
    if not log.is_file():return 'FLUTTER_STARTING'
    with log.open('rb') as h:
        h.seek(max(0,log.stat().st_size-55000))
        text=h.read().decode('utf8','replace')
    if 'OX_R02C_DART_STAGE=INSTALL_RETURNED' in text:return 'STOCK_INSTALLER_RETURNED'
    if 'OX_R02C_DART_STAGE=PREINSTALL_REFUSED' in text:return 'PREINSTALL_REFUSED'
    if 'OX_R02C_DART_STAGE=INSTALL_CALL' in text:return 'STOCK_INSTALLER_CALL'
    if 'OX_R02C_DART_STAGE=SCENARIO_STARTED' in text:return 'DART_TEST_STARTED'
    if 'Installing build/' in text or 'Installing APK' in text:return 'TEST_APK_INSTALL'
    if 'Running Gradle task' in text or 'Gradle task assemble' in text:return 'GRADLE_BUILD'
    return 'FLUTTER_STARTING'

def progress(out:Path,case:str,phase:str,elapsed:int,taps:int)->None:
    need(case in CASES and phase in PHASES and type(taps)==int and 0<=taps<=1,
         'invalid progress evidence')
    data={'schema':1,'case':case,'phase':phase,'elapsed_seconds':int(elapsed),
          'android_confirmations':taps,'raw_device_logs_uploaded':False}
    (out/'rt02c-progress.json').write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')
    print(f'OX_R02_RT02C_PROGRESS case={case} phase={phase} elapsed={int(elapsed)}s approvals={taps}',flush=True)

def baseline_v1(fixtures:Path)->dict:
    paths=base.adb('shell','pm','path',base.FIXTURE).splitlines()
    need(len(paths)==1 and paths[0].startswith('package:/data/app/') and
         paths[0].endswith('/base.apk'),'v1 baseline APK path ambiguous or unexpected')
    match=re.fullmatch(r'package:(/data/app/[A-Za-z0-9_+./~=-]+/base\.apk)',paths[0])
    need(match is not None,'v1 baseline installed APK path untrusted')
    digest=base.adb('shell','sha256sum',match.group(1),timeout=60).split()
    expected=sha(fixtures/'base_v1.apk')
    need(len(digest)==2 and digest[0]==expected,'v1 installed signed bytes drift')
    versions=re.findall(r'\bversionCode=(\d+)\b',base.adb('shell','dumpsys','package',base.FIXTURE,timeout=60))
    need('1' in versions and '2' not in versions,'v1 baseline version changed')
    return {'version_code':1,'installed_path_count':1,'base_sha256':expected,
            'installed_original_intact':True}

def flutter_failure(text:str)->str:
    lower=text.lower()
    if 'failed to install' in lower or 'adb exited' in lower:return 'FLUTTER_INSTALL_BRIDGE_FAILED'
    if 'gradle task' in lower and ('failed' in lower or 'exception' in lower):return 'GRADLE_BUILD_FAILED'
    if 'expect(' in lower or 'test failed' in lower or 'test failure' in lower:return 'DART_TEST_FAILED'
    if 'timeout' in lower:return 'TEST_TIMEOUT'
    return 'UNKNOWN_PRECISE_FAILURE'

def run_case(out:Path,fixtures:Path,inv:dict,case:str)->dict:
    name=filename(case)
    digest=inv['files'][name]['sha256']
    need(digest==sha(fixtures/name) and re.fullmatch(r'[0-9a-f]{64}',digest) is not None,
         'archive source digest differs')
    log=out/('rt02c-'+case.replace('.','_')+'.private.log')
    args=['flutter','test','integration_test/r02c_archive_install_test.dart',
          '-d',base.SERIAL,'--flavor','normal','--no-pub','--reporter','expanded',
          '--dart-define=OX_R02C_CASE='+case,
          '--dart-define=OX_R02C_ARCHIVE_SHA='+digest,
          '--dart-define=OX_R02C_BASE_SHA='+inv['signed_base_sha256'],
          '--dart-define=OX_R02C_SPLIT_SHA='+inv['signed_split_sha256']]
    started=time.monotonic();deadline=started+960;last_progress=0
    taps=0;installed=False;called=False
    with log.open('wb') as target:
        child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=target,stderr=subprocess.STDOUT)
        try:
            while child.poll() is None and time.monotonic()<deadline:
                now=time.monotonic();phase=stage(log)
                if phase=='STOCK_INSTALLER_CALL' and not called:
                    called=True;deadline=min(deadline,now+240)
                if not installed:
                    probe=base.command(['adb','-s',base.SERIAL,'shell','pm','path',base.APP],allow_failure=True)
                    if probe.returncode==0 and probe.stdout.strip().startswith(b'package:'):
                        base.adb('shell','appops','set',base.APP,'REQUEST_INSTALL_PACKAGES','allow')
                        installed=True
                # Never probe installer UI during compilation or before Dart calls it.
                if installed and called and phase=='STOCK_INSTALLER_CALL' and taps==0:
                    if base._tap_confirmed_install_dialog():taps=1
                if not last_progress or now-last_progress>=25:
                    progress(out,case,phase,int(now-started),taps)
                    last_progress=now
                time.sleep(2)
            if child.poll() is None:
                raise Refused('bounded Flutter RT02C timeout '+case+' phase='+stage(log))
            txt=log.read_text('utf8','replace');phase=stage(log)
            need(child.returncode==0 and 'All tests passed!' in txt,
                 'Flutter RT02C case failed '+case+' phase='+phase+' category='+flutter_failure(txt)+
                 ' log_sha256='+sha(log))
            need(installed,'Flutter runner APK not proven on Android emulator')
            if case in NEGATIVE:
                need(not called and taps==0 and 'OX_R02C_DART_STAGE=PREINSTALL_REFUSED' in txt,
                     'unsafe archive reached installation backend or was not rejected')
                proof=baseline_v1(fixtures)
                progress(out,case,'ANDROID_V1_BASELINE_VERIFIED',int(time.monotonic()-started),taps)
                proof.update({'case':case,'preinstall_refused':True,'android_confirmations':0,
                              'archive_sha256':digest,'flutter_log_sha256':sha(log)})
                print('OX_R02_RT02C_'+case.upper()+'_PREINSTALL_REJECTED_PASS',flush=True)
                return proof
            need(called and 'OX_R02C_DART_STAGE=INSTALL_RETURNED' in txt,
                 'production StockInstaller not invoked and returned for '+case)
            need(taps in (0,1),'Android system approval count invalid')
            proof=base.installed_state(2,True,fixtures)
            progress(out,case,'ANDROID_V2_SPLIT_VERIFIED',int(time.monotonic()-started),taps)
            proof.update({'case':case,'archive_sha256':digest,'android_confirmations':taps,
                          'flutter_log_sha256':sha(log),'installed_signed_members_verified':True})
            print('OX_R02_RT02C_'+case.upper().replace('.','_')+'_REAL_ARCHIVE_INSTALL_PASS',flush=True)
            return proof
        finally:
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=6)
                except subprocess.TimeoutExpired:child.kill()


def eligible_pre_dart_retry(out:Path,fixtures:Path,case:str,error:Exception)->bool:
    """Exactly one retry for a proven pre-Dart Flutter bridge failure only.

    The private log's *final* phase is checked, not a stale periodic progress
    receipt; Android v1 exact-byte state must remain independently intact.
    Never retry an actual installer operation, refusal, or user interaction.
    """
    if not str(error).startswith('Flutter RT02C case failed '):return False
    logfile=out/('rt02c-'+case.replace('.','_')+'.private.log')
    phase=stage(logfile)
    if phase not in ('FLUTTER_STARTING','GRADLE_BUILD','TEST_APK_INSTALL'):
        return False
    progress_file=out/'rt02c-progress.json'
    if not progress_file.is_file():return False
    state=json.loads(progress_file.read_text())
    if state.get('case')!=case or state.get('android_confirmations')!=0:
        return False
    baseline_v1(fixtures)  # Raises/refuses if package installed, replaced or missing.
    return True

def execute(out:Path)->int:
    source,run=base.host_check()
    need(out.is_absolute(),'absolute CI evidence directory required')
    out.mkdir(parents=True,exist_ok=True)
    receipt={'schema':1,'status':'NOT_RUN','source_sha':source,'run_id':run,
             'hosted_emulator_only':True,'physical_device_qualified':False,
             'full_r02_matrix_qualified':False,'user_facing_import_qualified':False,
             'release_qualified':False,'publication_allowed':False,
             'backend':'production StockInstaller','cases':[]}
    rp=out/RECEIPT;rp.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
    fixtures=out/'fixtures'
    inv=json.loads((fixtures/'rt02c_inventory.json').read_text())
    baseline=json.loads((fixtures/'fixture_inventory.json').read_text())
    need(inv.get('source_sha')==source and baseline.get('source_sha')==source and
         inv.get('fixture_package')==base.FIXTURE and baseline.get('fixture_package')==base.FIXTURE,
         'source-bound fixture inventory mismatch')
    need(set(inv['files'])==set(NAMES),'unapproved archive fixture names')
    need(inv['signed_base_sha256']==sha(fixtures/'base_v2.apk')==baseline['files']['base_v2.apk']['sha256'] and
         inv['signed_split_sha256']==sha(fixtures/'config.x86_64.apk')==baseline['files']['config.x86_64.apk']['sha256'],
         'APK signing fixture provenance mismatch')
    for name,data in inv['files'].items():
        need(data['sha256']==sha(fixtures/name),'archive fixture digest mismatch: '+name)
    base.empty_or_expected_package()
    base.FixtureServer.fixtures={name:fixtures/name for name in inv['files']}
    server=ThreadingHTTPServer(('127.0.0.1',base.PORT),base.FixtureServer)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        base.adb('reverse','tcp:'+str(base.PORT),'tcp:'+str(base.PORT))
        for case in CASES:
            # Reset the fixture before each case. ADB only provisions a v1 precondition.
            base.adb('shell','pm','uninstall',base.FIXTURE,allow_failure=True)
            base.empty_or_expected_package()
            base.adb('install','-t',str(fixtures/'base_v1.apk'),timeout=180)
            baseline_v1(fixtures)
            for attempt in (1,2):
                try:
                    data=run_case(out,fixtures,inv,case)
                    break
                except Refused as exc:
                    if attempt!=1 or not eligible_pre_dart_retry(out,fixtures,case,exc):
                        raise
                    print('OX_R02_RT02C_PRE_DART_RETRY case='+case+
                          ' attempt=2 source_bound_v1_intact=1',flush=True)
            receipt['cases'].append(data)
            rp.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
        receipt['status']='PASS_FIVE_ARCHIVES_TWO_PREINSTALL_REFUSALS'
        rp.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
        print('OX_R02_RT02C_FIVE_REAL_ARCHIVES_TWO_REJECTIONS_PASS',flush=True)
        return 0
    finally:
        server.shutdown();server.server_close()
        base.adb('reverse','--remove','tcp:'+str(base.PORT),allow_failure=True)
        base.adb('shell','pm','uninstall',base.FIXTURE,allow_failure=True)

def verify(out:Path)->int:
    source,run=base.identity_check()
    obj=json.loads((out/RECEIPT).read_text())
    expected={'schema':1,'status':'PASS_FIVE_ARCHIVES_TWO_PREINSTALL_REFUSALS',
        'source_sha':source,'run_id':run,'hosted_emulator_only':True,
        'physical_device_qualified':False,'full_r02_matrix_qualified':False,
        'user_facing_import_qualified':False,'release_qualified':False,
        'publication_allowed':False,'backend':'production StockInstaller'}
    for key,value in expected.items():need(obj.get(key)==value,'source-bound receipt invalid: '+key)
    cases=obj.get('cases')
    need(isinstance(cases,list) and len(cases)==7,'seven distinct archive scenarios required')
    for actual,case in zip(cases,CASES):
        need(isinstance(actual,dict) and actual.get('case')==case,'missing or reordered scenario')
        for field in ('archive_sha256','flutter_log_sha256'):
            need(isinstance(actual.get(field),str) and re.fullmatch(r'[0-9a-f]{64}',actual[field]) is not None,
                 'missing file digest: '+field)
        if case in POSITIVE:
            need(actual.get('installed_signed_members_verified') is True and
                 actual.get('version_code')==2 and actual.get('installed_path_count')==2 and
                 actual.get('config_x86_64_present') is True and
                 type(actual.get('android_confirmations')) is int and
                 actual['android_confirmations'] in (0,1),
                 'Android committed base+split evidence missing')
        else:
            need(actual.get('preinstall_refused') is True and
                 actual.get('installed_original_intact') is True and
                 actual.get('version_code')==1 and actual.get('installed_path_count')==1 and
                 actual.get('android_confirmations')==0,
                 'unsafe archive mutated installed package or reached installer')
    need(len(set(x['archive_sha256'] for x in cases))==7,
         'archive case input digests are not independently unique')
    print('OX_R02_RT02C_SOURCE_BOUND_ARCHIVE_RUNTIME_VERIFIED: scoped only',flush=True)
    return 0

def main()->int:
    p=argparse.ArgumentParser();p.add_argument('command',choices=['run','verify'])
    p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    try:return execute(a.out) if a.command=='run' else verify(a.out)
    except (OSError,KeyError,TypeError,ValueError,RuntimeError,base.Refused,
            subprocess.TimeoutExpired) as e:
        if a.command=='run':
            rp=a.out/RECEIPT
            if rp.is_file():
                try:
                    data=json.loads(rp.read_text());data['status']='FAILED'
                    data['failure_category']=type(e).__name__
                    progress_file=a.out/'rt02c-progress.json'
                    if progress_file.is_file():
                        p=json.loads(progress_file.read_text())
                        if p.get('case') in CASES:data['failure_case']=p['case']
                        if p.get('phase') in PHASES:data['failure_phase']=p['phase']
                    rp.write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')
                except (OSError,ValueError):pass
        print('OX_R02_RT02C_REFUSED: '+str(e),file=sys.stderr,flush=True)
        return 1
if __name__=='__main__':raise SystemExit(main())
