#!/usr/bin/env python3
"""R02G P01: sign one disposable Android-37-min APK on an ephemeral API36 CI runner.

This fixture does NOT become a release, cannot be used on a personal device,
and leaves no private key, unsigned APK, manifest or signing password behind.
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

PACKAGE = 'dev.bikram.obtainx.rt02g.future_sdk'
NAME = 'rt02g-min37.apk'
INVENTORY = 'rt02g_inventory.json'
MIN_SDK = 37

class Refused(RuntimeError): pass

def need(value: bool, why: str) -> None:
    if not value:
        raise Refused(why)

def manifest() -> str:
    return ( '<?xml version="1.0" encoding="utf-8"?>\n'
             '<manifest xmlns:android="http://schemas.android.com/apk/res/android" '
             'package="'+PACKAGE+'" android:versionCode="1">\n'
             '<uses-sdk android:minSdkVersion="37" android:targetSdkVersion="35"/>\n'
             '<application android:hasCode="false" android:label="ObtainX R02G Incompatible Fixture"/>\n'
             '</manifest>\n')

def tool(*args: str, timeout:int=100)->str:
    try:
        p=subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, check=False,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise Refused('disposable fixture tool unavailable or timed out') from exc
    # No secrets, command arguments, stdout or stderr are emitted into CI logs.
    need(p.returncode==0,'disposable fixture tool refused: '+Path(args[0]).name+
         ' rc='+str(p.returncode))
    return p.stdout.decode('utf8','replace')

def build(out: Path)->dict:
    need(out.is_absolute() and out.is_dir() and not out.is_symlink(),
         'absolute existing fixture directory required')
    need(os.environ.get('GITHUB_ACTIONS')=='true' and
         os.environ.get('RUNNER_OS')=='Linux' and
         os.environ.get('RUNNER_ARCH')=='X64',
         'only an authenticated GitHub Linux x64 runner can sign the fixture')
    head=os.environ.get('GITHUB_SHA','')
    need(bool(re.fullmatch(r'[0-9a-f]{40}',head)),'source commit absent')
    base=out/'fixture_inventory.json'
    need(base.is_file() and not base.is_symlink(),'R02 base signed fixtures must exist first')
    baseline=json.loads(base.read_text('utf8'))
    need(baseline.get('source_sha')==head and
         baseline.get('signed_with_ephemeral_ci_key') is True and
         baseline.get('never_released') is True,
         'source-bound R02 baseline signed fixture absent')
    sdk=Path(os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT') or '')
    tools=sdk/'build-tools'/'35.0.0'
    platform=sdk/'platforms'/'android-36'/'android.jar'
    for path in (tools/'aapt2',tools/'zipalign',tools/'apksigner',tools/'aapt',platform):
        need(path.is_file() and not path.is_symlink(),'pinned Android SDK build tool absent')
    key=out/'.rt02g-disposable.jks'
    xml=out/'.rt02g-manifest.xml'
    unsigned=out/'.rt02g-unsigned.apk'
    aligned=out/'.rt02g-aligned.apk'
    artifact=out/NAME
    inv=out/INVENTORY
    for f in (key,xml,unsigned,aligned,artifact,inv):
        need(not f.exists() and not f.is_symlink(), 'R02G fixture path already exists')
    password=secrets.token_hex(24)
    try:
        xml.write_text(manifest(),encoding='utf8')
        tool('keytool','-genkeypair','-noprompt','-alias','rt02g-fixture',
             '-dname','CN=ObtainX disposable R02G fixture', '-keyalg','RSA',
             '-keysize','2048','-validity','2','-keystore',str(key),
             '-storepass',password,'-keypass',password)
        # Android 36 compiler produces a test-only signed APK that declares
        # minSdkVersion=37. No application code and no runtime permissions.
        tool(str(tools/'aapt2'),'link','-o',str(unsigned),'-I',str(platform),
             '--manifest',str(xml),'--min-sdk-version','37','--target-sdk-version','35')
        tool(str(tools/'zipalign'),'-f','4',str(unsigned),str(aligned))
        tool(str(tools/'apksigner'),'sign','--ks',str(key),
             '--ks-key-alias','rt02g-fixture','--ks-pass','pass:'+password,
             '--key-pass','pass:'+password,'--out',str(artifact),str(aligned))
        tool(str(tools/'apksigner'),'verify',str(artifact))
        badging=tool(str(tools/'aapt'),'dump','badging',str(artifact))
        need("package: name='"+PACKAGE+"'" in badging and
             "sdkVersion:'37'" in badging and
             "targetSdkVersion:'35'" in badging,
             'signed APK package/minSdk/targetSdk verification refused')
        size=artifact.stat().st_size
        need(250<size<8*1024*1024 and not artifact.is_symlink(),
             'invalid disposable signed APK size or file type')
        doc={'schema':1,'source_sha':head,'fixture_package':PACKAGE,
             'file':NAME,'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest(),
             'size':size,'min_sdk_version':MIN_SDK,'device_sdk_expected':36,
             'ephemeral_ci_signing':True,'never_released':True}
        inv.write_text(json.dumps(doc,sort_keys=True,indent=2)+'\n',encoding='utf8')
        print('OX_R02G_SIGNED_MIN37_FIXTURE_VERIFIED',flush=True)
        return doc
    except BaseException:
        artifact.unlink(missing_ok=True)
        inv.unlink(missing_ok=True)
        raise
    finally:
        for f in (key,xml,unsigned,aligned):f.unlink(missing_ok=True)

def main()->int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',required=True,type=Path)
    args=ap.parse_args()
    try:
        build(args.out)
        return 0
    except (OSError,ValueError,TypeError,Refused) as exc:
        print('OX_R02G_FIXTURE_REFUSED '+type(exc).__name__,file=sys.stderr,flush=True)
        return 1

if __name__=='__main__':raise SystemExit(main())
