#!/usr/bin/env python3
"""Bounded API36 hosted-sdk package download; reject every unsafe/non-ZIP error.

Only a confirmed corrupt SDK ZIP can be retried once. This does not download
APKs or modify Android user data, Android sessions or security acceptance.
"""
from __future__ import annotations
import os, re, subprocess, sys, tempfile, time
from pathlib import Path

PACKAGES=('platforms;android-36','build-tools;35.0.0',
          'system-images;android-36;google_apis;x86_64')
CORRUPT_ZIP='Error reading Zip content from a SeekableByteChannel.'

class Refused(RuntimeError): pass

def need(ok, message):
    if not ok: raise Refused(message)

def sdk_proof(root: Path)->None:
    paths=(root/'platforms/android-36/android.jar',
           root/'build-tools/35.0.0/aapt2',
           root/'system-images/android-36/google_apis/x86_64/source.properties',
           root/'system-images/android-36/google_apis/x86_64/system.img')
    for item in paths:
        need(item.is_file() and not item.is_symlink() and item.stat().st_size > 0,
             'SDK_IMAGE_PROOF_REFUSED_'+item.name.replace('.','_'))
    need(paths[-1].stat().st_size > 1024*1024,
         'SDK_IMAGE_PROOF_REFUSED_TRUNCATED_SYSTEM_IMAGE')

def attempt_install(run=subprocess.run, sleep=time.sleep, sdk_root:Path|None=None,
                    env:dict|None=None)->int:
    e=dict(os.environ if env is None else env)
    need(e.get('GITHUB_ACTIONS')=='true' and e.get('RUNNER_OS')=='Linux' and
         e.get('RUNNER_ARCH')=='X64', 'SDK_HOSTED_LINUX_X64_REQUIRED')
    root=Path(sdk_root or e.get('ANDROID_HOME') or e.get('ANDROID_SDK_ROOT') or '')
    need(root.is_dir() and root.is_absolute(), 'SDK_ROOT_ABSENT_OR_NOT_ABSOLUTE')
    cmd=['sdkmanager','--install',*PACKAGES]
    for attempt in (1,2):
        with tempfile.TemporaryFile(mode='w+b',dir=e.get('RUNNER_TEMP') or None) as stream:
            try:
                result=run(cmd,stdin=subprocess.DEVNULL,stdout=stream,
                           stderr=subprocess.STDOUT,timeout=480,check=False)
            except (OSError,subprocess.TimeoutExpired) as exc:
                raise Refused('SDK_INSTALL_TOOL_FAILURE_'+type(exc).__name__) from exc
            stream.seek(0,2);length=stream.tell()
            stream.seek(max(0,length-128000))
            last=stream.read().decode('utf8','replace')
        if result.returncode==0:
            sdk_proof(root)
            print('OX_API36_SDK_PROVISION_AND_IMAGE_PROOF_PASS attempt='+str(attempt),flush=True)
            return 0
        # Never retry network/server, credentials, disk, license, KVM, or
        # arbitrary SDK failures. No cache deletion or integrity bypass.
        if attempt==1 and CORRUPT_ZIP in last:
            print('OX_API36_SDK_ZIP_CORRUPTION_RETRY_ONCE',flush=True)
            sleep(5)
            continue
        raise Refused('SDK_INSTALL_REFUSED_'+('CORRUPT_ZIP_SECOND_ATTEMPT'
                        if CORRUPT_ZIP in last else 'UNCLASSIFIED_ERROR')+
                      '_rc'+str(result.returncode))
    raise Refused('SDK_INSTALL_RETRY_EXHAUSTED')

def main()->int:
    try:
        need(tuple(sys.argv[1:])==PACKAGES, 'SDK_PACKAGE_ARGS_MISMATCH')
        return attempt_install()
    except Refused as exc:
        print('OX_API36_SDK_REFUSED: '+str(exc),file=sys.stderr,flush=True)
        return 1

if __name__=='__main__':raise SystemExit(main())
