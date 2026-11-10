#!/usr/bin/env python3
"""Build disposable same-signature standalone + configuration-split Android fixtures.

No private/release material: test signing key lives only in the hosted runner's
RUNNER_TEMP, and never enters an artifact, a repository or a receipt.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

PKG = 'dev.bikram.obtainx.rt02.fixture'
NAMES = ('base_v1.apk', 'base_v2.apk', 'config.x86_64.apk')


def need(value: bool, detail: str) -> None:
    if not value:
        raise RuntimeError(detail)


def command(*args: str) -> str:
    p = subprocess.run(args, capture_output=True, text=True, timeout=120, check=False)
    if p.returncode:
        raise RuntimeError(f'fixture tool failed: {Path(args[0]).name} rc={p.returncode}: '
                           + (p.stderr or p.stdout)[-500:])
    return p.stdout


def signed_fixture(out: Path) -> dict:
    need(out.is_absolute() and out.exists() and out.is_dir(), 'fixture output path must exist and be absolute')
    need(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('RUNNER_OS') == 'Linux',
         'fixture signing allowed only on GitHub Linux runner')
    sdk = Path(os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT') or '')
    tools = sdk / 'build-tools' / '35.0.0'
    platform = sdk / 'platforms' / 'android-36' / 'android.jar'
    aapt2 = tools/'aapt2'; zipalign = tools/'zipalign'; signer = tools/'apksigner'
    for item in (aapt2, zipalign, signer, platform):
        need(item.is_file(), 'Android build tool or API36 platform missing: '+str(item))
    key = out/'fixture-only.jks'
    need(not key.exists(), 'fixture key already exists: fresh runner required')
    # Key password is a temporary random value, never persisted in receipts.
    import secrets
    password = secrets.token_hex(18)
    command('keytool', '-genkeypair', '-noprompt', '-alias', 'fixture',
            '-dname', 'CN=ObtainX CI Fixture', '-keyalg', 'RSA', '-keysize', '2048',
            '-validity', '2', '-keystore', str(key), '-storepass', password,
            '-keypass', password)
    artifacts = {}
    try:
        for version, split, name in ((1,False,'base_v1.apk'), (2,False,'base_v2.apk'),
                                     (2,True,'config.x86_64.apk')):
            manifest = out/(name+'.xml')
            attributes = (f'package="{PKG}" android:versionCode="{version}" '
                          + ('split="config.x86_64" android:configForSplit="base" ' if split else ''))
            manifest.write_text('<?xml version="1.0" encoding="utf-8"?>\n'
                '<manifest xmlns:android="http://schemas.android.com/apk/res/android" '
                + attributes + '>\n'
                '<uses-sdk android:minSdkVersion="26" android:targetSdkVersion="35"/>\n'
                '<application android:hasCode="false" android:label="ObtainX RT02 Fixture"/>\n'
                '</manifest>\n', encoding='utf-8')
            unsigned = out/(name+'.unsigned.apk')
            aligned = out/(name+'.aligned.apk')
            dest = out/name
            command(str(aapt2), 'link', '-o', str(unsigned), '-I', str(platform),
                    '--manifest', str(manifest), '--min-sdk-version', '26',
                    '--target-sdk-version', '35')
            command(str(zipalign), '-f', '4', str(unsigned), str(aligned))
            command(str(signer), 'sign', '--ks', str(key), '--ks-key-alias', 'fixture',
                    '--ks-pass', 'pass:'+password, '--key-pass', 'pass:'+password,
                    '--out', str(dest), str(aligned))
            command(str(signer), 'verify', '--print-certs', str(dest))
            command(str(tools/'aapt'), 'dump', 'badging', str(dest))
            artifacts[name] = {'sha256': hashlib.sha256(dest.read_bytes()).hexdigest(),
                               'size': dest.stat().st_size, 'version_code': version,
                               'split': split}
            need(artifacts[name]['size'] > 250, 'fixture APK unexpectedly small')
        inventory = {'schema':1, 'fixture_package':PKG, 'signed_with_ephemeral_ci_key':True,
                     'source_sha':os.environ.get('GITHUB_SHA', ''), 'files':artifacts,
                     'never_released':True}
        need(bool(re.fullmatch('[0-9a-f]{40}', inventory['source_sha'])), 'source SHA missing')
        (out/'fixture_inventory.json').write_text(json.dumps(inventory, indent=2, sort_keys=True)+'\n')
        return inventory
    finally:
        # Preserve no private key or signing password after signed fixtures exist.
        key.unlink(missing_ok=True)
        for file in out.glob('*.unsigned.apk'): file.unlink()
        for file in out.glob('*.aligned.apk'): file.unlink()
        for file in out.glob('*.xml'): file.unlink()


def main() -> int:
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    try:
        inventory=signed_fixture(args.out)
        print('OX_R02_RT02_FIXTURES_SIGNED: '+','.join(inventory['files']),flush=True)
        return 0
    except (OSError,RuntimeError,ValueError,subprocess.TimeoutExpired) as ex:
        print('OX_R02_RT02_FIXTURE_REFUSED: '+str(ex),file=sys.stderr)
        return 1

if __name__=='__main__':raise SystemExit(main())
