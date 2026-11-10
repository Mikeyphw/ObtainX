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
        detail = result.stderr.decode(errors='replace')[-700:]
        raise Refused(f'{argv[0]} returned {result.returncode}: {detail}')
    return result.stdout if binary else result.stdout.decode(errors='replace').strip()


def adb(*argv: str, binary: bool = False, timeout: int = 40):
    return call('adb', '-s', SERIAL, *argv, binary=binary, timeout=timeout)


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
    badging = call(str(aapt), 'dump', 'badging', str(APK), timeout=45)
    need(f"package: name='{PACKAGE}'" in badging, 'APK package ID mismatch')
    certs = call(str(apksigner), 'verify', '--print-certs', str(APK), timeout=45)
    matches = re.findall(r'Signer #1 certificate SHA-256 digest:\s*([0-9a-fA-F]{64})', certs)
    need(len(matches) == 1, 'debug APK signature unverified')
    cert_sha = matches[0].lower()
    need(not adb('shell', 'pm', 'path', PACKAGE), 'non-fresh emulator app state')
    adb('install', '-t', str(APK), timeout=180)
    package_paths = adb('shell', 'pm', 'path', PACKAGE).splitlines()
    need(len(package_paths) == 1 and package_paths[0].startswith('package:/data/app/')
         and package_paths[0].endswith('/base.apk'), 'installed package path unexpected')
    remote_path = package_paths[0].removeprefix('package:')
    need(bool(re.fullmatch(r'/data/app/[A-Za-z0-9_+./~=-]+/base\.apk', remote_path)),
         'installed package path contains unsafe characters')
    installed_sha_text = adb('shell', 'sha256sum', remote_path).split()
    need(len(installed_sha_text) == 2 and installed_sha_text[0] == apk_sha,
         'on-emulator installed bytes do not match CI-built artifact')
    start = adb('shell', 'am', 'start', '-W', '-n', COMPONENT, timeout=90)
    need('Status: ok' in start or 'Status: timeout' not in start and 'Complete' in start,
         'MainActivity did not launch')
    # Flutter's first startup can take longer than the Android am start return.
    pid = ''
    for _ in range(15):
        pid = adb('shell', 'pidof', PACKAGE)
        if bool(re.fullmatch(r'[0-9]+', pid)):
            break
        time.sleep(2)
    need(bool(re.fullmatch(r'[0-9]+', pid)), 'ObtainX process never started')
    time.sleep(5)
    need(adb('shell', 'pidof', PACKAGE) == pid, 'ObtainX process exited or restarted unexpectedly')
    image_bytes = adb('exec-out', 'screencap', '-p', binary=True, timeout=40)
    need(image_bytes.startswith(b'\x89PNG\r\n\x1a\n') and len(image_bytes) > 2000,
         'emulator screenshot invalid')
    image_path = out / 'app_launch.png'
    image_path.write_bytes(image_bytes)
    receipt = {**prior, 'status':'PASS', 'api_level':36, 'emulator_abi':'x86_64',
               'emulator_serial':SERIAL, 'package':PACKAGE, 'activity':COMPONENT,
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
    }.items():
        need(data.get(key) == expected, f'receipt field invalid: {key}')
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
        print('OX_R02_API36_REFUSED: '+str(exc), file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
