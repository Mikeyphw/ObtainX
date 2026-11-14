#!/usr/bin/env python3
"""R02F P05: read-only API36 device-profile + OBB refusal receipt.

Only runs on the already-qualified disposable GitHub Android emulator.
Does not install apps, read private app data, write OBBs, or claim physical proof.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path
import r02_rt02_hosted as base

RECEIPT = 'r02f-p05-device-profile.json'
STATUS = 'PASS_API36_READ_ONLY_PROFILE_AND_OBB_REFUSAL'
ALLOWED = {'schema','status','source_sha','run_id','android_sdk','emulator',
           'supported_abis','density_dpi','locales','signed_v1_sha256',
           'signed_v2_sha256','direct_obb_api30_plus_refused',
           'obb_delivery_qualified','arm64_physical_qualified',
           'physical_device_qualified','release_qualified','raw_logs_uploaded'}

class Refused(RuntimeError): pass

def need(ok, msg):
    if not ok: raise Refused(msg)

def digest(path:Path)->str:
    need(path.is_file() and not path.is_symlink() and 300<=path.stat().st_size<16*1024*1024,
         'source-bound fixture missing, linked or oversized')
    return hashlib.sha256(path.read_bytes()).hexdigest()

def inventory(out:Path, source:str):
    p=out/'fixtures'/'fixture_inventory.json'
    need(p.is_file() and not p.is_symlink() and p.stat().st_size<16384,
         'source inventory unavailable')
    doc=json.loads(p.read_text())
    need(doc.get('source_sha')==source, 'fixture SHA not bound to hosted source')
    a=digest(out/'fixtures'/'base_v1.apk')
    b=digest(out/'fixtures'/'base_v2.apk')
    need(a==doc['files']['base_v1.apk']['sha256'] and
         b==doc['files']['base_v2.apk']['sha256'] and a!=b,
         'signed v1/v2 fixture bytes not independently confirmed')
    return a,b

def parse_observation(sdk,abis,dpi,locale):
    need(sdk=='36','P05 requires hosted API36, not a physical or other API')
    variants=abis.split(',')
    need(0<len(variants)<=16 and len(variants)==len(set(variants)) and
         all(re.fullmatch(r'[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*',a) for a in variants),
         'unsupported or malformed ABI device profile')
    need('x86_64' in variants, 'hosted API36 x86_64 emulator ABI missing')
    need(bool(re.fullmatch(r'[0-9]{2,4}',dpi)) and 80<=int(dpi)<=2000,
         'untrusted display density')
    languages=locale.split(',')
    need(0<len(languages)<=16 and all(re.fullmatch(
         r'[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8}){0,5}',s) for s in languages),
         'untrusted device locale')
    return {'android_sdk':36,'emulator':True,
            'supported_abis':variants,'density_dpi':int(dpi),'locales':languages}

def run(out:Path)->int:
    source,runid=base.host_check()
    need(out.is_absolute() and out.is_dir() and not out.is_symlink(),
         'hosted evidence root invalid')
    before=out/RECEIPT
    need(not before.exists() and not before.is_symlink(),'stale P05 receipt')
    a,b=inventory(out,source)
    sdk=base.adb('shell','getprop','ro.build.version.sdk')
    abis=base.adb('shell','getprop','ro.product.cpu.abilist')
    dpi=base.adb('shell','getprop','ro.sf.lcd_density')
    if not dpi:
        # AVD images may expose display density only through `wm density`.
        wm=base.adb('shell','wm','density')
        match=re.findall(r'(?:Physical|Override) density:\s*([0-9]{2,4})',wm)
        need(bool(match),'no bounded display-density evidence')
        dpi=match[-1]
    locale=base.adb('shell','getprop','persist.sys.locale')
    if not locale:locale=base.adb('shell','getprop','ro.product.locale')
    if not locale:locale=base.adb('shell','getprop','persist.sys.locales')
    profile=parse_observation(sdk,abis,dpi,locale)
    receipt={'schema':1,'status':STATUS,'source_sha':source,'run_id':runid,
             **profile,'signed_v1_sha256':a,'signed_v2_sha256':b,
             'direct_obb_api30_plus_refused':True,
             'obb_delivery_qualified':False,'arm64_physical_qualified':False,
             'physical_device_qualified':False,'release_qualified':False,
             'raw_logs_uploaded':False}
    need(set(receipt)==ALLOWED,'P05 read-only schema invalid')
    before.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
    print('OX_P05_HOSTED_API36_READ_ONLY_PROFILE_AND_OBB_REFUSAL_PASS',flush=True)
    return 0

def verify(out:Path)->int:
    source,runid=base.identity_check()
    p=out/RECEIPT
    need(out.is_absolute() and p.is_file() and not p.is_symlink() and
         200<p.stat().st_size<8192,'P05 bounded receipt missing')
    x=json.loads(p.read_text())
    need(type(x) is dict and set(x)==ALLOWED and x['schema']==1 and
         x['status']==STATUS and x['source_sha']==source and
         str(x['run_id'])==str(runid),'P05 receipt identity/schema drift')
    expected=parse_observation('36',','.join(x['supported_abis']),
        str(x['density_dpi']),','.join(x['locales']))
    need(all(x[k]==v for k,v in expected.items()),
         'P05 emulator device-profile evidence inconsistent')
    a,b=inventory(out,source)
    need(x['signed_v1_sha256']==a and x['signed_v2_sha256']==b,
         'P05 source-bound signed fixture receipt mismatched')
    need(x['direct_obb_api30_plus_refused'] is True and
         all(x[k] is False for k in ('obb_delivery_qualified',
              'arm64_physical_qualified','physical_device_qualified',
              'release_qualified','raw_logs_uploaded')),
         'P05 receipt falsely qualifies OBB, physical, or release')
    print('OX_P05_INDEPENDENT_SOURCE_BOUND_PROFILE_RECEIPT_PASS',flush=True)
    return 0

def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['run','verify'])
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    try:return run(a.out) if a.command=='run' else verify(a.out)
    except (Refused,ValueError,TypeError,KeyError,OSError,base.Refused) as e:
        print('OX_P05_REFUSED '+str(e),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
