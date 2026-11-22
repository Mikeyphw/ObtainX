#!/usr/bin/env python3
"""Build one differently signed v3 fixture; never export ephemeral key material.

Must run after RT02A's fresh test fixture generator on GitHub Actions Linux.
The base-v2 APK supplies the installed prior version, not a claim of an
ObtainX-driven installation. Only RT02B's negative attempts use StockInstaller.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys

from r02_rt02_fixture import PKG

WRONG = 'wrong_signer_v3.apk'
BASE = 'base_v2.apk'


def need(value: bool, reason: str) -> None:
    if not value:
        raise ValueError(reason)


def run(*args: str) -> str:
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ValueError('RT02B build tool unavailable: '+Path(args[0]).name) from e
    if p.returncode:
        # Bounded diagnostic; do not include any command arguments (key password).
        raise ValueError('RT02B tool failed: '+Path(args[0]).name+' rc='+str(p.returncode)
                         +' (diagnostics redacted: no signing secrets in logs)')
    return p.stdout


def signer_sha(signer: Path, apk: Path) -> str:
    t=run(str(signer), 'verify', '--print-certs', str(apk))
    m=re.findall(r'Signer #1 certificate SHA-256 digest:\s*([0-9a-fA-F]{64})',t)
    need(len(m)==1, 'APK certificate digest not unambiguous')
    return m[0].lower()


def wrong_signed_fixture(out: Path) -> dict:
    need(out.is_absolute() and out.is_dir(), 'absolute existing fixture folder required')
    need(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_OS')=='Linux'
         and os.environ.get('RUNNER_ARCH')=='X64', 'CI Linux x64 only')
    sha=os.environ.get('GITHUB_SHA','')
    need(bool(re.fullmatch('[0-9a-f]{40}',sha)), 'exact source SHA required')
    previous=json.loads((out/'fixture_inventory.json').read_text())
    need(previous.get('source_sha')==sha and previous.get('fixture_package')==PKG,
         'stale fixture inventory')
    need(set(previous.get('files',{}))=={'base_v1.apk','base_v2.apk','config.x86_64.apk'},
         'unexpected RT02A fixture inventory')
    for name,meta in previous['files'].items():
        need(hashlib.sha256((out/name).read_bytes()).hexdigest()==meta['sha256'],
             'fixture digest mismatch: '+name)
    sdk=Path(os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT') or '')
    tools=sdk/'build-tools'/'35.0.0'
    aapt2=tools/'aapt2'; zipalign=tools/'zipalign'; signer=tools/'apksigner'
    platform=sdk/'platforms'/'android-36'/'android.jar'
    for item in (aapt2,zipalign,signer,platform):need(item.is_file(),'Android build tool missing')
    key=out/'rt02b-wrong-identity.jks'
    manifest=out/'rt02b-wrong.xml'
    unsigned=out/'rt02b-wrong.unsigned.apk'
    aligned=out/'rt02b-wrong.aligned.apk'
    target=out/WRONG
    for p in (key,manifest,unsigned,aligned,target):need(not p.exists(),'stale RT02B artifact')
    passwd=secrets.token_hex(20)
    orig_cert=signer_sha(signer,out/BASE)
    try:
        run('keytool','-genkeypair','-noprompt','-alias','rt02b-wrong',
            '-dname','CN=ObtainX RT02B Disposable Wrong Key',
            '-keyalg','RSA','-keysize','2048','-validity','2',
            '-keystore',str(key),'-storepass',passwd,'-keypass',passwd)
        manifest.write_text('<?xml version="1.0" encoding="utf-8"?>\n'
            '<manifest xmlns:android="http://schemas.android.com/apk/res/android" '
            f'package="{PKG}" android:versionCode="3">\n'
            '<uses-sdk android:minSdkVersion="26" android:targetSdkVersion="35"/>\n'
            '<application android:hasCode="false" android:label="ObtainX RT02 Fixture"/>\n'
            '</manifest>\n',encoding='utf-8')
        run(str(aapt2),'link','-o',str(unsigned),'-I',str(platform),
            '--manifest',str(manifest),'--min-sdk-version','26','--target-sdk-version','35')
        run(str(zipalign),'-f','4',str(unsigned),str(aligned))
        run(str(signer),'sign','--ks',str(key),'--ks-key-alias','rt02b-wrong',
            '--ks-pass','pass:'+passwd,'--key-pass','pass:'+passwd,
            '--out',str(target),str(aligned))
        wrong_cert=signer_sha(signer,target)
        need(orig_cert!=wrong_cert, 'fixture certificate identity accidentally matches')
        need(target.stat().st_size>250,'signed negative APK unexpectedly small')
        digest=hashlib.sha256(target.read_bytes()).hexdigest()
        data={'schema':1,'source_sha':sha,'fixture_package':PKG,
              'original_version_code':2,'wrong_version_code':3,
              'original_sha256':previous['files'][BASE]['sha256'],
              'original_cert_sha256':orig_cert,'wrong_cert_sha256':wrong_cert,
              'wrong_sha256':digest,'wrong_size':target.stat().st_size,
              'ephemeral_keys_deleted':True,'physical_device_qualified':False,
              'release_qualified':False,'never_released':True}
        (out/'rt02b_inventory.json').write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')
        return data
    finally:
        key.unlink(missing_ok=True)
        for p in (manifest,unsigned,aligned):p.unlink(missing_ok=True)
        # The signed wrong APK stays only in RUNNER_TEMP, never upload.


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    a=parser.parse_args()
    try:
        data=wrong_signed_fixture(a.out)
        print('OX_R02_RT02B_WRONG_IDENTITY_FIXTURE_PASS: original_cert!=wrong_cert '
              'source_sha='+data['source_sha'],flush=True)
        return 0
    except (OSError,ValueError,KeyError,TypeError,RuntimeError) as e:
        print('OX_R02_RT02B_FIXTURE_REFUSED: '+str(e),file=sys.stderr,flush=True)
        return 1

if __name__=='__main__':raise SystemExit(main())
