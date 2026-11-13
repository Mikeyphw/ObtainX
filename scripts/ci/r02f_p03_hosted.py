#!/usr/bin/env python3
"""R02F P03 actual app UI tap -> provider -> native abandon -> signed baseline.

Runs ONLY inside the already-qualified hosted API36 emulator. Android's system
installer may show approval, but we never tap Install or issue adb install-abandon.
The Flutter integration test taps the exact production Cancel widget. Raw logs
are local-only; the published receipt includes only tightly bounded checksums.
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

import r02_rt02_hosted as base
import r02_rt02c_hosted as rt02c

RECEIPT = 'r02f-p03-app-ui-cancel.json'
SUCCESS = 'PASS_APP_UI_NATIVE_PENDING_APPROVAL_CANCEL_V1_BYTES_INTACT'
MARKERS = (
    'OX_P03_DART_STAGE=APP_ROUTE_OWNER_SURVIVED',
    'OX_P03_DART_STAGE=PRODUCTION_PROVIDER_INSTALL_STARTED',
    'OX_P03_DART_STAGE=ANDROID_APPROVAL_PENDING',
    'OX_P03_DART_STAGE=REAL_APP_PAGE_CANCEL_TAPPED',
    'OX_P03_DART_STAGE=APP_OWNED_CANCEL_RESULT_VERIFIED',
)

class Refused(RuntimeError): pass

def need(ok: bool, reason: str) -> None:
    if not ok: raise Refused(reason)

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

class P03Handler(BaseHTTPRequestHandler):
    fixtures: Path
    baseline: dict
    foreground_count: int = 0

    def log_message(self, *args): pass

    def do_GET(self):
        files = {'/fixtures/base_v2.apk': 'base_v2.apk',
                 '/fixtures/config.x86_64.apk': 'config.x86_64.apk'}
        name = files.get(self.path)
        if name is None:
            self.send_error(404); return
        p = self.fixtures / name
        data = p.read_bytes()
        if not 1000 < len(data) < 16*1024*1024:
            self.send_error(422); return
        self.send_response(200)
        self.send_header('Content-Type', 'application/vnd.android.package-archive')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != '/p03/foreground' or self.headers.get('Content-Length') != '0':
            self.send_error(403); return
        if P03Handler.foreground_count:
            self.send_error(409); return
        try:
            # Device baseline must still match after the system displayed the
            # approval prompt; no install was approved by host input.
            need(rt02c.baseline_v1(self.fixtures) == self.baseline,
                 'v1 baseline changed before UI cancellation')
            window = base.adb('shell','dumpsys','window','windows', timeout=25).lower()
            need('packageinstaller' in window or 'permissioncontroller' in window,
                 'Android user-approval screen not observed')
            # Reuse the same Flutter test Activity; CLEAR_TOP | SINGLE_TOP
            # prevents the Android installer overlay from spawning a second
            # MainActivity and destroying the in-flight integration test.
            base.adb('shell','am','start','-f','0x24000000','-n',
                     base.APP+'/dev.imranr.obtainium.MainActivity', timeout=30)
            P03Handler.foreground_count += 1
        except (Refused, base.Refused, subprocess.TimeoutExpired) as exc:
            self.send_error(409, str(exc)[:120]); return
        data = b'foreground_ready'
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def run(out: Path) -> int:
    source, runid = base.host_check()
    need(out.is_absolute(), 'evidence destination must be absolute')
    out.mkdir(parents=True, exist_ok=True)
    fixtures = out/'fixtures'
    inv = json.loads((fixtures/'fixture_inventory.json').read_text())
    need(inv.get('source_sha') == source and inv.get('fixture_package') == base.FIXTURE,
         'not source-bound RT02 fixture inventory')
    for name in ('base_v1.apk','base_v2.apk','config.x86_64.apk'):
        need(sha(fixtures/name) == inv['files'][name]['sha256'], 'fixture SHA mismatch '+name)
    # Disposable signed baseline. All subsequent cancellation is initiated by
    # ObtainX's production UI; ADB never abandons or commits the v2 session.
    base.adb('install','-r','-t',str(fixtures/'base_v1.apk'),timeout=80)
    before = rt02c.baseline_v1(fixtures)
    P03Handler.fixtures = fixtures
    P03Handler.baseline = before
    P03Handler.foreground_count = 0
    server = ThreadingHTTPServer(('127.0.0.1', base.PORT), P03Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log = out/'r02f-p03-private.log'
    try:
        base.adb('reverse','tcp:'+str(base.PORT),'tcp:'+str(base.PORT))
        # The Flutter runner's normal debug app is installed by flutter test.
        # No root, privileged installer, or personal Android device is touched.
        argv = ['flutter','test','integration_test/r02f_p03_app_cancel_test.dart',
                '-d',base.SERIAL,'--flavor','normal','--no-pub',
                '--reporter','expanded',
                '--dart-define=OX_P03_BASE_SHA='+inv['files']['base_v2.apk']['sha256'],
                '--dart-define=OX_P03_SPLIT_SHA='+inv['files']['config.x86_64.apk']['sha256']]
        print('OX_R02F_P03_HOSTED_APP_UI_STARTED source='+source, flush=True)
        started=time.monotonic()
        with log.open('wb') as f:
            process=subprocess.Popen(argv,stdout=f,stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL)
            stage='FLUTTER_STARTING'
            last_report=0.0
            while process.poll() is None and time.monotonic()-started < 1100:
                tail=log.read_text('utf-8','replace')[-50000:]
                if MARKERS[-1] in tail: stage='UI_CANCEL_COMPLETED'
                elif MARKERS[-2] in tail: stage='UI_CANCEL_TAPPED'
                elif MARKERS[2] in tail: stage='APPROVAL_PENDING'
                elif MARKERS[1] in tail: stage='PRODUCTION_PROVIDER_INSTALL_STARTED'
                elif MARKERS[0] in tail: stage='APP_ROUTE_OWNER_SURVIVED'
                elif 'Running Gradle task' in tail: stage='GRADLE_BUILD'
                if base.command(['adb','-s',base.SERIAL,'shell','pm','path',base.APP],
                                allow_failure=True).returncode == 0:
                    base.adb('shell','appops','set',base.APP,'REQUEST_INSTALL_PACKAGES','allow',timeout=25)
                if time.monotonic()-last_report>=25:
                    print('OX_R02F_P03_HOSTED_PROGRESS stage='+stage+
                          ' elapsed='+str(int(time.monotonic()-started))+'s',flush=True)
                    last_report=time.monotonic()
                time.sleep(3)
            if process.poll() is None:
                process.kill();process.wait(timeout=20)
                raise Refused('Flutter runtime P03 timed out in '+stage)
        text=log.read_text('utf-8','replace')
        need(process.returncode==0 and 'All tests passed!' in text,
             'Flutter P03 app UI test failed, log_sha256='+sha(log))
        for marker in MARKERS:
            need(text.count(marker) == 1, 'missing/duplicate real UI marker: '+marker)
        need(P03Handler.foreground_count == 1,
             'host never observed Android approval and returned to actual app UI')
        after = rt02c.baseline_v1(fixtures)
        need(before == after,
             'P03 app Cancel mutated signed v1 installed version or base APK bytes')
        # Persist only explicit results, never turn source-only checks into PASS.
        receipt = {'schema':1,'status':SUCCESS,'head_sha':source,'run_id':runid,
                   'baseline_before':before,'baseline_after':after,
                   'v2_base_sha256':sha(fixtures/'base_v2.apk'),
                   'v2_split_sha256':sha(fixtures/'config.x86_64.apk'),
                   'ui_cancel_widget_tapped':True,
                   'native_session_abandoned_from_application':True,
                   'android_approval_observed':True,'external_or_root_installer_used':False,
                   'installed_v1_signed_bytes_preserved':True,
                   'flutter_log_sha256':sha(log),
                   'raw_logs_uploaded':False,'physical_device_qualified':False,
                   'external_shizuku_dhizuku_qualified':False,
                   'release_qualified':False}
        (out/RECEIPT).write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
        print('OX_R02F_P03_HOSTED_REAL_APP_UI_CANCEL_AND_V1_BYTES_PASS',flush=True)
        return 0
    finally:
        server.shutdown();server.server_close()
        base.adb('reverse','--remove','tcp:'+str(base.PORT), allow_failure=True)


def verify(out: Path) -> int:
    source,runid = base.host_check()
    fixture_dir = out/'fixtures'
    obj = json.loads((out/RECEIPT).read_text())
    need(obj.get('head_sha') == source and obj.get('run_id') == runid,
         'source/run receipt mismatch')
    need(obj.get('status') == SUCCESS and obj.get('schema') == 1,
         'missing successful real hosted UI receipt')
    need(obj.get('baseline_before') == obj.get('baseline_after') == rt02c.baseline_v1(fixture_dir),
         'Android installed baseline changed after receipt')
    need(all(obj.get(k) is True for k in (
        'ui_cancel_widget_tapped','native_session_abandoned_from_application',
        'android_approval_observed','installed_v1_signed_bytes_preserved')),
        'missing real UI/Android proof')
    need(obj.get('v2_base_sha256')==sha(fixture_dir/'base_v2.apk') and
         obj.get('v2_split_sha256')==sha(fixture_dir/'config.x86_64.apk'),
         'signed v2 fixture drift')
    need(obj.get('flutter_log_sha256')==sha(out/'r02f-p03-private.log'),
         'private runtime log no longer matches receipt')
    print('OX_R02F_P03_INDEPENDENT_ANDROID_UI_CANCEL_RECEIPT_PASS',flush=True)
    return 0


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('command', choices=['run','verify'])
    ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args()
    try:
        return run(a.out) if a.command=='run' else verify(a.out)
    except (OSError,ValueError,KeyError,TypeError,Refused,base.Refused,rt02c.Refused) as e:
        print('OX_R02F_P03_REFUSED: '+str(e),file=sys.stderr,flush=True)
        return 2

if __name__=='__main__': sys.exit(main())
