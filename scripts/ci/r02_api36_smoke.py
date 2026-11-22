#!/usr/bin/env python3
"""Hosted API36 *bootstrap* smoke, not split-install or device qualification.

Python-only standard-library harness. Confines ADB operations to an ephemeral
Android Emulator on a GitHub-hosted Linux runner. Emits allowlisted evidence.
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
import time

PACKAGE = 'dev.bikram.obtainx.debug'
COMPONENT = 'dev.bikram.obtainx.debug/dev.imranr.obtainium.MainActivity'
SERIAL = 'emulator-5554'
APK = Path('build/app/outputs/flutter-apk/app-normal-debug.apk')
OUT_NAME = 'receipt.json'
SHA_PATTERN = re.compile(r'^[0-9a-f]{64}$')

class Refused(RuntimeError):
    pass


def need(ok: bool, message: str) -> None:
    if not ok:
        raise Refused(message)


def call(*argv: str, timeout: int = 45, binary: bool = False):
    try:
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as ex:
        raise Refused(f'Command unavailable or timed out: {argv[0]}') from ex
    if result.returncode:
        # Always expose the actual failing operation, including stdout-only
        # Android errors. Never log an entire environment or any credentials.
        detail = (result.stderr.decode(errors='replace').strip()
                  or result.stdout.decode(errors='replace').strip()
                  or '<no command output>')[-700:]
        command = ' '.join(argv[:10])
        raise Refused(f'{command} returned {result.returncode}: {detail}')
    return result.stdout if binary else result.stdout.decode(errors='replace').strip()


def adb(*argv: str, binary: bool = False, timeout: int = 40):
    return call('adb', '-s', SERIAL, *argv, binary=binary, timeout=timeout)


def verify_fresh_package_absent() -> None:
    """Fail closed on an existing installation or an ambiguous package query.

    On API 36, `pm path <absent-package>` may return exit 1 and *no* output.
    That is not an ADB failure when a second, independent package-manager
    query succeeds and also shows that this exact package is absent.
    """
    argv = ('adb', '-s', SERIAL, 'shell', 'pm', 'path', PACKAGE)
    try:
        result = subprocess.run(argv, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=40,
                                check=False)
    except (OSError, subprocess.TimeoutExpired) as ex:
        raise Refused('Fresh-install package-path probe unavailable') from ex
    stdout = result.stdout.decode(errors='replace').strip()
    stderr = result.stderr.decode(errors='replace').strip()
    need(result.returncode in (0, 1) and not stdout and not stderr,
         f'Existing/ambiguous package-path probe: status={result.returncode}, '
         f'stdout={stdout[-180:]!r}, stderr={stderr[-180:]!r}')
    # A successful second command is mandatory. An empty inventory confirms
    # absence; any installed match, command failure, or unexpected output redacts
    # no error and refuses the run. Never interpret ADB/pm failures as absence.
    listing = adb('shell', 'cmd', 'package', 'list', 'packages', '--user', '0', PACKAGE)
    need(not listing.strip(), 'Package inventory is non-empty: emulator is not fresh')
    print('OX_R02_API36_FRESH_PACKAGE_ABSENT_PASS', flush=True)


def query_main_pid() -> str:
    """Allow a temporarily absent PID, never an ambiguous ADB failure."""
    argv = ('adb', '-s', SERIAL, 'shell', 'pidof', PACKAGE)
    try:
        result = subprocess.run(argv, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=40, check=False)
    except (OSError, subprocess.TimeoutExpired) as ex:
        raise Refused('Main-process PID query unavailable') from ex
    stdout = result.stdout.decode(errors='replace').strip()
    stderr = result.stderr.decode(errors='replace').strip()
    if result.returncode == 1 and not stdout and not stderr:
        return ''
    need(result.returncode == 0 and not stderr and
         bool(re.fullmatch(r'[0-9]+', stdout)),
         f'Ambiguous main-process PID query: rc={result.returncode}, '
         f'stdout={stdout[-120:]!r}, stderr={stderr[-120:]!r}')
    return stdout


def _mentions_exact_main_activity(line: str) -> bool:
    """No substring matching other packages or other activities."""
    options = (COMPONENT, PACKAGE + '/.MainActivity')
    return any(re.search(r'(?<![A-Za-z0-9_.])' + re.escape(value) +
                         r'(?=$|[\s}\],])', line) for value in options)


def main_activity_proof(activities: str, windows: str) -> str:
    """Require actual *resumed or focused* MainActivity, not a launch banner.

    Android's am start -W output differs by API and task-reuse state. A
    successful shell return alone is insufficient for a runtime pass.
    """
    resumed = re.compile(r'^\s*(?:topResumedActivity|mResumedActivity|ResumedActivity)\s*[:=]')
    focused = re.compile(r'^\s*(?:mCurrentFocus|mFocusedApp|mFocusedWindow)\s*[:=]')
    for line in activities.splitlines():
        if resumed.match(line) and _mentions_exact_main_activity(line):
            return 'resumed'
    for line in windows.splitlines():
        if focused.match(line) and _mentions_exact_main_activity(line):
            return 'focused'
    return ''


def observe_main_activity() -> str:
    activities = adb('shell', 'dumpsys', 'activity', 'activities', timeout=45)
    windows = adb('shell', 'dumpsys', 'window', 'windows', timeout=45)
    return main_activity_proof(activities, windows)


def launch_report(text: str) -> str:
    """Keep bounded, single-line diagnostic text, never silently accept errors."""
    return ' | '.join(line.strip() for line in text.splitlines() if line.strip())[-600:]


def stage(label: str) -> None:
    print('OX_R02_API36_STAGE='+label, flush=True)


def classify_main_window(activities: str, windows: str) -> str:
    """Return only an allowlisted category, never private window content."""
    if main_activity_proof(activities, windows):
        return 'obtainx_main'
    labels = '\n'.join(line for line in (activities + '\n' + windows).splitlines()
                       if re.search(r'\b(?:topResumedActivity|mResumedActivity|ResumedActivity|mCurrentFocus|mFocusedApp|mFocusedWindow)\s*[:=]', line))
    if re.search(r'com\.android\.permissioncontroller', labels):
        return 'permission_controller'
    if re.search(r'com\.android\.(?:launcher|quickstep)', labels):
        return 'launcher'
    if re.search(r'com\.android\.(?:systemui|settings)', labels):
        return 'android_system'
    if labels.strip():
        return 'unrelated_foreground'
    return 'no_foreground_record'


def last_foreground_category() -> str:
    activities = adb('shell', 'dumpsys', 'activity', 'activities', timeout=45)
    windows = adb('shell', 'dumpsys', 'window', 'windows', timeout=45)
    return classify_main_window(activities, windows)


def start_main_activity(*, recovery: bool = False) -> str:
    """Avoid am start -W's ten-second cold-start timeout on API 36.

    This is only a launch *request*. Never accept its return as boot proof.
    Cinderbox's hosted tests also depend on device-side execution evidence.
    """
    response = adb('shell', 'am', 'start', '-n', COMPONENT, timeout=45)
    detail = launch_report(response)
    label = 'OX_R02_API36_AM_REFOCUS_OUTPUT=' if recovery else 'OX_R02_API36_AM_START_OUTPUT='
    print(label + (detail or '<empty>'), flush=True)
    need(not re.search(r'(?im)^\s*(?:Error:|Exception|SecurityException|Failure \[)', response),
         'Android activity manager rejected launch: ' + detail)
    return detail


def wait_for_stable_main_activity(start_detail: str) -> tuple[str, str, bool]:
    """Require repeated real foreground observations with one bounded recovery.

    A first-run permission UI or splash transition may temporarily replace the
    activity as the system finishes launching Flutter. Never convert that
    transition, a process restart, or a perpetual system dialog into success.
    """
    stage('VERIFY_MAIN_ACTIVITY_RESUMED')
    pid = ''
    stable_observations = 0
    proof = ''
    refocus_attempted = False
    lost_after_proof = False
    seen_positive = False
    for index in range(24):
        current = query_main_pid()
        if current:
            if pid and pid != current:
                raise Refused('ObtainX process restarted during runtime qualification')
            pid = current
            state = observe_main_activity()
            if state in ('resumed', 'focused'):
                seen_positive = True
                if lost_after_proof:
                    # Starting a new continuous window after a UI transition.
                    lost_after_proof = False
                stable_observations += 1
                proof = state
                if stable_observations >= 4:
                    break
            else:
                if stable_observations:
                    lost_after_proof = True
                stable_observations = 0
                proof = ''
        else:
            if stable_observations:
                lost_after_proof = True
            stable_observations = 0
            proof = ''
        # Reassert focus just once, only when the verified original process is
        # still alive. A restart cannot be hidden by restarting the app.
        if index == 11 and pid and not refocus_attempted and stable_observations == 0:
            stage('REASSERT_MAIN_ACTIVITY_ONCE')
            need(query_main_pid() == pid, 'ObtainX process disappeared before re-focus')
            start_main_activity(recovery=True)
            refocus_attempted = True
        if index < 23:
            time.sleep(2)
    need(bool(re.fullmatch(r'[0-9]+', pid)),
         'ObtainX process never started; am start=' + start_detail)
    if not (stable_observations >= 4 and proof in ('resumed', 'focused')):
        raise Refused('MainActivity did not stabilize in foreground after bounded probes; '
                      'last_focus=' + last_foreground_category() +
                      '; seen_once=' + str(seen_positive))
    # This is the final device-state check. An unrelated window, died process,
    # or a screenshot of another app may never satisfy the bootstrap receipt.
    need(query_main_pid() == pid, 'ObtainX process exited or restarted before capture')
    if observe_main_activity() not in ('resumed', 'focused'):
        raise Refused('MainActivity lost foreground before capture; last_focus=' + last_foreground_category())
    return pid, proof, refocus_attempted


def write_failed_evidence(out: Path, reason: str) -> None:
    """Cinderbox-style fail-closed receipt: categorical, no raw device logs."""
    path = receipt_path(out)
    if not path.is_file():
        return
    try:
        receipt = json.loads(path.read_text())
        if receipt.get('status') != 'NOT_RUN':
            return
        # A failing run never emits a success screenshot or success receipt.
        (out / 'app_launch.png').unlink(missing_ok=True)
        permitted = ('MainActivity', 'process', 'ADB', 'Android', 'APK', 'launch',
                     'emulator', 'device', 'package', 'activity', 'permission')
        category = 'RUNTIME_REFUSED' if any(x.lower() in reason.lower() for x in permitted) else 'HOST_REFUSED'
        receipt.update(status='FAILED', failure_category=category,
                       hosted_emulator_only=True, physical_device_qualified=False,
                       split_install_e2e_qualified=False,
                       obtainx_installer_e2e_qualified=False,
                       release_qualified=False, publication_allowed=False)
        path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + '\n')
    except (OSError, ValueError):
        pass


def host_identity() -> tuple[str, str]:
    need(os.environ.get('GITHUB_ACTIONS') == 'true' and
         os.environ.get('RUNNER_OS') == 'Linux' and
         os.environ.get('RUNNER_ARCH') == 'X64', 'GH Linux x64 runner required')
    source = os.environ.get('GITHUB_SHA', '')
    run_id = os.environ.get('GITHUB_RUN_ID', '')
    need(bool(re.fullmatch('[0-9a-f]{40}', source)), 'missing source SHA')
    need(bool(re.fullmatch('[0-9]+', run_id)), 'missing run ID')
    need(call('git','rev-parse','HEAD') == source, 'checkout does not match workflow source')
    return source, run_id


def receipt_path(out: Path) -> Path:
    need(out.is_absolute(), 'output directory must be absolute')
    return out / OUT_NAME


def init(out: Path) -> None:
    source, run_id = host_identity()
    out.mkdir(parents=True, exist_ok=True)
    payload = {'schema': 1, 'status': 'NOT_RUN', 'source_sha': source,
               'run_id': run_id, 'hosted_emulator_only': True,
               'physical_device_qualified': False,
               'split_install_e2e_qualified': False,
               'obtainx_installer_e2e_qualified': False,
               'release_qualified': False, 'publication_allowed': False}
    receipt_path(out).write_text(json.dumps(payload, indent=2, sort_keys=True)+'\n')
    print('OX_R02_API36_EVIDENCE_INITIALIZED')


def run_emulator(out: Path) -> None:
    source, run_id = host_identity()
    prior = json.loads(receipt_path(out).read_text())
    need(prior.get('status') == 'NOT_RUN' and prior.get('source_sha') == source
         and prior.get('run_id') == run_id, 'failure receipt missing or stale')
    stage('VERIFY_EMULATOR_IDENTITY')
    need(adb('get-state') == 'device', 'ADB emulator not connected')
    need(adb('shell', 'getprop', 'ro.kernel.qemu') == '1', 'physical/unknown device refused')
    need(adb('shell', 'getprop', 'ro.build.version.sdk') == '36', 'Android API 36 required')
    need(APK.is_file() and APK.stat().st_size > 100000, 'debug APK absent or undersized')
    apk_bytes = APK.read_bytes()
    apk_sha = hashlib.sha256(apk_bytes).hexdigest()
    android_home = Path(os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT') or '')
    aapt = android_home / 'build-tools/35.0.0/aapt'
    apksigner = android_home / 'build-tools/35.0.0/apksigner'
    need(aapt.is_file() and apksigner.is_file(), 'Android SDK tools missing')
    stage('VERIFY_APK_METADATA_AND_SIGNATURE')
    badging = call(str(aapt), 'dump', 'badging', str(APK), timeout=45)
    need(f"package: name='{PACKAGE}'" in badging, 'APK package ID mismatch')
    certs = call(str(apksigner), 'verify', '--print-certs', str(APK), timeout=45)
    matches = re.findall(r'Signer #1 certificate SHA-256 digest:\s*([0-9a-fA-F]{64})', certs)
    need(len(matches) == 1, 'debug APK signature unverified')
    cert_sha = matches[0].lower()
    stage('VERIFY_FRESH_PACKAGE')
    verify_fresh_package_absent()
    stage('INSTALL_DEBUG_APK')
    adb('install', '-t', str(APK), timeout=180)
    stage('VERIFY_INSTALLED_APK_BYTES')
    package_paths = adb('shell', 'pm', 'path', PACKAGE).splitlines()
    need(len(package_paths) == 1 and package_paths[0].startswith('package:/data/app/')
         and package_paths[0].endswith('/base.apk'), 'installed package path unexpected')
    remote_path = package_paths[0].removeprefix('package:')
    need(bool(re.fullmatch(r'/data/app/[A-Za-z0-9_+./~=-]+/base\.apk', remote_path)),
         'installed package path contains unsafe characters')
    installed_sha_text = adb('shell', 'sha256sum', remote_path).split()
    need(len(installed_sha_text) == 2 and installed_sha_text[0] == apk_sha,
         'on-emulator installed bytes do not match CI-built artifact')
    stage('START_OBTAINX_MAIN_ACTIVITY')
    start_detail = start_main_activity()
    pid, activity_proof, refocus_attempted = wait_for_stable_main_activity(start_detail)
    print('OX_R02_API36_MAIN_ACTIVITY_DEVICE_PROOF=' + activity_proof, flush=True)
    stage('CAPTURE_EMULATOR_SCREENSHOT')
    image_bytes = adb('exec-out', 'screencap', '-p', binary=True, timeout=40)
    need(image_bytes.startswith(b'\x89PNG\r\n\x1a\n') and len(image_bytes) > 2000,
         'emulator screenshot invalid')
    # Cinderbox's evidence pattern: the captured image must be bound to the
    # same verified, living foreground task, not a subsequent system overlay.
    need(query_main_pid() == pid, 'ObtainX process disappeared after screenshot')
    need(observe_main_activity() in ('resumed', 'focused'),
         'ObtainX lost foreground after screenshot')
    image_path = out / 'app_launch.png'
    image_path.write_bytes(image_bytes)
    receipt = {**prior, 'status':'PASS', 'api_level':36, 'emulator_abi':'x86_64',
               'emulator_serial':SERIAL, 'package':PACKAGE, 'activity':COMPONENT,
               'activity_proof':activity_proof, 'foreground_activity_verified':True,
               'stable_foreground_observations':4, 'refocus_attempted':refocus_attempted,
               'app_apk_sha256':apk_sha, 'installed_apk_sha256':installed_sha_text[0],
               'debug_certificate_sha256':cert_sha,
               'app_launch_png_sha256':hashlib.sha256(image_bytes).hexdigest(),
               'app_launch_png_bytes':len(image_bytes),
               'source_sha':source, 'run_id':run_id}
    receipt_path(out).write_text(json.dumps(receipt, sort_keys=True, indent=2)+'\n')
    print('OX_R02_API36_BOOTSTRAP_PASS: installed debug bytes and MainActivity process verified')
    print('OX_R02_API36_SPLIT_RUNTIME_PENDING: no ObtainX-driven split install proven')


def verify(out: Path) -> None:
    source, run_id = host_identity()
    data = json.loads(receipt_path(out).read_text())
    for key, expected in {
        'schema': 1, 'status': 'PASS', 'source_sha': source,
        'run_id': run_id, 'hosted_emulator_only': True,
        'physical_device_qualified': False,
        'split_install_e2e_qualified': False,
        'obtainx_installer_e2e_qualified': False,
        'release_qualified': False, 'publication_allowed': False,
        'api_level': 36, 'emulator_abi': 'x86_64', 'emulator_serial': SERIAL,
        'package': PACKAGE, 'activity': COMPONENT,
        'foreground_activity_verified': True,
        'stable_foreground_observations': 4,
    }.items():
        need(data.get(key) == expected, f'receipt field invalid: {key}')
    need(type(data.get('refocus_attempted')) is bool,
         'invalid foreground recovery evidence')
    need(data.get('activity_proof') in ('resumed', 'focused'),
         'missing device-state MainActivity foreground proof')
    for key in ('app_apk_sha256', 'installed_apk_sha256',
                'debug_certificate_sha256', 'app_launch_png_sha256'):
        need(bool(SHA_PATTERN.fullmatch(data.get(key, ''))), f'invalid digest: {key}')
    need(data['app_apk_sha256'] == data['installed_apk_sha256'],
         'source-bound installed bytes mismatch')
    image_path = out / 'app_launch.png'
    need(image_path.is_file() and image_path.stat().st_size >= 2000,
         'verified screenshot missing')
    need(hashlib.sha256(image_path.read_bytes()).hexdigest() == data['app_launch_png_sha256'],
         'screenshot digest mismatch')
    need(data.get('app_launch_png_bytes') == image_path.stat().st_size,
         'screenshot size mismatch')
    print('OX_R02_API36_VERIFIED: emulator-only app boot, source sha and evidence hashes')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['init', 'run', 'verify'])
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    try:
        {'init':init,'run':run_emulator,'verify':verify}[args.command](args.out)
        return 0
    except (Refused, OSError, ValueError, json.JSONDecodeError) as exc:
        if args.command == 'run':
            write_failed_evidence(args.out, str(exc))
        print('OX_R02_API36_REFUSED: '+str(exc), file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
