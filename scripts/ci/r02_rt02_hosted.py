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
import signal
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



def split_pre_dart_recovery_allowed(scenario:str,attempt:int,phase:str,
                                    dart_started:bool,tap_count:int)->bool:
    """Only recover from a failed *test harness*, never from an installer attempt."""
    return (scenario=='split' and type(attempt) is int and attempt==1 and
            phase in ('FLUTTER_STARTING','GRADLE_BUILD','TEST_APK_INSTALL') and
            dart_started is False and type(tap_count) is int and tap_count==0)


def split_pre_dart_stalled(scenario:str,attempt:int,phase:str,
                           elapsed:float,idle:float)->bool:
    """No timed restart after Dart, StockInstaller, or Android approval."""
    return (scenario=='split' and attempt==1 and phase=='TEST_APK_INSTALL' and
            elapsed>=360 and idle>=180)


def terminate_flutter_process_group(p:subprocess.Popen)->None:
    """Stop only this invocation's isolated process group; reap its parent."""
    try:
        os.killpg(p.pid,signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        p.wait(timeout=6)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:p.wait(timeout=6)
        except subprocess.TimeoutExpired as ex:
            raise Refused('Flutter process group did not terminate') from ex


# Explicitly allowlisted, bounded log diagnostics. Never emit, upload or store
# raw Flutter output, device identifiers, environment variables or stack traces.
FAILURE_RULES=(
    ('ANDROID_APK_INSTALL_REJECTED', r'INSTALL_(?:FAILED|PARSE_FAILED)_[A-Z_]+'),
    ('FLUTTER_INSTALL_BRIDGE_FAILED', r'(?:adb: failed to install|Error installing APK|Unable to install APK)'),
    ('GRADLE_BUILD_FAILED', r'(?:FAILURE: Build failed with an exception|Gradle task .* failed)'),
    ('FLUTTER_COMPILATION_FAILED', r'(?:Error: .* failed to compile|Compilation failed|Target kernel_snapshot_program failed)'),
    ('ANDROID_INSTRUMENTATION_FAILED', r'(?:INSTRUMENTATION_FAILED|INSTRUMENTATION_RESULT: shortMsg=|Test runner failed)'),
    ('VM_SERVICE_UNAVAILABLE', r'(?:Dart VM Service.*not found|Unable to connect to the VM service|Error connecting to the service protocol)'),
    ('TEST_RUNNER_START_FAILED', r'(?:Error waiting for a debug connection|Could not start the Dart VM|The application could not be started)'),
    ('FLUTTER_TEST_ASSERTION_FAILED', r'(?:Some tests failed|Test failed\.|Expected:|TestFailure)'),
)


def classify_flutter_failure(logfile:Path)->tuple[str,bool,str]:
    """Report only known diagnostic *categories* and SHA, never device logs."""
    data=logfile.read_bytes() if logfile.is_file() else b''
    # Reading is ephemeral; neither bytes nor extracted fragments leave runner.
    text=data.decode('utf-8','replace')
    dart_started=bool(re.search(r'OX_R02_RT02_DART_STAGE=(?:SCENARIO_STARTED|INSTALL_CALL|INSTALL_RETURNED)',text))
    for code,pattern in FAILURE_RULES:
        if re.search(pattern,text,re.IGNORECASE):
            return code,dart_started,hashlib.sha256(data).hexdigest()
    return ('DART_TEST_FAILED_UNCLASSIFIED' if dart_started else 'PRE_DART_FAILURE_UNCLASSIFIED',
            dart_started,hashlib.sha256(data).hexdigest())


def record_flutter_failure(out:Path,scenario:str,attempt:int,phase:str,
                           logfile:Path,returncode:int)->tuple[str,bool]:
    category,dart_started,checksum=classify_flutter_failure(logfile)
    need(category in {code for code,_ in FAILURE_RULES} |
         {'DART_TEST_FAILED_UNCLASSIFIED','PRE_DART_FAILURE_UNCLASSIFIED'},
         'unexpected Flutter failure category')
    evidence=json.loads((out/'progress.json').read_text())
    need(evidence.get('scenario')==scenario and evidence.get('flutter_phase') in PHASES,
         'missing bounded progress evidence')
    evidence.update(status='FAILED',flutter_error_category=category,
                    flutter_return_code=returncode,
                    dart_test_started=dart_started,
                    ephemeral_flutter_log_sha256=checksum,
                    flutter_attempt=attempt,
                    contains_raw_device_logs=False)
    (out/'progress.json').write_text(json.dumps(evidence,sort_keys=True,indent=2)+'\n')
    print(f'OX_R02_RT02_FLUTTER_FAILURE scenario={scenario} attempt={attempt} '
          f'phase={phase} category={category} dart_started={int(dart_started)} rc={returncode}',flush=True)
    return category,dart_started


def one_scenario(out:Path,inventory:dict,scenario:str)->dict:
    assert scenario in ('standalone','split')
    files=inventory['files'];base=files['base_v1.apk' if scenario=='standalone' else 'base_v2.apk']
    split=files['config.x86_64.apk']
    args=['flutter','test','integration_test/r02_real_installer_test.dart',
          '-d',SERIAL,'--flavor','normal','--no-pub','--reporter','expanded',
          '--dart-define=OX_R02_SCENARIO='+scenario,
          '--dart-define=OX_R02_BASE_SHA='+base['sha256'],
          '--dart-define=OX_R02_SPLIT_SHA='+split['sha256']]
    tap_count=0
    # A second attempt is permitted only when the first Flutter test failed
    # BEFORE Dart executed, the fixture remains absent, and no approval occurred.
    # It never retries a failed actual install or a failed Android package check.
    for attempt in (1,2):
        logfile=out/('flutter-'+scenario+'-attempt'+str(attempt)+'.log')
        started=time.monotonic()
        deadline=started+900
        saw_installer_call=False
        last_progress=0.0
        last_log_size=0
        last_log_growth=started
        tap_count=0
        with logfile.open('wb') as log:
            p=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                               start_new_session=True)
            installed_app=False
            try:
                while p.poll() is None and time.monotonic()<deadline:
                    now=time.monotonic()
                    phase=flutter_phase(logfile)
                    log_size=logfile.stat().st_size
                    if log_size != last_log_size:
                        last_log_growth=now
                        last_log_size=log_size
                    # A stalled second Flutter test has already installed its
                    # harness APK but has not reached Dart or StockInstaller.
                    # Abort only this pre-Dart bootstrap, never an install call.
                    if split_pre_dart_stalled(scenario,attempt,phase,
                                              now-started,now-last_log_growth):
                        print('OX_R02_RT02_SPLIT_BOOTSTRAP_STALL_DETECTED',flush=True)
                        break
                    if phase=='STOCK_INSTALLER_CALL' and not saw_installer_call:
                        saw_installer_call=True
                        deadline=min(deadline,now+240)
                    if now-last_progress>=25 or not last_progress:
                        record_flutter_progress(out,scenario,phase,int(now-started),
                                                installed_app,tap_count)
                        last_progress=now
                    # This is only app-op eligibility, not Android approval.
                    if not installed_app:
                        r=command(['adb','-s',SERIAL,'shell','pm','path',APP],allow_failure=True)
                        if r.returncode==0 and r.stdout.strip().startswith(b'package:'):
                            adb('shell','appops','set',APP,'REQUEST_INSTALL_PACKAGES','allow')
                            installed_app=True
                    # CRITICAL: uiautomator.dump can disrupt Flutter startup. Do
                    # not probe Android UI during Gradle/test APK installation.
                    # Probe only after Dart has reached the real installer call.
                    if (installed_app and phase in ('STOCK_INSTALLER_CALL','STOCK_INSTALLER_RETURNED')
                            and tap_count<2):
                        if _tap_confirmed_install_dialog():tap_count+=1
                    time.sleep(2)
                if p.poll() is None:
                    phase=flutter_phase(logfile)
                    record_flutter_progress(out,scenario,phase,int(time.monotonic()-started),
                                            installed_app,tap_count)
                    category,dart_started=record_flutter_failure(out,scenario,attempt,phase,logfile,-1)
                    if split_pre_dart_recovery_allowed(scenario,attempt,phase,dart_started,tap_count):
                        # Flutter's prior process must be fully stopped before
                        # inspecting/reusing the exact v1 Android baseline.
                        terminate_flutter_process_group(p)
                        installed_state(1,False,out/'fixtures')
                        adb('shell','am','force-stop',APP,timeout=20)
                        installed_state(1,False,out/'fixtures')
                        print('OX_R02_RT02_SPLIT_PRE_DART_RETRY category='+category,flush=True)
                        continue
                    raise Refused('RT02_FLUTTER_TIMEOUT: scenario='+scenario+' phase='+phase+
                                  ' app_present='+str(installed_app)+' approvals='+str(tap_count))
                text=logfile.read_text('utf-8','replace')
                phase=flutter_phase(logfile)
                record_flutter_progress(out,scenario,phase,int(time.monotonic()-started),
                                        installed_app,tap_count)
                test_success=p.returncode==0 and 'All tests passed!' in text
                if not test_success:
                    category,dart_started=record_flutter_failure(
                        out,scenario,attempt,phase,logfile,p.returncode)
                    if (attempt==1 and not dart_started and tap_count==0 and
                            phase in ('FLUTTER_STARTING','GRADLE_BUILD','TEST_APK_INSTALL')):
                        # Confirm the real fixture is absent before restarting a
                        # test-runner/bootstrap failure. An installed fixture or
                        # ambiguous package query prevents a retry.
                        if scenario=='split':
                            # V1 is a mandatory installed baseline for an update;
                            # the old 'fixture absent' check was impossible here.
                            terminate_flutter_process_group(p)
                            installed_state(1,False,out/'fixtures')
                            adb('shell','am','force-stop',APP,timeout=20)
                            installed_state(1,False,out/'fixtures')
                        else:
                            empty_or_expected_package()
                        print('OX_R02_RT02_PRE_DART_RETRY scenario='+scenario+
                              ' category='+category,flush=True)
                        continue
                    raise Refused('Flutter real installer test failed ('+scenario+') phase='+phase+
                                  ' category='+category+' rc='+str(p.returncode))
                need(installed_app,'Flutter test APK not installed on emulator')
                # Android's immutable package state is mandatory proof. No
                # approvals are fabricated to turn an update green.
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
                    terminate_flutter_process_group(p)
    raise Refused('both Flutter attempts failed without runtime installation')

def execute(out:Path)->int:
    source,run=host_check()
    out.mkdir(parents=True,exist_ok=True)
    receipt={'schema':2,'status':'NOT_RUN','source_sha':source,'run_id':run,
             'hosted_emulator_only':True,'physical_device_qualified':False,
             'full_r02_matrix_qualified':False,'release_qualified':False,
             'publication_allowed':False,'installer_backend':'production StockInstaller',
             'scenarios':[],'flutter_launches':0,
             'host_acknowledgement_order':[],'dart_event_order':[]}
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
    # OPT05 P02: preserve one_scenario for legacy HF06 recovery regression
    # tests, but run both real Android states in a single Flutter test process.
    from opt05_p02_rt02_session import CASES,EVENTS,run_single_session
    try:
        # The hosted script executes as __main__, while the helper imports
        # r02_rt02_hosted by module name. Convert its independent Refused
        # class into this script's fail-closed exception type.
        try:
            proofs,log_sha=run_single_session(out,inventory)
        except RuntimeError as ex:
            raise Refused('OPT05 P02 Android session refused: '+str(ex)) from ex
        for scenario in ('standalone','split'):
            need(scenario in proofs,'missing one-session Android scenario proof')
            receipt['scenarios'].append(proofs[scenario])
            path.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
        receipt['flutter_launches']=1
        receipt['host_acknowledgement_order']=list(CASES)
        receipt['dart_event_order']=[case+':'+step for case,step in EVENTS]
        receipt['session_log_sha256']=log_sha
        receipt['status']='PASS_TWO_ANDROID_SYSTEM_SESSIONS'
        path.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
        print('OX_R02_RT02_TWO_REAL_SESSIONS_PASS',flush=True)
        print('OX_R02_RT02_OPT05_ONE_FLUTTER_TWO_REAL_INSTALLS_PASS',flush=True)
        return 0
    finally:
        # Only disposable RT02 fixture APK is removed. Never touch user apps.
        adb('shell','pm','uninstall',FIXTURE,allow_failure=True)

def verify(out:Path)->int:
    source,run=identity_check()
    v=json.loads((out/'rt02-receipt.json').read_text())
    for k,expected in {'schema':2,'status':'PASS_TWO_ANDROID_SYSTEM_SESSIONS',
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
    # OPT05 P02: no duplicate compilation or unacknowledged Android outcome.
    from opt05_p02_rt02_session import CASES,EVENTS
    need(type(v.get('flutter_launches')) is int and v['flutter_launches']==1,
         'one Flutter launch required')
    need(v.get('host_acknowledgement_order')==list(CASES) and
         v.get('dart_event_order')==[case+':'+step for case,step in EVENTS],
         'exact two-case host ack and Dart event sequence required')
    digest=v.get('session_log_sha256')
    need(isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest) is not None,
         'one-session private log SHA-256 required')
    print('OX_R02_RT02_OPT05_SINGLE_SESSION_SOURCE_BOUND_VERIFIED',flush=True)
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
