#!/usr/bin/env python3
"""P04B P03 signed, disposable delayed-decline APK for hosted API36 only.

Reuse the already-qualified P01 builder; alter only a bounded foreground delay.
No PackageInstaller or shell-privileged code is added to the APK.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import r02f_p04b_target as delegate

PACKAGE=delegate.PACKAGE
ACTIVITY=delegate.ACTIVITY
APK='p04b-p03-delayed-decline.apk'
OLD='}, 1500L);'
NEW='}, 12000L);'

def build(out:Path):
    if not out.is_absolute() or not out.is_dir() or out.is_symlink():
        raise ValueError('P03 fixture needs an existing real absolute directory')
    if delegate.JAVA.count(OLD)!=1 or delegate.JAVA.count(NEW):
        raise ValueError('P03 source-bound P01 target delay anchor drift')
    original_java=delegate.JAVA
    original_apk=delegate.APK
    try:
        delegate.JAVA=original_java.replace(OLD,NEW,1)
        delegate.APK=APK
        delegate.build(out)
    finally:
        delegate.JAVA=original_java
        delegate.APK=original_apk
    print('OX_P04B_P03_HOSTED_SIGNED_DELAYED_DECLINE_TARGET_PASS',flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',required=True,type=Path)
    a=p.parse_args()
    try:build(a.out);return 0
    except (ValueError,RuntimeError,OSError) as exc:
        print('OX_P04B_P03_TARGET_REFUSED '+str(exc),flush=True)
        return 2

if __name__=='__main__':raise SystemExit(main())
