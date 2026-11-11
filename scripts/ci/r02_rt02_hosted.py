#!/usr/bin/env python3
"""Fail-closed, disposable Android 16 system-installer acceptance runner.

Two distinct real Flutter integration test launches invoke production StockInstaller:
  1. standalone fresh fixture APK version 1
  2. base + config.x86_64 split update version 2
No real user packages are used. This is not full R02 container-matrix or release proof.
"""
from __future__ import annotations
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET

APP='dev.bikram.obtainx.debug'
FIXTURE='dev.bikram.obtainx.rt02.fixture'
SERIAL='emulator-5554'
PORT=18782
NAME='ObtainX RT02 Fixture'
SHA=re.compile(r'^[0-9a-f]{64}$')
APPROVERS={'com.google.android.packageinstaller','com.android.packageinstaller',
           'com.google.android.permissioncontroller','com.android.permissioncontroller'}

class Refused(RuntimeError): pass

def need(condition:bool, message:str)->None:
    if not condition: raise Refused(message)

def command(args:list[str], timeout:int=30, allow_failure:bool=False)->subprocess.CompletedProcess:
    try:
        p=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,timeout=timeout,check=False)
    except (OSError,subprocess.TimeoutExpired) as ex:
        raise Refused('host command unavailable or timeout: '+args[0]) from ex
    if p.returncode and not allow_failure:
        msg=(p.stderr or p.stdout).decode('utf-8','replace').strip()[-300:]
        raise Refused('command failed: '+args[0]+' rc='+str(p.returncode)+' '+msg)
    return p

def adb(*args:str, timeout:int=30, allow_failure:bool=False)->str:
    return command(['adb','-s',SERIAL,*args],timeout=timeout,allow_failure=allow_failure).stdout.decode('utf-8','replace').strip()

def sha_file(p:Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()

def identity_check()->tuple[str,str]:
    need(os.environ.get('GITHUB_ACTIONS')=='true' and
         os.environ.get('RUNNER_OS')=='Linux' and os.environ.get('RUNNER_ARCH')=='X64',
         'hosted Linux x64 runner required')
    source=os.environ.get('GITHUB_SHA','');run=os.environ.get('GITHUB_RUN_ID','')
    need(bool(re.fullmatch('[0-9a-f]{40}',source)) and run.isdigit(),
         'missing hosted source/run pin')
    need(command(['git','rev-parse','HEAD']).stdout.decode().strip()==source,
         'checkout source differs from GitHub workflow SHA')
    return source,run

def host_check()->tuple[str,str]:
    source,run=identity_check()
    need(adb('get-state')=='device' and adb('shell','getprop','ro.kernel.qemu')=='1'
         and adb('shell','getprop','ro.build.version.sdk')=='36',
         'no verified disposable Android 16 emulator')
    return source,run

def empty_or_expected_package() -> bool:
    p=command(['adb','-s',SERIAL,'shell','pm','path',FIXTURE],allow_failure=True)
    stdout=p.stdout.decode('utf-8','replace').strip()
    stderr=p.stderr.decode('utf-8','replace').strip()
    if p.returncode in (0,1) and not stdout and not stderr:
        extra=adb('shell','cmd','package','list','packages','--user','0',FIXTURE)
        need(not extra, 'fixture package unexpectedly present')
        return True
    raise Refused('fixture package already installed or package query ambiguous')

def installed_state(expected_version:int,split:bool,fixture_dir:Path)->dict:
    paths=adb('shell','pm','path',FIXTURE).splitlines()
    need(len(paths)==(2 if split else 1), 'installed APK count differs from required atomic session')
    need(all(p.startswith('package:/data/app/') for p in paths),'unexpected installed package paths')
    need(any(p.endswith('/base.apk') for p in paths),'installed base APK absent')
    if split:
        need(any('config.x86_64.apk' in p for p in paths),'installed config.x86_64 split absent')
    pattern=re.compile(r'^package:(/data/app/[A-Za-z0-9_+./~=-]+\.apk)$')
    expected={'base.apk':sha_file(fixture_dir/('base_v2.apk' if split else 'base_v1.apk'))}
    if split:
        split_sha=sha_file(fixture_dir/'config.x86_64.apk')
        expected['config.x86_64.apk']=split_sha
        expected['split_config.x86_64.apk']=split_sha
    for item in paths:
        match=pattern.fullmatch(item)
        need(match is not None,'untrusted installed path syntax')
        name=Path(match.group(1)).name
        need(name in expected,'unexpected installed split name: '+name)
        digest=adb('shell','sha256sum',match.group(1),timeout=60).split()
        need(len(digest)==2 and digest[0]==expected[name], 'installed APK bytes differ from signed CI fixture: '+name)
    details=adb('shell','dumpsys','package',FIXTURE,timeout=60)
    matches=re.findall(r'\bversionCode=(\d+)\b',details)
    need(str(expected_version) in matches,'installed versionCode mismatch')
    return {'version_code':expected_version,'installed_path_count':len(paths),
            'config_x86_64_present':split}

class FixtureServer(BaseHTTPRequestHandler):
    fixtures:dict[str,Path]={}
    def do_GET(self):
        name=self.path.lstrip('/')
        if name not in self.fixtures or '/' in name or '?' in name:
            self.send_error(404);return
        payload=self.fixtures[name].read_bytes()
        self.send_response(200);self.send_header('Content-Type','application/vnd.android.package-archive')
        self.send_header('Content-Length',str(len(payload)));self.end_headers()
        self.wfile.write(payload)
    def log_message(self,*args):pass

def _tap_confirmed_install_dialog()->bool:
    # No blind tap coordinates. Only click an explicit Install/Update action
    # belonging to the known Android package installer and our fixture label.
    command(['adb','-s',SERIAL,'shell','uiautomator','dump','--compressed',
             '/sdcard/ox-rt02-window.xml'], timeout=18,allow_failure=True)
    p=command(['adb','-s',SERIAL,'shell','cat','/sdcard/ox-rt02-window.xml'],
              timeout=10,allow_failure=True)
    if p.returncode or len(p.stdout)>450000 or not p.stdout.lstrip().startswith(b'<?xml'):
        return False
    try:
        root=ET.fromstring(p.stdout)
    except ET.ParseError:
        return False
    nodes=list(root.iter('node'))
    # Validate actual system package installer screen and fixture identity.
    if not any(NAME in (n.attrib.get('text','')+' '+n.attrib.get('content-desc',''))
               for n in nodes):
        return False
    candidates=[]
    for n in nodes:
        a=n.attrib
        label=(a.get('text','')+' '+a.get('content-desc','')).strip()
        if (a.get('package') in APPROVERS and a.get('enabled')=='true' and
            label in ('Install','Update','Install app','Update app')):
            m=re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]',a.get('bounds',''))
            if m:
                x1,y1,x2,y2=map(int,m.groups())
                if x2>x1 and y2>y1:
                    candidates.append(((x1+x2)//2,(y1+y2)//2))
    if len(candidates)!=1:
        return False
    x,y=candidates[0]
    adb('shell','input','tap',str(x),str(y))
    print('OX_R02_RT02_ANDROID_CONFIRMATION_TAPPED',flush=True)
    return True

# Only allowlisted progress phases are emitted or retained; raw Flutter logs remain
# local to the ephemeral runner and are deliberately excluded from artifacts.
PHASES=('FLUTTER_STARTING','GRADLE_BUILD','TEST_APK_INSTALL',
        'DART_TEST_STARTED','STOCK_INSTALLER_CALL','STOCK_INSTALLER_RETURNED',
        'ANDROID_PACKAGE_STATE_VERIFIED')


def flutter_phase(logfile:Path)->str:
    if not logfile.is_file(): return 'FLUTTER_STARTING'
    with logfile.open('rb') as stream:
        stream.seek(max(0,logfile.stat().st_size-48000))
        tail=stream.read().decode('utf-8','replace')
    if 'OX_R02_RT02_DART_STAGE=INSTALL_RETURNED' in tail:
        return 'STOCK_INSTALLER_RETURNED'
    if 'OX_R02_RT02_DART_STAGE=INSTALL_CALL' in tail:
        return 'STOCK_INSTALLER_CALL'
    if 'OX_R02_RT02_DART_STAGE=SCENARIO_STARTED' in tail:
        return 'DART_TEST_STARTED'
    if 'Installing build/' in tail or 'Installing APK' in tail:
        return 'TEST_APK_INSTALL'
    if 'Running Gradle task' in tail or 'Gradle task assemble' in tail:
        return 'GRADLE_BUILD'
    return 'FLUTTER_STARTING'


def record_flutter_progress(out:Path,scenario:str,phase:str,elapsed:int,
                            app_installed:bool,confirmations:int)->None:
    need(phase in PHASES and scenario in ('standalone','split'),
         'invalid bounded diagnostic phase')
    evidence={'schema':1,'status':'RUNNING','scenario':scenario,
              'flutter_phase':phase,'elapsed_seconds':int(elapsed),
              'obtainx_apk_present':app_installed,
              'android_confirmation_count':confirmations,
              'contains_raw_device_logs':False}
    (out/'progress.json').write_text(json.dumps(evidence,sort_keys=True,indent=2)+'\n')
    print(f'OX_R02_RT02_PROGRESS scenario={scenario} phase={phase} elapsed={int(elapsed)}s '
          f'app_installed={int(app_installed)} approvals={confirmations}',flush=True)


def classify_android_approval(scenario:str,tap_count:int,actual:dict)->str:
    """Distinguish a real UI approval from an Android-committed update.

    Android may complete an update of a package installed by the same installer
    without presenting a second approval dialog. A missing click is NEVER used
    as proof of installation. For split upgrades, the caller MUST first verify
    version 2, base and config split paths, and exact signed bytes using
    installed_state(). A first-time install still requires observed UI approval.
    """
    need(scenario in ('standalone','split') and type(tap_count) is int,
         'invalid approval classification request')
    need(tap_count in (0,1),'unexpected number of Android system approvals')
    if scenario == 'standalone':
        need(tap_count==1,'fresh standalone install requires observed Android approval')
        need(actual.get('version_code')==1 and actual.get('installed_path_count')==1
             and actual.get('config_x86_64_present') is False,
             'first-install package-state proof absent')
        return 'explicit_dialog'
    need(actual.get('version_code')==2 and actual.get('installed_path_count')==2
         and actual.get('config_x86_64_present') is True,
         'no verified Android-committed split update')
    return 'explicit_dialog' if tap_count==1 else 'platform_committed_no_dialog'


def one_scenario(out:Path,inventory:dict,scenario:str)->dict:
    assert scenario in ('standalone','split')
    files=inventory['files'];base=files['base_v1.apk' if scenario=='standalone' else 'base_v2.apk']
    split=files['config.x86_64.apk']
    args=['flutter','test','integration_test/r02_real_installer_test.dart',
          '-d',SERIAL,'--flavor','normal','--no-pub','--reporter','expanded',
          '--dart-define=OX_R02_SCENARIO='+scenario,
          '--dart-define=OX_R02_BASE_SHA='+base['sha256'],
          '--dart-define=OX_R02_SPLIT_SHA='+split['sha256']]
    logfile=out/('flutter-'+scenario+'.log')
    tap_count=0
    started=time.monotonic()
    # Cold hosted Gradle builds can exceed the original 330s ceiling.
    # Once the Dart installer call starts, allow at most 240s for Android UI.
    deadline=started+900
    saw_installer_call=False
    last_progress=0.0
    with logfile.open('wb') as log:
        p=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
        installed_app=False
        try:
            while p.poll() is None and time.monotonic()<deadline:
                now=time.monotonic()
                phase=flutter_phase(logfile)
                if phase=='STOCK_INSTALLER_CALL' and not saw_installer_call:
                    saw_installer_call=True
                    deadline=min(deadline,now+240)
                if now-last_progress>=25 or not last_progress:
                    record_flutter_progress(out,scenario,phase,int(now-started),
                                            installed_app,tap_count)
                    last_progress=now
                # Flutter installs the test runner APK itself. Explicit app-op
                # grants only install-from-source eligibility, not final install.
                if not installed_app:
                    r=command(['adb','-s',SERIAL,'shell','pm','path',APP],allow_failure=True)
                    if r.returncode==0 and r.stdout.strip().startswith(b'package:'):
                        adb('shell','appops','set',APP,'REQUEST_INSTALL_PACKAGES','allow')
                        installed_app=True
                if installed_app and tap_count<2:
                    if _tap_confirmed_install_dialog():tap_count+=1
                time.sleep(2)
            if p.poll() is None:
                phase=flutter_phase(logfile)
                record_flutter_progress(out,scenario,phase,int(time.monotonic()-started),
                                        installed_app,tap_count)
                raise Refused('RT02_FLUTTER_TIMEOUT: scenario='+scenario+' phase='+phase+
                              ' app_present='+str(installed_app)+
                              ' approvals='+str(tap_count))
            text=logfile.read_text('utf-8','replace')
            record_flutter_progress(out,scenario,flutter_phase(logfile),
                                    int(time.monotonic()-started),installed_app,tap_count)
            need(p.returncode==0 and 'All tests passed!' in text,
                 'Flutter real installer test failed ('+scenario+') phase='+flutter_phase(logfile)+
                 ' rc='+str(p.returncode))
            need(installed_app,'Flutter test APK not installed on emulator')
            # Android can complete an update without a second user prompt. The
            # real production installer must report success (Dart test above),
            # AND Android's package manager must prove the exact version,
            # base/split counts, and SHA256 of every installed APK BEFORE any
            # no-dialog result can be admitted. Never fabricate a UI tap.
            actual=installed_state(1 if scenario=='standalone' else 2,
                                   scenario=='split',out/'fixtures')
            approval_path=classify_android_approval(scenario,tap_count,actual)
            record_flutter_progress(out,scenario,'ANDROID_PACKAGE_STATE_VERIFIED',
                                    int(time.monotonic()-started),installed_app,tap_count)
            actual['scenario']=scenario
            actual['android_confirmations']=tap_count
            actual['approval_path']=approval_path
            print('OX_R02_RT02_ANDROID_APPROVAL_PATH='+scenario+':'+approval_path,flush=True)
            print('OX_R02_RT02_REAL_'+scenario.upper()+'_PASS',flush=True)
            return actual
        finally:
            if p.poll() is None:
                p.terminate()
                try:p.wait(timeout=6)
                except subprocess.TimeoutExpired:p.kill()

def execute(out:Path)->int:
    source,run=host_check()
    out.mkdir(parents=True,exist_ok=True)
    receipt={'schema':1,'status':'NOT_RUN','source_sha':source,'run_id':run,
             'hosted_emulator_only':True,'physical_device_qualified':False,
             'full_r02_matrix_qualified':False,'release_qualified':False,
             'publication_allowed':False,'installer_backend':'production StockInstaller',
             'scenarios':[]}
    path=out/'rt02-receipt.json';path.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
    fixtures=out/'fixtures';inventory=json.loads((fixtures/'fixture_inventory.json').read_text())
    need(inventory.get('source_sha')==source and inventory.get('fixture_package')==FIXTURE,
         'fixture source or package identity mismatch')
    need(set(inventory['files'])=={'base_v1.apk','base_v2.apk','config.x86_64.apk'},
         'unexpected fixture inventory')
    for name,entry in inventory['files'].items():
        need(SHA.fullmatch(entry['sha256']) is not None and sha_file(fixtures/name)==entry['sha256'],
             'fixture digest mismatch: '+name)
    empty_or_expected_package()
    FixtureServer.fixtures={name:fixtures/name for name in inventory['files']}
    server=ThreadingHTTPServer(('127.0.0.1',PORT),FixtureServer)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        adb('reverse','tcp:'+str(PORT),'tcp:'+str(PORT))
        for scenario in ('standalone','split'):
            proof=one_scenario(out,inventory,scenario)
            receipt['scenarios'].append(proof)
            path.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
        receipt['status']='PASS_TWO_ANDROID_SYSTEM_SESSIONS'
        path.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
        print('OX_R02_RT02_TWO_REAL_SESSIONS_PASS',flush=True)
        return 0
    finally:
        server.shutdown();server.server_close()
        adb('reverse','--remove','tcp:'+str(PORT),allow_failure=True)
        adb('shell','pm','uninstall',FIXTURE,allow_failure=True)

def verify(out:Path)->int:
    source,run=identity_check()
    v=json.loads((out/'rt02-receipt.json').read_text())
    for k,expected in {'schema':1,'status':'PASS_TWO_ANDROID_SYSTEM_SESSIONS',
        'source_sha':source,'run_id':run,'hosted_emulator_only':True,
        'physical_device_qualified':False,'full_r02_matrix_qualified':False,
        'release_qualified':False,'publication_allowed':False,
        'installer_backend':'production StockInstaller'}.items():
        need(v.get(k)==expected,'invalid device receipt: '+k)
    # Exact receipt alternatives: standalone MUST prove its approval, while
    # an update can be confirmed either by a real dialog or by a platform-
    # committed no-dialog upgrade. Never synthesize android_confirmations=1.
    standalone={'scenario':'standalone','version_code':1,'installed_path_count':1,
        'config_x86_64_present':False,'android_confirmations':1,
        'approval_path':'explicit_dialog'}
    split_common={'scenario':'split','version_code':2,'installed_path_count':2,
        'config_x86_64_present':True}
    valid_scenarios=[]
    for count,path in ((0,'platform_committed_no_dialog'),(1,'explicit_dialog')):
        valid_scenarios.append([standalone,
            {**split_common,'android_confirmations':count,'approval_path':path}])
    need(v.get('scenarios') in valid_scenarios,
        'incomplete or forged real system-installation scenario proof')
    print('OX_R02_RT02_SOURCE_BOUND_EMULATOR_ONLY_VERIFIED',flush=True)
    return 0

def main()->int:
    p=argparse.ArgumentParser();p.add_argument('action',choices=['run','verify']);p.add_argument('--out',required=True,type=Path)
    a=p.parse_args()
    try:
        need(a.out.is_absolute(),'receipt directory must be absolute')
        return execute(a.out) if a.action=='run' else verify(a.out)
    except (OSError,ValueError,Refused,subprocess.TimeoutExpired) as ex:
        if a.action=='run':
            receipt=a.out/'rt02-receipt.json'
            if receipt.is_file():
                try:
                    v=json.loads(receipt.read_text());v['status']='FAILED';v['failure_category']=type(ex).__name__
                    progress=a.out/'progress.json'
                    if progress.is_file():
                        detail=json.loads(progress.read_text())
                        if detail.get('flutter_phase') in PHASES:
                            v['failure_phase']=detail['flutter_phase']
                        if detail.get('scenario') in ('standalone','split'):
                            v['failure_scenario']=detail['scenario']
                    receipt.write_text(json.dumps(v,sort_keys=True,indent=2)+'\n')
                except (OSError,ValueError):pass
        print('OX_R02_RT02_REFUSED: '+str(ex),file=sys.stderr,flush=True)
        return 1

if __name__=='__main__':raise SystemExit(main())
