#!/usr/bin/env python3
"""Bounded hosted API36 SDK installer with exact-package preflight and safe diagnostics.

OPT06 P02 skips sdkmanager ONLY for individually attested SDK packages. The
original post-install image proof and single corrupt-ZIP retry remain mandatory.
This is SDK provisioning, not emulator / installer / device qualification.
"""
from __future__ import annotations
import os, re, subprocess, sys, tempfile, time, stat
from pathlib import Path

PACKAGES=('platforms;android-36','build-tools;35.0.0',
          'system-images;android-36;google_apis;x86_64')
CORRUPT_ZIP='Error reading Zip content from a SeekableByteChannel.'

# Exact SDK component properties and conservative minimum binary sizes. These
# checks are deliberately stricter than the existing post-install proof: an
# ambiguous local installation is installed through sdkmanager, not skipped.
COMPONENTS=(
    ('platforms/android-36/android.jar','platforms/android-36/source.properties',
     'AndroidVersion.ApiLevel','36',1024*1024),
    ('build-tools/35.0.0/aapt2','build-tools/35.0.0/source.properties',
     'Pkg.Revision','35.0.0',1024*1024),
    ('system-images/android-36/google_apis/x86_64/system.img',
     'system-images/android-36/google_apis/x86_64/source.properties',
     'AndroidVersion.ApiLevel','36',1024*1024),
)

class Refused(RuntimeError): pass

def need(ok, message):
    if not ok: raise Refused(message)


def _regular(root:Path, relative:str, min_bytes:int)->bool:
    """Never treat symlinked SDK inventory or small placeholders as installed."""
    path=root
    for name in Path(relative).parts:
        path=path/name
        if path.is_symlink():return False
    try:
        return path.is_file() and path.stat().st_size>=min_bytes
    except OSError:
        return False


def _properties(root:Path,relative:str)->dict[str,str]:
    if not _regular(root,relative,10):return {}
    path=root/relative
    try:
        if path.stat().st_size>65536:return {}
        raw=path.read_text(encoding='utf8')
    except (OSError,UnicodeError):return {}
    values={}
    for line in raw.splitlines():
        line=line.strip()
        if not line or line.startswith('#') or line.startswith('!'):continue
        if '=' not in line:return {}
        key,value=line.split('=',1);key=key.strip();value=value.strip()
        if not key or key in values:return {}
        values[key]=value
    return values


def present_packages(root:Path)->tuple[bool,bool,bool]:
    """Conservative, exact-version SDK preflight; never a runtime qualification."""
    present=[]
    for path,props,key,value,size in COMPONENTS:
        info=_properties(root,props)
        ok=_regular(root,path,size) and info.get(key)==value
        if path.endswith('/system.img'):
            ok=ok and info.get('SystemImage.Abi')=='x86_64' and \
               info.get('SystemImage.TagId')=='google_apis'
        present.append(bool(ok))
    return tuple(present)


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


def _kvm_status()->str:
    """Informational only: bash hard gate still owns /dev/kvm acceptance."""
    try:
        info=os.stat('/dev/kvm')
        if stat.S_ISCHR(info.st_mode) and os.access('/dev/kvm',os.R_OK|os.W_OK):
            return 'ready'
    except OSError:pass
    return 'unavailable'


def _diagnostics(env:dict, ready:tuple[bool,bool,bool], installs:int,
                 attempts:int, seconds:int)->None:
    # No absolute SDK paths, ADB output, environment dumps, or tokens are shown.
    label=''.join('1' if x else '0' for x in ready)
    marker=(f'OX_OPT06_P02_SDK_DIAGNOSTICS schema=1 preinstalled={label} '
            f'packages_requested={installs} sdkmanager_attempts={attempts} '
            f'elapsed_seconds={seconds} kvm={_kvm_status()}')
    print(marker,flush=True)
    summary=env.get('GITHUB_STEP_SUMMARY','')
    if summary:
        path=Path(summary)
        # Summary is optional telemetry; it must never bypass package proof.
        if path.is_absolute() and not path.is_symlink() and path.parent.is_dir():
            try:
                with path.open('a',encoding='utf8') as output:
                    output.write('ObtainX OPT06 P02 SDK: preinstalled='+label+
                                 ', packages_requested='+str(installs)+
                                 ', sdkmanager_attempts='+str(attempts)+
                                 ', elapsed_seconds='+str(seconds)+'s, kvm='+_kvm_status()+'\n')
            except OSError:
                print('OX_OPT06_P02_DIAGNOSTICS_SUMMARY_UNAVAILABLE',flush=True)


def attempt_install(run=subprocess.run, sleep=time.sleep, sdk_root:Path|None=None,
                    env:dict|None=None)->int:
    e=dict(os.environ if env is None else env)
    need(e.get('GITHUB_ACTIONS')=='true' and e.get('RUNNER_OS')=='Linux' and
         e.get('RUNNER_ARCH')=='X64', 'SDK_HOSTED_LINUX_X64_REQUIRED')
    root=Path(sdk_root or e.get('ANDROID_HOME') or e.get('ANDROID_SDK_ROOT') or '')
    need(root.is_dir() and root.is_absolute(), 'SDK_ROOT_ABSENT_OR_NOT_ABSOLUTE')
    start=time.monotonic()
    ready=present_packages(root)
    missing=tuple(pkg for pkg,available in zip(PACKAGES,ready) if not available)
    print('OX_OPT06_P02_SDK_PRECHECK=' + ''.join('1' if x else '0' for x in ready),flush=True)
    if not missing:
        sdk_proof(root)
        _diagnostics(e,ready,0,0,int(time.monotonic()-start))
        print('OX_API36_SDK_PREINSTALLED_EXACT_PROOF_PASS',flush=True)
        return 0
    cmd=['sdkmanager','--install',*missing]
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
            _diagnostics(e,ready,len(missing),attempt,int(time.monotonic()-start))
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
