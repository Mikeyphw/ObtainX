#!/usr/bin/env python3
"""OPT03: source-bound, verifiable *optional* GitHub Actions debug APK cache.

Cache data is never qualification evidence. Android installation, installed APK
SHA256, activity and independent receipt verification still run on every job.
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
import zipfile

PROFILE = 'ubuntu24-x64-flutter3.47.6-jdk21-normal-debug-v1'
PACKAGE = 'dev.bikram.obtainx.debug'
APK_NAME = 'app-normal-debug.apk'
RECEIPT_NAME = 'obtainx-opt03-debug-apk.json'
MIN_BYTES = 1024 * 1024
MAX_BYTES = 150 * 1024 * 1024
FIELDS = {'schema','source_sha','profile','package_name','apk_name','sha256','size_bytes'}

class Refused(RuntimeError):
    pass

def need(condition: bool, message: str) -> None:
    if not condition:
        raise Refused('OX_OPT03_REFUSED: '+message)

def source_identity() -> str:
    source = os.environ.get('GITHUB_SHA','')
    need(os.environ.get('GITHUB_ACTIONS') == 'true' and
         os.environ.get('RUNNER_OS') == 'Linux' and
         os.environ.get('RUNNER_ARCH') == 'X64', 'must run on hosted Linux x64')
    need(re.fullmatch(r'[0-9a-f]{40}',source) is not None, 'invalid GitHub source SHA')
    result = subprocess.run(['git','rev-parse','HEAD'],capture_output=True,timeout=15,check=False)
    need(result.returncode == 0 and result.stdout.decode().strip() == source,
         'checkout does not match exact GitHub event SHA')
    return source

def inspect_apk(apk: Path) -> tuple[str,int]:
    need(apk.name == APK_NAME and apk.is_file() and not apk.is_symlink(),
         'expected regular normal-flavor debug APK')
    size = apk.stat().st_size
    need(MIN_BYTES <= size <= MAX_BYTES, 'APK outside bounded size')
    try:
        with zipfile.ZipFile(apk,'r') as z:
            names = z.namelist()
            need(len(names) == len(set(names)) and 'AndroidManifest.xml' in names,
                 'APK missing manifest or duplicate ZIP members')
            need(len(names) < 150000 and all(
                 not n.startswith('/') and '\\' not in n and '..' not in Path(n).parts
                 for n in names), 'APK ZIP paths are unsafe')
            need(z.testzip() is None, 'APK ZIP CRC failure')
    except (zipfile.BadZipFile, OSError, RuntimeError) as ex:
        raise Refused('OX_OPT03_REFUSED: unreadable APK ZIP') from ex
    digest = hashlib.sha256()
    with apk.open('rb') as fh:
        for block in iter(lambda:fh.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest(),size

def seal(apk: Path,receipt: Path,source: str) -> None:
    need(receipt.name == RECEIPT_NAME and receipt.parent == apk.parent and
         not receipt.is_symlink(), 'receipt destination must be adjacent to APK')
    sha,size = inspect_apk(apk)
    data = {'schema':1,'source_sha':source,'profile':PROFILE,'package_name':PACKAGE,
            'apk_name':APK_NAME,'sha256':sha,'size_bytes':size}
    tmp=receipt.with_suffix('.json.tmp')
    need(not tmp.is_symlink(), 'temporary receipt cannot be a symlink')
    tmp.write_text(json.dumps(data,sort_keys=True,indent=2)+'\n',encoding='utf8')
    tmp.replace(receipt)
    verify(apk,receipt,source)
    print('OX_OPT03_SOURCE_BOUND_APK_SEALED sha256='+sha,flush=True)

def verify(apk: Path,receipt: Path,source: str) -> None:
    need(receipt.name == RECEIPT_NAME and receipt.is_file() and not receipt.is_symlink(),
         'missing regular cache manifest')
    try:
        data=json.loads(receipt.read_text('utf8'))
    except (OSError,UnicodeDecodeError,ValueError) as ex:
        raise Refused('OX_OPT03_REFUSED: invalid manifest') from ex
    need(type(data) is dict and set(data)==FIELDS and
         data.get('schema') == 1 and data.get('source_sha') == source and
         data.get('profile') == PROFILE and data.get('package_name') == PACKAGE and
         data.get('apk_name') == APK_NAME and
         type(data.get('size_bytes')) is int and
         type(data.get('sha256')) is str and
         re.fullmatch(r'[0-9a-f]{64}',data['sha256']) is not None,
         'cache manifest source/profile/shape mismatch')
    sha,size=inspect_apk(apk)
    need(size == data['size_bytes'] and sha == data['sha256'],
         'cached APK bytes differ from source-bound manifest')
    print('OX_OPT03_EXACT_SOURCE_APK_CACHE_VERIFIED sha256='+sha,flush=True)

def verify_android_tools(apk: Path) -> None:
    """Independent package/signature proof on the consumer, after SDK install."""
    home=Path(os.environ.get('ANDROID_HOME',''))
    need(home.is_absolute(), 'Android SDK home absent')
    aapt=home/'build-tools'/'35.0.0'/'aapt'
    signer=home/'build-tools'/'35.0.0'/'apksigner'
    need(aapt.is_file() and signer.is_file(), 'Android 35 build tools absent')
    for cmd in ([str(signer),'verify','--verbose',str(apk)],
                [str(aapt),'dump','badging',str(apk)]):
        try:
            r=subprocess.run(cmd,stdin=subprocess.DEVNULL,capture_output=True,
                             timeout=40,check=False)
        except (OSError,subprocess.TimeoutExpired) as e:
            raise Refused('OX_OPT03_REFUSED: APK inspection tool unavailable') from e
        need(r.returncode == 0, 'APK signature or package inspection failed')
        if cmd[1] == 'dump':
            t=r.stdout.decode('utf8','replace')
            need(re.search(r"(?m)^package: name='"+re.escape(PACKAGE)+r"'(?:\s|$)",t) is not None,
                 'APK package name differs from production debug application')
            need('application-debuggable' in t, 'APK is not explicitly debuggable')
    print('OX_OPT03_ANDROID_PACKAGE_SIGNATURE_AND_DEBUG_PROOF_PASS',flush=True)

def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['seal','verify','verify-tools'])
    p.add_argument('--apk',type=Path,default=Path('build/app/outputs/flutter-apk')/APK_NAME)
    p.add_argument('--receipt',type=Path,default=Path('build/app/outputs/flutter-apk')/RECEIPT_NAME)
    args=p.parse_args()
    source=source_identity()
    if args.mode=='seal': seal(args.apk,args.receipt,source)
    else:
        verify(args.apk,args.receipt,source)
        if args.mode=='verify-tools':verify_android_tools(args.apk)
    return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except (Refused,OSError,ValueError,subprocess.TimeoutExpired) as ex:
        print(str(ex),file=sys.stderr,flush=True)
        raise SystemExit(1)
