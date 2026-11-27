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
from r02f_p03_failure_diagnostics import write_failure

RECEIPT = 'r02f-p03-app-ui-cancel.json'
AUDIT = 'r02f-p03-android-audit.json'
SUCCESS = 'PASS_APP_UI_NATIVE_PENDING_APPROVAL_CANCEL_V1_BYTES_INTACT'
AUDIT_SUCCESS = 'PASS_INDEPENDENT_LIVE_ANDROID_V1_BASELINE_AUDIT'
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

# The native pending-approval callback precedes Android drawing/focusing its
# window. Wait for a fresh focused window, not a stale package name anywhere
# in dumpsys. This is a hosted harness boundary, not an installer retry.
FOREGROUND_BUDGET = 55.0
APPROVAL_FOCUS_BUDGET = 20.0
FOREGROUND_COMPONENT = base.APP+'/dev.imranr.obtainium.MainActivity'
FOREGROUND_REFUSALS = frozenset({
    'P03_BASELINE_REFUSED', 'P03_WINDOW_QUERY_REFUSED',
    'P03_APPROVAL_FOCUS_TIMEOUT', 'P03_FOREGROUND_START_REFUSED',
    'P03_APP_FOCUS_TIMEOUT', 'P03_FOREGROUND_DEADLINE',
    'P03_FOREGROUND_DUPLICATE', 'P03_FOREGROUND_REQUEST_REFUSED',
})


class ForegroundRefused(Refused):
    def __init__(self, code: str):
        if code not in FOREGROUND_REFUSALS:
            raise ValueError('invalid foreground refusal code')
        super().__init__(code)


def focused_component(window: str) -> str | None:
    # Restrict the observation to user 0, one unambiguous focused window.
    # mFocusedApp and historical Window entries are not focus evidence.
    lines = re.findall(r'(?m)^\s*mCurrentFocus=([^\r\n]*)$', window)
    if len(lines) != 1:
        return None
    match = re.fullmatch(r'Window\{[0-9a-fA-F]+ u0 ([A-Za-z0-9_.]+/[A-Za-z0-9_.$]+)\}',
                         lines[0].strip())
    return match.group(1) if match else None


def wait_focused_window(predicate, deadline: float, refusal: str) -> None:
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            window = base.adb('shell','dumpsys','window','windows',
                              timeout=min(5, remaining))
        except (base.Refused, subprocess.TimeoutExpired) as exc:
            raise ForegroundRefused('P03_WINDOW_QUERY_REFUSED') from exc
        component = focused_component(window)
        if time.monotonic() < deadline and component is not None and predicate(component):
            return
        time.sleep(max(0, min(0.4, deadline-time.monotonic())))
    raise ForegroundRefused(refusal)


def restore_app_foreground(fixtures: Path, baseline: dict) -> None:
    deadline = time.monotonic() + FOREGROUND_BUDGET
    # No Install tap, no ADB session abandonment, no activity restart retry.
    # The owned Dart operation already proved an active pending session.
    wait_focused_window(lambda c: c.split('/',1)[0] in base.APPROVERS,
                        min(deadline, time.monotonic()+APPROVAL_FOCUS_BUDGET),
                        'P03_APPROVAL_FOCUS_TIMEOUT')
    try:
        unchanged = rt02c.baseline_v1(fixtures, deadline=deadline) == baseline
    except (Refused, base.Refused, rt02c.Refused, subprocess.TimeoutExpired, OSError) as exc:
        raise ForegroundRefused('P03_BASELINE_REFUSED') from exc
    if not unchanged:
        raise ForegroundRefused('P03_BASELINE_REFUSED')
    # A slow baseline probe must never authorize a late foreground mutation.
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ForegroundRefused('P03_FOREGROUND_DEADLINE')
    # Recheck current approval after the baseline probe, before bringing the
    # same existing Activity forward (CLEAR_TOP | SINGLE_TOP).
    wait_focused_window(lambda c: c.split('/',1)[0] in base.APPROVERS,
                        min(deadline, time.monotonic()+5),
                        'P03_APPROVAL_FOCUS_TIMEOUT')
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ForegroundRefused('P03_FOREGROUND_DEADLINE')
    try:
        result = base.adb('shell','am','start','-f','0x24000000','-n',
                          FOREGROUND_COMPONENT, timeout=min(10, remaining))
    except (base.Refused, subprocess.TimeoutExpired) as exc:
        raise ForegroundRefused('P03_FOREGROUND_START_REFUSED') from exc
    if re.search(r'(?im)^\s*(?:error|exception|securityexception)\b', result):
        raise ForegroundRefused('P03_FOREGROUND_START_REFUSED')
    wait_focused_window(lambda c: c == FOREGROUND_COMPONENT, deadline,
                        'P03_APP_FOCUS_TIMEOUT')


class P03Handler(BaseHTTPRequestHandler):
    fixtures: Path
    baseline: dict
    foreground_count: int = 0
    foreground_attempted: bool = False
    foreground_lock = threading.Lock()

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
        # Exactly one foreground attempt, including refusal. A second request
        # cannot duplicate a mutation whose outcome was uncertain.
        with P03Handler.foreground_lock:
            if P03Handler.foreground_attempted:
                self.send_error(409, 'P03_FOREGROUND_DUPLICATE'); return
            P03Handler.foreground_attempted = True
        try:
            restore_app_foreground(self.fixtures, self.baseline)
        except ForegroundRefused as exc:
            # Publish only a fixed category. No raw dumpsys, ADB text or paths.
            code = str(exc)
            print('OX_R02F_P03_FOREGROUND_REFUSED code='+code, flush=True)
            self.send_error(409, code); return
        with P03Handler.foreground_lock:
            P03Handler.foreground_count += 1
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
    P03Handler.foreground_attempted = False
    server = ThreadingHTTPServer(('127.0.0.1', base.PORT), P03Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log = out/'r02f-p03-private.log'
    process = None
    eligible_seen = False
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
                                     stdin=subprocess.DEVNULL,start_new_session=True)
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
                # Flutter may replace the debug APK between path and UID
                # lookup. Defer only exact clean absence/No UID observations
                # while this live child is bounded by the original deadline.
                # Stop changing eligibility once approval is observed.
                if stage not in ('APPROVAL_PENDING','UI_CANCEL_TAPPED','UI_CANCEL_COMPLETED'):
                    eligible_now = base.grant_runner_install_eligibility()
                    eligible_seen = eligible_seen or eligible_now
                if time.monotonic()-last_report>=25:
                    print('OX_R02F_P03_HOSTED_PROGRESS stage='+stage+
                          ' elapsed='+str(int(time.monotonic()-started))+'s',flush=True)
                    last_report=time.monotonic()
                time.sleep(3)
            if process.poll() is None:
                base.terminate_flutter_process_group(process)
                raise Refused('Flutter runtime P03 timed out in '+stage)
        text=log.read_text('utf-8','replace')
        # Flutter can terminate before the next progress tick. Report only
        # the final fixed milestone, never private log lines or device data.
        final_stage = stage
        for marker, label in reversed(tuple(zip(MARKERS, (
            'APP_ROUTE_OWNER_SURVIVED', 'PRODUCTION_PROVIDER_INSTALL_STARTED',
            'APPROVAL_PENDING', 'UI_CANCEL_TAPPED', 'UI_CANCEL_COMPLETED',
        )))):
            if marker in text:
                final_stage = label
                break
        if process.returncode != 0 or 'All tests passed!' not in text:
            stage = final_stage
            diag = write_failure(out, log, process.returncode, stage, source, runid)
            raise Refused('Flutter P03 app UI test failed; diagnostic_categories='+
                          ','.join(diag['failure_categories'])+
                          '; private_log_sha256='+diag['private_log_sha256'])
        need(eligible_seen, 'P03 runner eligibility was never established')
        for marker in MARKERS:
            need(text.count(marker) == 1, 'missing/duplicate real UI marker: '+marker)
        first_party = text.count('OX_P03_DART_CLOSURE=FIRST_PARTY_ABANDON') == 1
        android_abort = text.count('OX_P03_DART_CLOSURE=ANDROID_ABORT_OBSERVED') == 1
        need(first_party != android_abort,
             'exclusive, source-bound native/Android cancellation origin unproven')
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
                   'native_session_abandoned_from_application':first_party,
                   'android_abort_observed_before_cancel':android_abort,
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
        try:
            if process is not None and process.poll() is None:
                base.terminate_flutter_process_group(process)
        finally:
            server.shutdown();server.server_close()
            base.adb('reverse','--remove','tcp:'+str(base.PORT), allow_failure=True)


def bounded_json(path: Path) -> dict:
    need(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= 131072,
         'missing or unbounded P03 evidence: '+path.name)
    obj = json.loads(path.read_text(encoding='utf8'))
    need(isinstance(obj, dict), 'non-object P03 evidence: '+path.name)
    return obj


def static_evidence(out: Path, source: str, runid: str) -> dict:
    # Deliberately NO ADB in this helper. Called inside the emulator during
    # audit and outside the emulator during independent artifact verification.
    fixture_dir = out/'fixtures'
    obj = bounded_json(out/RECEIPT)
    need(obj.get('head_sha') == source and str(obj.get('run_id')) == runid,
         'source/run receipt mismatch')
    need(obj.get('status') == SUCCESS and obj.get('schema') == 1,
         'missing successful real hosted UI receipt')
    need(obj.get('baseline_before') == obj.get('baseline_after'),
         'P03 before/after v1 baseline mismatch')
    need(all(obj.get(k) is True for k in (
        'ui_cancel_widget_tapped','android_approval_observed',
        'installed_v1_signed_bytes_preserved')),
         'missing real UI/Android proof')
    need(type(obj.get('native_session_abandoned_from_application')) is bool and
         type(obj.get('android_abort_observed_before_cancel')) is bool and
         obj['native_session_abandoned_from_application'] != obj['android_abort_observed_before_cancel'],
         'exclusive native versus Android abort evidence missing')
    need(all(obj.get(k) is False for k in (
        'raw_logs_uploaded','physical_device_qualified',
        'external_or_root_installer_used','external_shizuku_dhizuku_qualified',
        'release_qualified')),
         'P03 receipt claims an unqualified scope')
    need(obj.get('v2_base_sha256')==sha(fixture_dir/'base_v2.apk') and
         obj.get('v2_split_sha256')==sha(fixture_dir/'config.x86_64.apk'),
         'signed v2 fixture drift')
    need(obj.get('flutter_log_sha256')==sha(out/'r02f-p03-private.log'),
         'private runtime log no longer matches receipt')
    return obj


def audit(out: Path) -> int:
    # Runs WITHIN the same live API36 emulator as the real production UI tap.
    # Never replace this check with offline receipt self-attestation.
    source, runid = base.host_check()
    need(out.is_absolute(), 'absolute P03 evidence root required')
    need(not (out/AUDIT).exists(), 'stale live Android audit receipt exists')
    obj = static_evidence(out, source, runid)
    fresh = rt02c.baseline_v1(out/'fixtures')
    need(obj['baseline_before'] == obj['baseline_after'] == fresh,
         'INDEPENDENT LIVE Android v1 installed version/APK bytes changed')
    proof = {
        'schema': 1,
        'status': AUDIT_SUCCESS,
        'head_sha': source,
        'run_id': runid,
        'receipt_sha256': sha(out/RECEIPT),
        'signed_v1_installed_state': fresh,
        'android_live_queried': True,
        'android_api_36_emulator': True,
        'physical_device_qualified': False,
        'release_qualified': False,
    }
    (out/AUDIT).write_text(json.dumps(proof, sort_keys=True, indent=2)+'\n', encoding='utf8')
    print('OX_R02F_P03_INDEPENDENT_ANDROID_UI_CANCEL_RECEIPT_PASS',flush=True)
    return 0


def verify(out: Path) -> int:
    # Runner has SHUT DOWN its emulator here. Only verify the receipt which
    # audit emitted *after* its independent live Android state query.
    source, runid = base.identity_check()
    need(out.is_absolute(), 'absolute P03 evidence root required')
    obj = static_evidence(out, source, runid)
    proof = bounded_json(out/AUDIT)
    required = {'schema', 'status', 'head_sha', 'run_id', 'receipt_sha256',
                'signed_v1_installed_state', 'android_live_queried',
                'android_api_36_emulator', 'physical_device_qualified',
                'release_qualified'}
    need(set(proof) == required, 'P03 independent audit schema mismatch')
    need(proof.get('schema') == 1 and proof.get('status') == AUDIT_SUCCESS,
         'P03 live Android audit never passed')
    need(proof.get('head_sha') == source and str(proof.get('run_id')) == runid,
         'P03 live Android audit belongs to another source/run')
    need(proof.get('receipt_sha256') == sha(out/RECEIPT),
         'P03 main receipt modified after live Android audit')
    need(proof.get('signed_v1_installed_state') == obj['baseline_before'],
         'P03 live audit v1 state differs from signed baseline')
    need(proof.get('android_live_queried') is True and
         proof.get('android_api_36_emulator') is True and
         proof.get('physical_device_qualified') is False and
         proof.get('release_qualified') is False,
         'P03 runtime scope or Android provenance unqualified')
    print('OX_R02F_P03_OFFLINE_SOURCE_BOUND_LIVE_AUDIT_RECEIPT_VERIFIED_PASS',flush=True)
    return 0


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('command', choices=['run','audit','verify'])
    ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args()
    try:
        return run(a.out) if a.command=='run' else (audit(a.out) if a.command=='audit' else verify(a.out))
    except (OSError,ValueError,KeyError,TypeError,Refused,base.Refused,rt02c.Refused) as e:
        print('OX_R02F_P03_REFUSED: '+str(e),file=sys.stderr,flush=True)
        return 2

if __name__=='__main__': sys.exit(main())
