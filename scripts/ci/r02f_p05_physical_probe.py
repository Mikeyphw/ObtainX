#!/usr/bin/env python3
"""Explicit-only read-only profile probe. No installation, root, or APK writes."""
from __future__ import annotations
import argparse,json,re,subprocess,sys

def adb(serial,*args):
    command=['adb','-s',serial,*args]
    if any(x in {'install','uninstall','push','pull','root','remount','reboot','shell am','input'}
           for x in args):
        raise RuntimeError('write-capable ADB command refused')
    p=subprocess.run(command,capture_output=True,text=True,timeout=20,check=False)
    if p.returncode:raise RuntimeError('read-only ADB query failed: '+args[0])
    return p.stdout.strip()

def profile(serial, ack):
    if ack!='I_AUTHORIZE_READ_ONLY_DEVICE_PROBE':
        raise RuntimeError('explicit read-only acceptance acknowledgement required')
    if not re.fullmatch(r'[A-Za-z0-9._:-]{1,60}',serial):
        raise RuntimeError('invalid device serial')
    if adb(serial,'get-state')!='device':raise RuntimeError('device not connected')
    def prop(x):return adb(serial,'shell','getprop',x)
    sdk=prop('ro.build.version.sdk')
    abis=prop('ro.product.cpu.abilist')
    locale=prop('persist.sys.locale') or prop('ro.product.locale')
    density=prop('ro.sf.lcd_density')
    if not density:
        wm=adb(serial,'shell','wm','density')
        found=re.findall(r'(?:Physical|Override) density:\s*([0-9]{2,4})',wm)
        if not found:raise RuntimeError('no display density evidence')
        density=found[-1]
    if not sdk.isdigit() or not (1<=int(sdk)<=100):raise RuntimeError('invalid API evidence')
    if not re.fullmatch(r'[A-Za-z0-9_,-]{1,256}',abis):
        raise RuntimeError('invalid ABI list')
    if not re.fullmatch(r'[0-9]{2,4}',density):raise RuntimeError('invalid density')
    if not re.fullmatch(r'[A-Za-z0-9_,-]{2,100}',locale):
        raise RuntimeError('invalid locale')
    report={'schema':1,'probe':'P05_PHYSICAL_READ_ONLY_INSPECTION',
      'android_sdk':int(sdk),'supported_abis':abis.split(','),
      'density_dpi':int(density),'locales':locale.split(','),
      'device_writes':False,'obb_delivery_qualified':False,
      'installer_runtime_qualified':False,'release_qualified':False}
    return report

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--serial',default='localhost:5555')
    ap.add_argument('--ack',required=True)
    a=ap.parse_args()
    report=profile(a.serial, a.ack)
    print(json.dumps(report,sort_keys=True,indent=2))
    print('OX_P05_PHYSICAL_READ_ONLY_INSPECTION_COMPLETE_NOT_QUALIFIED')
    return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as e:
        print('OX_P05_PHYSICAL_REFUSED '+str(e),file=sys.stderr);raise SystemExit(2)
