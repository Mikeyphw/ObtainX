#!/usr/bin/env python3
"""OPT05 P01: one real Flutter session, two Android rejection cases.

The Dart test cannot enter case 2 until this independent host has proved
that the signed v2 installation survived case 1 without byte/version changes.
All evidence is emulator-only, source-bound, and non-release qualification.
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

import r02_rt02_hosted as base
from r02_rt02b_fixture import WRONG, BASE

CASES=('signature_mismatch','downgrade')
EVENTS=tuple((case,step) for case in CASES
             for step in ('START','INSTALL_CALL','REJECTED','ACKED'))
EVENT_RE=re.compile(r'OX_R02B_EVENT=(signature_mismatch|downgrade):(START|INSTALL_CALL|REJECTED|ACKED)(?![A-Za-z_])')
RECEIPT='rt02b-receipt.json'
PHASES=('FLUTTER_STARTING','GRADLE_BUILD','TEST_APK_INSTALL',
        'DART_TEST_STARTED','STOCK_INSTALLER_CALL','STOCK_INSTALLER_RETURNED',
        'ANDROID_UNCHANGED_VERIFIED')

class Refused(RuntimeError):pass

def need(ok:bool,detail:str)->None:
    if not ok:raise Refused(detail)

def sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def record(out:Path,case:str,phase:str,elapsed:int,taps:int)->None:
    need(case in CASES and phase in PHASES and type(taps) is int and taps in (0,1),
         'invalid bounded RT02B progress')
    state={'schema':2,'case':case,'phase':phase,'elapsed_seconds':elapsed,
           'approved_installer_taps':taps,'flutter_launches':1,
           'raw_logs_uploaded':False}
    (out/'rt02b-progress.json').write_text(json.dumps(state,sort_keys=True,indent=2)+'\n')
    print(f'OX_R02_RT02B_PROGRESS case={case} phase={phase} elapsed={elapsed}s approvals={taps}',flush=True)

def baseline_unchanged(fixtures:Path)->dict:
    """Independent real Android PM and installed APK SHA; no simulated install."""
    paths=base.adb('shell','pm','path',base.FIXTURE).splitlines()
    need(len(paths)==1 and paths[0].startswith('package:/data/app/') and
         paths[0].endswith('/base.apk'),'installed fixture package/splits changed')
    match=re.fullmatch(r'package:(/data/app/[A-Za-z0-9_+./~=-]+/base\.apk)',paths[0])
    need(match is not None,'untrusted installed fixture path')
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

def events_from_log(log:Path)->tuple[tuple[str,str],...]:
    if not log.is_file():return ()
    need(log.stat().st_size<=16*1024*1024,'private Flutter log exceeded bound')
    events=tuple(EVENT_RE.findall(log.read_text('utf8','replace')))
    need(len(events)<=len(EVENTS) and events==EVENTS[:len(events)],
         'missing, reordered, or duplicate real Dart events')
    return events

class AckState:
    def __init__(self,files:dict[str,Path]):
        self.files=files
        self.acks={case:threading.Event() for case in CASES}

class FixtureServer(BaseHTTPRequestHandler):
    state:AckState
    def do_GET(self):
        # Fixed allowlist only; no arbitrary filesystem access or dynamic paths.
        path=self.path
        if path.startswith('/ack/'):
            case=path[len('/ack/'):]
            if case not in CASES:
                self.send_error(404);return
            approved=self.state.acks[case].is_set()
            self.send_response(200 if approved else 425)
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length','0')
            self.end_headers();return
        name=path.lstrip('/')
        if name not in self.state.files or '/' in name or '?' in name:
            self.send_error(404);return
        src=self.state.files[name]
        size=src.stat().st_size
        if not 250<=size<=70*1024*1024:
            self.send_error(500);return
        self.send_response(200)
        self.send_header('Content-Type','application/vnd.android.package-archive')
        self.send_header('Content-Length',str(size));self.end_headers()
        with src.open('rb') as stream:
            while chunk:=stream.read(65536):self.wfile.write(chunk)
    def log_message(self,*args):pass

def validate_inventory(fixtures:Path,source:str)->tuple[dict,dict]:
    initial=json.loads((fixtures/'fixture_inventory.json').read_text())
    extra=json.loads((fixtures/'rt02b_inventory.json').read_text())
    need(initial.get('source_sha')==source and extra.get('source_sha')==source and
         initial.get('fixture_package')==base.FIXTURE and
         extra.get('fixture_package')==base.FIXTURE,'source-bound fixture mismatch')
    need(initial['files'][BASE]['sha256']==sha(fixtures/BASE)==extra['original_sha256'],
         'signed baseline integrity mismatch')
    need(extra['wrong_sha256']==sha(fixtures/WRONG) and
         re.fullmatch(r'[0-9a-f]{64}',extra['wrong_sha256']) is not None,
         'signed wrong-certificate fixture hash mismatch')
    need(initial['files']['base_v1.apk']['sha256']==sha(fixtures/'base_v1.apk'),
         'downgrade fixture hash mismatch')
    need(extra['original_cert_sha256']!=extra['wrong_cert_sha256'] and
         extra['ephemeral_keys_deleted'] is True,
         'wrong signing identity or ephemeral-key cleanup not proven')
    return initial,extra

def run_one_session(out:Path,fixtures:Path,initial:dict,extra:dict)->tuple[list[dict],str]:
    state=AckState({WRONG:fixtures/WRONG,'base_v1.apk':fixtures/'base_v1.apk'})
    server=ThreadingHTTPServer(('127.0.0.1',base.PORT),FixtureServer)
    server.RequestHandlerClass.state=state
    log=out/'rt02b-single-session.private.log'
    cases:list[dict]=[]
    taps={case:0 for case in CASES}
    done=[];installed=False
    args=['flutter','test','integration_test/r02b_rejection_test.dart',
          '-d',base.SERIAL,'--flavor','normal','--no-pub','--reporter','expanded',
          '--dart-define=OX_R02B_WRONG_SHA256='+extra['wrong_sha256'],
          '--dart-define=OX_R02B_DOWNGRADE_SHA256='+initial['files']['base_v1.apk']['sha256']]
    start=time.monotonic();deadline=start+1800;last_record=0
    child=None
    try:
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base.adb('reverse','tcp:'+str(base.PORT),'tcp:'+str(base.PORT))
        with log.open('wb') as target:
            child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=target,
                                   stderr=subprocess.STDOUT,start_new_session=True)
            while child.poll() is None:
                now=time.monotonic()
                need(now<deadline,'bounded Flutter negative-test timeout')
                sequence=events_from_log(log)
                if not installed:
                    probe=base.command(['adb','-s',base.SERIAL,'shell','pm','path',base.APP],
                                       allow_failure=True)
                    if probe.returncode==0 and probe.stdout.strip().startswith(b'package:'):
                        base.adb('shell','appops','set',base.APP,'REQUEST_INSTALL_PACKAGES','allow')
                        installed=True
                pending=next((case for case in CASES if case not in done),None)
                if pending is None:
                    time.sleep(1);continue
                phase=('STOCK_INSTALLER_RETURNED' if (pending,'REJECTED') in sequence else
                       'STOCK_INSTALLER_CALL' if (pending,'INSTALL_CALL') in sequence else
                       'DART_TEST_STARTED' if (pending,'START') in sequence else
                       base.flutter_phase(log))
                # Only probe the actual system installer after this case invoked
                # production StockInstaller. Never use blind taps or retries.
                if installed and phase=='STOCK_INSTALLER_CALL' and taps[pending]==0:
                    if base._tap_confirmed_install_dialog():taps[pending]=1
                if (pending,'REJECTED') in sequence and pending not in done:
                    # Dart is blocked on /ack/<case>; prove the real installed
                    # baseline is unchanged *before* allowing the next case.
                    proof=baseline_unchanged(fixtures)
                    proof.update({'case':pending,'stock_installer_error_observed':True,
                                  'android_confirmation_count':taps[pending]})
                    cases.append(proof)
                    done.append(pending)
                    record(out,pending,'ANDROID_UNCHANGED_VERIFIED',int(now-start),taps[pending])
                    state.acks[pending].set()
                    print('OX_R02_RT02B_'+pending.upper()+'_REJECTED_AND_UNCHANGED_PASS',flush=True)
                if now-last_record>=25:
                    record(out,pending,phase,int(now-start),taps[pending]);last_record=now
                time.sleep(1)
            sequence=events_from_log(log)
            text=log.read_text('utf8','replace')
            need(child.returncode==0 and 'All tests passed!' in text,
                 'one real Flutter integration-test invocation failed; log_sha256='+sha(log))
            need(sequence==EVENTS and done==list(CASES) and installed,
                 'missing exact two-case Dart and Android acknowledgement sequence')
            need(all(state.acks[case].is_set() for case in CASES),
                 'missing host acknowledgements')
            baseline_unchanged(fixtures)
            session_sha=sha(log)
            for proof in cases:proof['flutter_log_sha256']=session_sha
            return cases,session_sha
    finally:
        if child is not None and child.poll() is None:
            base.terminate_flutter_process_group(child)
        base.adb('reverse','--remove','tcp:'+str(base.PORT),allow_failure=True)
        server.shutdown();server.server_close()

def execute(out:Path)->int:
    source,run=base.host_check()
    need(out.is_absolute(),'absolute evidence directory required')
    out.mkdir(parents=True,exist_ok=True)
    receipt={'schema':2,'source_sha':source,'run_id':run,'status':'NOT_RUN',
             'hosted_emulator_only':True,'physical_device_qualified':False,
             'full_r02_matrix_qualified':False,'release_qualified':False,
             'publication_allowed':False,'backend':'production StockInstaller',
             'flutter_launches':0,'host_acknowledgement_order':[],
             'android_negative_cases':[]}
    rp=out/RECEIPT;rp.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
    fixtures=out/'fixtures'
    initial,extra=validate_inventory(fixtures,source)
    base.empty_or_expected_package()
    # ADB is ONLY used to establish the disposable v2 precondition.
    try:
        base.adb('install','-t',str(fixtures/BASE),timeout=180)
        baseline_unchanged(fixtures)
        proofs,log_sha=run_one_session(out,fixtures,initial,extra)
        receipt.update(status='PASS_TWO_REAL_ANDROID_REJECTIONS',
                       flutter_launches=1,host_acknowledgement_order=list(CASES),
                       session_log_sha256=log_sha,android_negative_cases=proofs)
        rp.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
        print('OX_R02_RT02B_SINGLE_FLUTTER_SESSION_TWO_REJECTIONS_PASS',flush=True)
        return 0
    finally:
        base.adb('shell','pm','uninstall',base.FIXTURE,allow_failure=True)

def verify(out:Path)->int:
    source,run=base.identity_check()
    d=json.loads((out/RECEIPT).read_text())
    expected={'schema':2,'source_sha':source,'run_id':run,
              'status':'PASS_TWO_REAL_ANDROID_REJECTIONS',
              'hosted_emulator_only':True,'physical_device_qualified':False,
              'full_r02_matrix_qualified':False,'release_qualified':False,
              'publication_allowed':False,'backend':'production StockInstaller',
              'flutter_launches':1,'host_acknowledgement_order':list(CASES)}
    for k,v in expected.items():need(d.get(k)==v,'single-session receipt invalid: '+k)
    cases=d.get('android_negative_cases')
    need(isinstance(cases,list) and len(cases)==2,'two Android negative proofs required')
    session_sha=d.get('session_log_sha256')
    need(isinstance(session_sha,str) and re.fullmatch('[0-9a-f]{64}',session_sha),
         'missing private single-session log digest')
    for case,name in zip(cases,CASES):
        need(isinstance(case,dict) and case.get('case')==name,
             'missing or reordered Android negative proof')
        need(case.get('installed_original_intact') is True and
             case.get('stock_installer_error_observed') is True and
             case.get('version_code')==2 and case.get('installed_path_count')==1,
             'missing independent unchanged Android state')
        need(type(case.get('android_confirmation_count')) is int and
             case['android_confirmation_count'] in (0,1),'invalid Android dialog count')
        for field in ('base_sha256','flutter_log_sha256'):
            need(isinstance(case.get(field),str) and
                 re.fullmatch('[0-9a-f]{64}',case[field]),
                 'missing bound provenance '+field)
        need(case['flutter_log_sha256']==session_sha,
             'case not bound to the one Flutter session')
    need(cases[0]['base_sha256']==cases[1]['base_sha256'],
         'Android baseline changed between independent rejections')
    print('OX_R02_RT02B_SINGLE_SESSION_SOURCE_BOUND_VERIFIED: no release qualification',flush=True)
    return 0

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=('run','verify'))
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
