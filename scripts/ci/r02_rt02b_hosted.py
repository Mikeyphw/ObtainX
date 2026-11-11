#!/usr/bin/env python3
"""Hosted Android 16 negative system-installer journeys; no release claims.

Precondition: ADB provisions a disposable v2 fixture for these *negative*
journeys only. Actual attempts at unsafe updates use production StockInstaller
through a real Flutter integration_test. ADB package-state and bytes after
attempts must match the exact original baseline. Raw Flutter logs are private.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer

import r02_rt02_hosted as base
from r02_rt02b_fixture import WRONG, BASE

CASES=('signature_mismatch','downgrade')
PHASES=('FLUTTER_STARTING','GRADLE_BUILD','TEST_APK_INSTALL','DART_TEST_STARTED',
        'STOCK_INSTALLER_CALL','STOCK_INSTALLER_RETURNED','ANDROID_UNCHANGED_VERIFIED')
RECEIPT='rt02b-receipt.json'

class Refused(RuntimeError): pass

def need(ok:bool, detail:str) -> None:
    if not ok:raise Refused(detail)

def sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def record(out:Path,case:str,phase:str,elapsed:int,taps:int,attempt:int=1)->None:
    need(case in CASES and phase in PHASES and 0<=taps<=1,'invalid RT02B progress state')
    status={'schema':1,'case':case,'phase':phase,'elapsed_seconds':int(elapsed),
            'approved_installer_taps':taps,'attempt':attempt,'raw_logs_uploaded':False}
    (out/'rt02b-progress.json').write_text(json.dumps(status,indent=2,sort_keys=True)+'\n')
    print(f'OX_R02_RT02B_PROGRESS case={case} phase={phase} elapsed={int(elapsed)}s approvals={taps}',flush=True)

def stage(logfile:Path)->str:
    return base.flutter_phase(logfile)

def baseline_unchanged(fixtures:Path)->dict:
    """Real Android PM and SHA-256 proof; a fake failed Flutter test cannot pass."""
    paths=base.adb('shell','pm','path',base.FIXTURE).splitlines()
    need(len(paths)==1 and paths[0].startswith('package:/data/app/') and
         paths[0].endswith('/base.apk'),'installed fixture package/splits changed')
    match=re.fullmatch(r'package:(/data/app/[A-Za-z0-9_+./~=-]+/base\.apk)',paths[0])
    need(match is not None,'installed base path not trusted')
    digest=base.adb('shell','sha256sum',match.group(1),timeout=60).split()
    expected=sha(fixtures/BASE)
    need(len(digest)==2 and digest[0]==expected,
         'unsafe update changed installed APK bytes or package identity')
    details=base.adb('shell','dumpsys','package',base.FIXTURE,timeout=60)
    versions=re.findall(r'\bversionCode=(\d+)\b',details)
    need('2' in versions and '3' not in versions and '1' not in versions,
         'installed package version changed under negative update')
    return {'version_code':2,'installed_path_count':1,'base_sha256':expected,
            'installed_original_intact':True}

def flutter_failure_category(text:str)->str:
    """Permit only a fixed failure taxonomy, never raw CI/device log export."""
    lower=text.lower()
    if 'gradle task assemble' in lower and ('failed' in lower or 'exception' in lower):
        return 'GRADLE_BUILD_FAILED'
    if 'failed to install' in lower or 'adb exited with exit code' in lower:
        return 'FLUTTER_INSTALL_BRIDGE_FAILED'
    if 'test failed' in lower or 'test failure' in lower or 'expect(' in lower:
        return 'DART_TEST_FAILED'
    if 'timeout' in lower:
        return 'TEST_TIMEOUT'
    return 'UNKNOWN_PRECISE_FAILURE'


def test_case(out:Path,fixtures:Path,case:str,expected_sha:str)->dict:
    need(case in CASES and re.fullmatch(r'[0-9a-f]{64}',expected_sha) is not None,
         'invalid negative journey')
    logfile=out/('rt02b-'+case+'.private.log')
    args=['flutter','test','integration_test/r02b_rejection_test.dart',
          '-d',base.SERIAL,'--flavor','normal','--no-pub','--reporter','expanded',
          '--dart-define=OX_R02B_CASE='+case,
          '--dart-define=OX_R02B_SHA256='+expected_sha]
    started=time.monotonic();deadline=started+930
    taps=0;installed=False;installer_called=False;progress=0
    with logfile.open('wb') as log:
        child=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,
                               stdin=subprocess.DEVNULL)
        try:
            while child.poll() is None and time.monotonic()<deadline:
                phase=stage(logfile);now=time.monotonic()
                if phase=='STOCK_INSTALLER_CALL' and not installer_called:
                    installer_called=True;deadline=min(deadline,now+240)
                if not installed:
                    result=base.command(['adb','-s',base.SERIAL,'shell','pm','path',base.APP],allow_failure=True)
                    if result.returncode==0 and result.stdout.strip().startswith(b'package:'):
                        base.adb('shell','appops','set',base.APP,'REQUEST_INSTALL_PACKAGES','allow')
                        installed=True
                # Never probe the system UI during Gradle build / Flutter boot.
                if installed and phase=='STOCK_INSTALLER_CALL' and taps==0:
                    if base._tap_confirmed_install_dialog():taps=1
                if not progress or now-progress>=25:
                    record(out,case,phase,int(now-started),taps)
                    progress=now
                time.sleep(2)
            if child.poll() is None:
                raise Refused('bounded Flutter negative-test timeout: '+case+' phase='+stage(logfile))
            text=logfile.read_text('utf8','replace')
            phase=stage(logfile)
            need(child.returncode==0 and 'All tests passed!' in text and
                 'OX_R02_RT02_DART_STAGE=INSTALL_RETURNED' in text,
                 'real StockInstaller rejection test did not pass: '+case+' phase='+phase+
                 ' category='+flutter_failure_category(text)+' log_sha256='+sha(logfile))
            need(installed and installer_called,'ObtainX installer not invoked on Android')
            # Each negative result must be independently verified after the
            # real test; neither an absence of UI nor a failed test suffices.
            proof=baseline_unchanged(fixtures)
            record(out,case,'ANDROID_UNCHANGED_VERIFIED',int(time.monotonic()-started),taps)
            proof.update({'case':case,'stock_installer_error_observed':True,
                          'android_confirmation_count':taps,
                          'flutter_log_sha256':sha(logfile)})
            print('OX_R02_RT02B_'+case.upper()+'_REJECTED_AND_UNCHANGED_PASS',flush=True)
            return proof
        finally:
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=6)
                except subprocess.TimeoutExpired:child.kill()
            # Never include private Flutter logs in GitHub artifacts.

def execute(out:Path)->int:
    source,run=base.host_check()
    need(out.is_absolute(), 'absolute evidence directory required')
    out.mkdir(parents=True,exist_ok=True)
    receipt={'schema':1,'source_sha':source,'run_id':run,'status':'NOT_RUN',
             'hosted_emulator_only':True,'physical_device_qualified':False,
             'full_r02_matrix_qualified':False,'release_qualified':False,
             'publication_allowed':False,'backend':'production StockInstaller',
             'android_negative_cases':[]}
    rp=out/RECEIPT;rp.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
    fixtures=out/'fixtures'
    initial=json.loads((fixtures/'fixture_inventory.json').read_text())
    extra=json.loads((fixtures/'rt02b_inventory.json').read_text())
    need(initial.get('source_sha')==source and extra.get('source_sha')==source and
         initial.get('fixture_package')==base.FIXTURE and
         extra.get('fixture_package')==base.FIXTURE,'source-bound fixture mismatch')
    need(initial['files'][BASE]['sha256']==sha(fixtures/BASE)==extra['original_sha256'],
         'signed v2 fixture integrity mismatch')
    need(extra['wrong_sha256']==sha(fixtures/WRONG) and
         re.fullmatch(r'[0-9a-f]{64}',extra['wrong_sha256']) is not None,
         'wrong-signature fixture digest mismatch')
    need(extra['original_cert_sha256']!=extra['wrong_cert_sha256'] and
         extra['ephemeral_keys_deleted'] is True,'negative certificate identity proof missing')
    base.empty_or_expected_package()
    # ADB is only used to establish the disposable precondition; no negative
    # install is simulated through ADB.
    base.adb('install','-t',str(fixtures/BASE),timeout=180)
    baseline_unchanged(fixtures)
    server=None
    try:
        base.FixtureServer.fixtures={WRONG:fixtures/WRONG,'base_v1.apk':fixtures/'base_v1.apk'}
        server=ThreadingHTTPServer(('127.0.0.1',base.PORT),base.FixtureServer)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base.adb('reverse','tcp:'+str(base.PORT),'tcp:'+str(base.PORT))
        for case in CASES:
            # Ensure the next test starts from the same known v2 baseline.
            baseline_unchanged(fixtures)
            expected=(extra['wrong_sha256'] if case=='signature_mismatch' else
                      initial['files']['base_v1.apk']['sha256'])
            proof=test_case(out,fixtures,case,expected)
            receipt['android_negative_cases'].append(proof)
            rp.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
        receipt['status']='PASS_TWO_REAL_ANDROID_REJECTIONS'
        rp.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
        print('OX_R02_RT02B_TWO_REAL_REJECTIONS_PASS',flush=True)
        return 0
    finally:
        if server is not None:
            server.shutdown();server.server_close()
        base.adb('reverse','--remove','tcp:'+str(base.PORT),allow_failure=True)
        base.adb('shell','pm','uninstall',base.FIXTURE,allow_failure=True)

def verify(out:Path)->int:
    source,run=base.identity_check()
    data=json.loads((out/RECEIPT).read_text())
    expected={'schema':1,'source_sha':source,'run_id':run,
              'status':'PASS_TWO_REAL_ANDROID_REJECTIONS',
              'hosted_emulator_only':True,'physical_device_qualified':False,
              'full_r02_matrix_qualified':False,'release_qualified':False,
              'publication_allowed':False,'backend':'production StockInstaller'}
    for key,value in expected.items():need(data.get(key)==value,'receipt invalid: '+key)
    cases=data.get('android_negative_cases')
    need(isinstance(cases,list) and len(cases)==2, 'two distinct negative cases required')
    for got,name in zip(cases,CASES):
        need(isinstance(got,dict) and got.get('case')==name,
             'negative case missing or out of order')
        need(got.get('installed_original_intact') is True and
             got.get('stock_installer_error_observed') is True and
             got.get('version_code')==2 and got.get('installed_path_count')==1,
             'unchanged Android package state not proven')
        need(type(got.get('android_confirmation_count')) is int and
             got['android_confirmation_count'] in (0,1),
             'fabricated or unsafe dialog count')
        for key in ('base_sha256','flutter_log_sha256'):
            need(isinstance(got.get(key),str) and bool(re.fullmatch('[0-9a-f]{64}',got[key])),
                 'missing file provenance: '+key)
    need(cases[0]['base_sha256']==cases[1]['base_sha256'],
         'installed baseline bytes changed between rejections')
    print('OX_R02_RT02B_NEGATIVE_RUNTIME_EVIDENCE_VERIFIED: no release qualification',flush=True)
    return 0

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=['run','verify'])
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    try:
        return execute(a.out) if a.command=='run' else verify(a.out)
    except (OSError,KeyError,TypeError,ValueError,Refused,base.Refused,
            subprocess.TimeoutExpired) as exc:
        if a.command=='run':
            rp=a.out/RECEIPT
            if rp.is_file():
                try:
                    d=json.loads(rp.read_text());d['status']='FAILED'
                    d['failure_category']=type(exc).__name__
                    progress=a.out/'rt02b-progress.json'
                    if progress.is_file():
                        detail=json.loads(progress.read_text())
                        if detail.get('case') in CASES:d['failure_case']=detail['case']
                        if detail.get('phase') in PHASES:d['failure_phase']=detail['phase']
                    rp.write_text(json.dumps(d,sort_keys=True,indent=2)+'\n')
                except (OSError,ValueError):pass
        print('OX_R02_RT02B_REFUSED: '+str(exc),file=sys.stderr,flush=True)
        return 1

if __name__=='__main__':raise SystemExit(main())
