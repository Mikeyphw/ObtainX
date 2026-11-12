#!/usr/bin/env python3
"""RT02C HF01: one Flutter test process, seven host-verified Android boundaries.

Private, ephemeral authenticated loopback protocol; no evidence released except
allowlisted receipts. Android package installation is never simulated.
"""
from __future__ import annotations
import hashlib
from http import HTTPStatus
import json
import secrets
import subprocess
import threading
import time
from pathlib import Path
from r02_rt02_hosted import FixtureServer
from obtainx_ci_optimization_opt06_rt02c_polling import should_probe_runner

CASES = ('apks', 'apkm', 'xapk', 'zip', 'tar.gz', 'traversal', 'ambiguous')
POSITIVE = CASES[:5]
NEGATIVE = CASES[5:]


class ControlHandler(FixtureServer):
    controller = None

    def do_POST(self):
        control = type(self).controller
        if control is None:
            self.send_error(503)
            return
        if self.headers.get('X-RT02C-Token') != control.token:
            self.send_error(403)
            return
        try:
            length = int(self.headers.get('Content-Length', '-1'))
            if length <= 0 or length > 1024:
                raise ValueError('bounded control body required')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('control body must be object')
            result = control.transition(self.path, data)
            payload = (json.dumps(result, sort_keys=True) + '\n').encode()
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (RuntimeError, ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired) as exc:
            # Never leak ADB output, filesystem paths or tokens to the device.
            control.fail(type(exc).__name__)
            self.send_error(409, 'RT02C controlled boundary refused')


class SingleSession:
    def __init__(self, out: Path, fixtures: Path, inventory: dict,
                 receipt: dict, receipt_path: Path, host, base):
        self.out = out
        self.fixtures = fixtures
        self.inv = inventory
        self.receipt = receipt
        self.rp = receipt_path
        self.H = host
        self.base = base
        self.token = secrets.token_hex(24)
        self.lock = threading.RLock()
        self.next_index = 0
        self.active = None
        self.called = False
        self.taps = 0
        self.phase = 'FLUTTER_STARTING'
        self.started_at = time.monotonic()
        self.case_started_at = self.started_at
        self.call_at = None
        self.failure = None
        self.flutter_log = out / 'rt02c-single-session.private.log'
        self.app_installed = False
        self.runner_probe_last = None
        self.runner_probe_count = 0
        self.runner_probe_skipped = 0
        self.launches = 0
        self.last_progress = 0.0

    def need(self, condition, why):
        self.H.need(condition, why)

    def fail(self, category: str):
        with self.lock:
            if self.failure is None:
                self.failure = category

    def snapshot(self):
        with self.lock:
            return (self.active, self.phase, self.called, self.taps,
                    self.call_at, self.next_index, self.failure)

    def transition(self, route: str, data: dict):
        with self.lock:
            self.need(self.failure is None, 'previous control failure')
            self.need(route in ('/rt02c/prepare', '/rt02c/call', '/rt02c/finish'),
                      'unapproved protocol operation')
            self.need(set(data).issubset({'case', 'result'}) and
                      isinstance(data.get('case'), str), 'invalid scenario request')
            case = data['case']
            self.need(self.next_index < len(CASES) and
                      case == CASES[self.next_index], 'out-of-order scenario request')
            if route == '/rt02c/prepare':
                self.need(self.active is None and set(data) == {'case'},
                          'duplicate or overlapping scenario preparation')
                # Complete physical reset and exact-byte attestation before Dart
                # may access this case's signed archive.
                self.base.adb('shell', 'pm', 'uninstall', self.base.FIXTURE,
                              allow_failure=True)
                self.base.empty_or_expected_package()
                self.base.adb('install', '-t', str(self.fixtures / 'base_v1.apk'),
                              timeout=180)
                self.H.baseline_v1(self.fixtures)
                runner = self.base.command(['adb', '-s', self.base.SERIAL,
                                            'shell', 'pm', 'path', self.base.APP],
                                           allow_failure=True)
                self.need(runner.returncode == 0 and
                          runner.stdout.strip().startswith(b'package:'),
                          'Flutter runner APK not installed at start boundary')
                if not self.app_installed:
                    self.base.adb('shell', 'appops', 'set', self.base.APP,
                                  'REQUEST_INSTALL_PACKAGES', 'allow')
                    self.app_installed = True
                self.active = case
                self.called = False
                self.taps = 0
                self.call_at = None
                self.case_started_at = time.monotonic()
                self.phase = 'DART_TEST_STARTED'
                self.H.progress(self.out, case, self.phase, 0, 0)
                name = self.H.filename(case)
                digest = self.inv['files'][name]['sha256']
                self.need(digest == self.H.sha(self.fixtures / name),
                          'archive bytes changed after staging')
                return {'case': case, 'archive_sha256': digest}
            self.need(self.active == case, 'scenario not prepared')
            if route == '/rt02c/call':
                self.need(case in POSITIVE and not self.called and
                          set(data) == {'case'}, 'unapproved or repeated installer call')
                self.called = True
                self.call_at = time.monotonic()
                self.phase = 'STOCK_INSTALLER_CALL'
                return {'authorized': True}
            self.need(route == '/rt02c/finish' and set(data) == {'case', 'result'},
                      'invalid scenario completion request')
            expected = 'installed' if case in POSITIVE else 'refused'
            self.need(data['result'] == expected, 'unexpected scenario disposition')
            if case in POSITIVE:
                self.need(self.called, 'positive scenario never called stock installer')
                proof = self.base.installed_state(2, True, self.fixtures)
                proof.update(installed_signed_members_verified=True)
                self.phase = 'ANDROID_V2_SPLIT_VERIFIED'
            else:
                self.need(not self.called and self.taps == 0,
                          'negative scenario reached installer or Android approval')
                proof = self.H.baseline_v1(self.fixtures)
                proof.update(preinstall_refused=True)
                self.phase = 'ANDROID_V1_BASELINE_VERIFIED'
            # The session log is private; only its bounded SHA is retained.
            self.need(self.flutter_log.is_file(), 'missing private Flutter evidence')
            log_hash = self.H.sha(self.flutter_log)
            name = self.H.filename(case)
            proof.update(case=case,
                         archive_sha256=self.inv['files'][name]['sha256'],
                         android_confirmations=self.taps,
                         flutter_log_sha256=log_hash,
                         process_launch=1,
                         boundary_index=self.next_index)
            self.H.progress(self.out, case, self.phase,
                            int(time.monotonic() - self.case_started_at), self.taps)
            self.receipt['cases'].append(proof)
            self.rp.write_text(json.dumps(self.receipt, sort_keys=True, indent=2) + '\n')
            print('OX_R02_RT02C_HF01_CASE_PASS case=' + case +
                  ' boundary=' + str(self.next_index + 1) + '/7', flush=True)
            self.next_index += 1
            self.active = None
            self.called = False
            self.call_at = None
            return {'verified': True, 'next_index': self.next_index}

    def run(self):
        self.need(self.launches == 0, 'single Flutter launch enforced')
        self.launches = 1
        args = ['flutter', 'test', 'integration_test/r02c_archive_install_test.dart',
                '-d', self.base.SERIAL, '--flavor', 'normal', '--no-pub',
                '--reporter', 'expanded',
                '--dart-define=OX_R02C_CONTROL_TOKEN=' + self.token,
                '--dart-define=OX_R02C_BASE_SHA=' + self.inv['signed_base_sha256'],
                '--dart-define=OX_R02C_SPLIT_SHA=' + self.inv['signed_split_sha256']]
        started = time.monotonic()
        timeout_at = started + 6000  # One bounded runtime for all seven cases.
        with self.flutter_log.open('wb') as target:
            p = subprocess.Popen(args, stdin=subprocess.DEVNULL,
                                 stdout=target, stderr=subprocess.STDOUT)
            try:
                while p.poll() is None:
                    now = time.monotonic()
                    active, phase, called, taps, call_at, idx, failure = self.snapshot()
                    if failure:
                        raise self.H.Refused('single-session boundary refused: ' + failure)
                    self.need(now < timeout_at, 'bounded single-session Flutter timeout')
                    self.need(call_at is None or now - call_at < 240,
                              'bounded real installer request timeout')
                    if not self.app_installed:
                        # No need to poll Android every second while Gradle
                        # is compiling the Flutter runner. Outside that
                        # phase, eligibility polling remains immediate.
                        runner_stage = self.H.stage(self.flutter_log)
                        if should_probe_runner(now, self.runner_probe_last, runner_stage):
                            self.runner_probe_last = now
                            self.runner_probe_count += 1
                            probe = self.base.command(['adb', '-s', self.base.SERIAL,
                                                       'shell', 'pm', 'path', self.base.APP],
                                                      allow_failure=True)
                            if (probe.returncode == 0 and
                                    probe.stdout.strip().startswith(b'package:')):
                                self.base.adb('shell', 'appops', 'set', self.base.APP,
                                              'REQUEST_INSTALL_PACKAGES', 'allow')
                                self.app_installed = True
                        else:
                            self.runner_probe_skipped += 1
                    # Never interfere with startup/Gradle. Never tap unless Dart
                    # explicitly reached StockInstaller for the current case.
                    if self.app_installed and active and called and taps == 0:
                        with self.lock:
                            if self.active == active and self.called and self.taps == 0:
                                if self.base._tap_confirmed_install_dialog():
                                    self.taps = 1
                    if now - self.last_progress >= 25:
                        current = active or (CASES[idx] if idx < len(CASES) else CASES[-1])
                        current_phase = phase if active else self.H.stage(self.flutter_log)
                        # Legacy stage parser is only for non-active bootstrap,
                        # never the authority for a later per-case installer call.
                        if current_phase not in self.H.PHASES:
                            current_phase = 'FLUTTER_STARTING'
                        self.H.progress(self.out, current, current_phase,
                                        int(now - started), taps if active else 0)
                        self.last_progress = now
                    time.sleep(1)
                self.need(p.returncode == 0 and
                          'All tests passed!' in self.flutter_log.read_text('utf8', 'replace'),
                          'one-session Flutter test failed: ' +
                          self.H.flutter_failure(self.flutter_log.read_text('utf8', 'replace')))
                self.need(self.app_installed, 'Flutter runner APK not proven installed')
                self.need(self.next_index == len(CASES) and self.active is None,
                          'missing completed, independently verified scenario')
                self.need(self.failure is None, 'boundary failure after Flutter exit')
                self.receipt['flutter_launches'] = self.launches
                self.receipt['session_log_sha256'] = self.H.sha(self.flutter_log)
                self.receipt['runner_probe_count'] = self.runner_probe_count
                self.receipt['runner_probe_skipped'] = self.runner_probe_skipped
                print('OX_OPT06_RT02C_RUNNER_PROBES_COUNT=' + str(self.runner_probe_count) +
                      ' SKIPPED=' + str(self.runner_probe_skipped), flush=True)
            finally:
                if p.poll() is None:
                    p.terminate()
                    try:
                        p.wait(timeout=6)
                    except subprocess.TimeoutExpired:
                        p.kill()
                        p.wait(timeout=6)
