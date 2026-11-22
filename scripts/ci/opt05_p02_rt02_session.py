#!/usr/bin/env python3
"""OPT05 P02 one Flutter launch; two real Android installer transitions.

The local HTTP acknowledgement is withheld until independent ADB proof of the
signed v1 installation or atomic v2+split update. No ADB fixture installation,
no faked platform result, and no retry after Dart or Android activity.
"""
from __future__ import annotations
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import re
import subprocess
import threading
import time

import r02_rt02_hosted as base

CASES=('standalone','split')
STEPS=('START','INSTALL_CALL','INSTALL_RETURNED','ACKED')
EVENTS=tuple((case,step) for case in CASES for step in STEPS)
EVENT_RE=re.compile(r'OX_R02_P02_EVENT=(standalone|split):(START|INSTALL_CALL|INSTALL_RETURNED|ACKED)(?![A-Za-z_])')
MAX_LOG=16*1024*1024

class Refused(base.Refused):pass

def need(ok:bool,why:str)->None:
    if not ok:raise Refused(why)

def sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def events_from_log(log:Path)->tuple[tuple[str,str],...]:
    if not log.is_file():return ()
    need(log.stat().st_size<=MAX_LOG,'bounded private Flutter log size exceeded')
    events=tuple(EVENT_RE.findall(log.read_text('utf8','replace')))
    need(len(events)<=len(EVENTS) and events==EVENTS[:len(events)],
         'reordered, duplicated or missing Dart events')
    return events

class AckState:
    def __init__(self,fixtures:dict[str,Path]):
        self.fixtures=fixtures
        self.acks={case:threading.Event() for case in CASES}

class FixtureServer(BaseHTTPRequestHandler):
    state:AckState
    def do_GET(self):
        target=self.path
        if target.startswith('/ack/'):
            case=target[len('/ack/'):]
            if case not in CASES:
                self.send_error(404);return
            ready=self.state.acks[case].is_set()
            self.send_response(200 if ready else 425)
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length','0')
            self.end_headers();return
        name=target.lstrip('/')
        if name not in self.state.fixtures or '/' in name or '?' in name:
            self.send_error(404);return
        source=self.state.fixtures[name]
        size=source.stat().st_size
        if not 250<=size<=70*1024*1024:
            self.send_error(500);return
        self.send_response(200)
        self.send_header('Content-Type','application/vnd.android.package-archive')
        self.send_header('Content-Length',str(size));self.end_headers()
        with source.open('rb') as src:
            while data:=src.read(65536):self.wfile.write(data)
    def log_message(self,*args):pass

def run_single_session(out:Path,inventory:dict)->tuple[dict[str,dict],str]:
    """One Dart test and one host-proven ack per distinct real install."""
    fixtures=out/'fixtures'
    entries=inventory['files']
    names=('base_v1.apk','base_v2.apk','config.x86_64.apk')
    need(set(entries)==set(names),'three exact signed fixtures required')
    hashes={name:entries[name]['sha256'] for name in names}
    need(all(base.SHA.fullmatch(hashes[name]) and
             sha(fixtures/name)==hashes[name] for name in names) and
         len(set(hashes.values()))==3,'source-bound three distinct APK digests required')
    state=AckState({name:fixtures/name for name in names})
    server=ThreadingHTTPServer(('127.0.0.1',base.PORT),FixtureServer)
    server.RequestHandlerClass.state=state
    log=out/'rt02-opt05-single-session.private.log'
    args=['flutter','test','integration_test/r02_opt05_single_session_test.dart',
          '-d',base.SERIAL,'--flavor','normal','--no-pub','--reporter','expanded',
          '--dart-define=OX_R02_P02_V1_SHA='+hashes['base_v1.apk'],
          '--dart-define=OX_R02_P02_V2_SHA='+hashes['base_v2.apk'],
          '--dart-define=OX_R02_P02_SPLIT_SHA='+hashes['config.x86_64.apk']]
    child=None
    installed_app=False
    done=[]
    proofs={}
    approvals={case:0 for case in CASES}
    start=time.monotonic()
    deadline=start+1800
    last_progress=0.0
    try:
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base.adb('reverse','tcp:'+str(base.PORT),'tcp:'+str(base.PORT))
        with log.open('wb') as output:
            child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=output,
                                   stderr=subprocess.STDOUT,start_new_session=True)
            while child.poll() is None:
                now=time.monotonic()
                need(now<deadline,'RT02_FLUTTER_TIMEOUT: bounded one-session runtime')
                events=events_from_log(log)
                if not installed_app:
                    probe=base.command(['adb','-s',base.SERIAL,'shell','pm','path',base.APP],
                                       allow_failure=True)
                    if probe.returncode==0 and probe.stdout.strip().startswith(b'package:'):
                        base.adb('shell','appops','set',base.APP,'REQUEST_INSTALL_PACKAGES','allow')
                        installed_app=True
                pending=next((case for case in CASES if case not in done),None)
                if pending is None:
                    time.sleep(1);continue
                phase=('STOCK_INSTALLER_RETURNED' if (pending,'INSTALL_RETURNED') in events else
                       'STOCK_INSTALLER_CALL' if (pending,'INSTALL_CALL') in events else
                       'DART_TEST_STARTED' if (pending,'START') in events else
                       base.flutter_phase(log))
                # UI probes start ONLY after the actual production installer call.
                if (installed_app and (pending,'INSTALL_CALL') in events and
                        (pending,'INSTALL_RETURNED') not in events and approvals[pending]==0):
                    if base._tap_confirmed_install_dialog():approvals[pending]=1
                if (pending,'INSTALL_RETURNED') in events:
                    # v1 bytes/version MUST be independently proven before the
                    # Dart test can proceed to the split upgrade; likewise v2
                    # base + config bytes are mandatory before the final ack.
                    actual=base.installed_state(1 if pending=='standalone' else 2,
                                                 pending=='split',fixtures)
                    approval_path=base.classify_android_approval(pending,approvals[pending],actual)
                    actual.update(scenario=pending,android_confirmations=approvals[pending],
                                  approval_path=approval_path)
                    proofs[pending]=actual
                    done.append(pending)
                    base.record_flutter_progress(out,pending,'ANDROID_PACKAGE_STATE_VERIFIED',
                                                 int(now-start),installed_app,approvals[pending])
                    state.acks[pending].set()
                    print('OX_R02_RT02_REAL_'+pending.upper()+'_PASS',flush=True)
                    print('OX_R02_RT02_ANDROID_APPROVAL_PATH='+pending+':'+approval_path,flush=True)
                if not last_progress or now-last_progress>=25:
                    base.record_flutter_progress(out,pending,phase,int(now-start),
                                                 installed_app,approvals[pending])
                    last_progress=now
                time.sleep(1)
            events=events_from_log(log)
            msg=log.read_text('utf8','replace')
            need(child.returncode==0 and 'All tests passed!' in msg,
                 'Flutter one-session test failed; private_log_sha256='+sha(log))
            need(installed_app and done==list(CASES) and events==EVENTS and
                 all(state.acks[case].is_set() for case in CASES),
                 'missing one-session real Android acknowledgement and Dart event ordering')
            # Validate the final installed split state again after Dart exit.
            base.installed_state(2,True,fixtures)
            return proofs,sha(log)
    finally:
        if child is not None and child.poll() is None:
            base.terminate_flutter_process_group(child)
        base.adb('reverse','--remove','tcp:'+str(base.PORT),allow_failure=True)
        server.shutdown();server.server_close()
