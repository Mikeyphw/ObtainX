#!/usr/bin/env python3
"""Create source-bound disposable APK archives after RT02 signing fixture stage.

No APKs, signing keys, or raw package data are included in CI artifacts.
All files use a fixed tiny inventory; malicious cases deliberately remain local.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tarfile
import zipfile

PKG='dev.bikram.obtainx.rt02.fixture'
POSITIVE=('apks','apkm','xapk','zip','tar.gz')
NEGATIVE=('traversal','ambiguous')
NAMES=tuple(f'bundle.{suffix}' for suffix in POSITIVE)+('blocked-traversal.apks','ambiguous-base.apkm')
MEMBERS=('payload/base.apk','payload/config.x86_64.apk')

def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()

def need(ok:bool,msg:str)->None:
    if not ok:raise RuntimeError(msg)

def archive_entries(kind:str,base:bytes,split:bytes)->dict[str,bytes]:
    need(kind in POSITIVE+NEGATIVE,'unknown archive fixture')
    members={'payload/base.apk':base,'payload/config.x86_64.apk':split}
    if kind=='xapk':
        members['manifest.json']=json.dumps({'package_name':PKG,'version_code':2},sort_keys=True).encode()
    elif kind=='apkm':
        members['info.json']=b'{"format":"apkm","source":"RT02C CI"}'
    elif kind=='apks':
        members['toc.json']=b'{"format":"apks","source":"RT02C CI"}'
    if kind=='traversal':
        members['../escape.apk']=base
    if kind=='ambiguous':
        members['payload/another-base.apk']=base
    return members

def pack_zip(entries:dict[str,bytes])->bytes:
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path,data in sorted(entries.items()):
            info=zipfile.ZipInfo(path,date_time=(2026,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            z.writestr(info,data)
    return out.getvalue()

def pack_tar(entries:dict[str,bytes])->bytes:
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w:gz',format=tarfile.PAX_FORMAT) as t:
        for path,data in sorted(entries.items()):
            info=tarfile.TarInfo(path);info.size=len(data);info.mode=0o644
            info.uid=0;info.gid=0;info.mtime=0
            t.addfile(info,io.BytesIO(data))
    return out.getvalue()

def build(out:Path)->dict:
    need(out.is_absolute() and out.is_dir(),'absolute existing CI fixture directory required')
    need(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_OS')=='Linux',
         'hosted Linux GitHub runner required')
    source=os.environ.get('GITHUB_SHA','')
    need(bool(re.fullmatch('[0-9a-f]{40}',source)),'invalid source SHA')
    baseline=json.loads((out/'fixture_inventory.json').read_text())
    need(baseline.get('source_sha')==source and baseline.get('fixture_package')==PKG,
         'RT02 source/signer baseline mismatch')
    expected=baseline.get('files',{})
    base=(out/'base_v2.apk').read_bytes()
    split=(out/'config.x86_64.apk').read_bytes()
    need(sha(base)==expected['base_v2.apk']['sha256'] and
         sha(split)==expected['config.x86_64.apk']['sha256'],
         'signed APK payload SHA mismatch')
    files={}
    for kind in POSITIVE+NEGATIVE:
        filename=(f'bundle.{kind}' if kind in POSITIVE else
                  'blocked-traversal.apks' if kind=='traversal' else 'ambiguous-base.apkm')
        need(not (out/filename).exists(),'archive fixture already exists: '+filename)
        entries=archive_entries(kind,base,split)
        raw=pack_tar(entries) if kind=='tar.gz' else pack_zip(entries)
        need(500 < len(raw) < 12*1024*1024, 'archive size outside CI fixture budget')
        (out/filename).write_bytes(raw)
        files[filename]={'sha256':sha(raw),'bytes':len(raw),'case':kind,
                         'contains_v2_base_and_split':True}
    inventory={'schema':1,'source_sha':source,'fixture_package':PKG,
               'signed_base_sha256':sha(base),'signed_split_sha256':sha(split),
               'files':files,'no_private_keys':True,'hosted_only':True,
               'release_qualified':False,'physical_device_qualified':False}
    (out/'rt02c_inventory.json').write_text(json.dumps(inventory,sort_keys=True,indent=2)+'\n')
    return inventory

def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path)
    opts=p.parse_args()
    try:
        data=build(opts.out)
        print('OX_R02_RT02C_ARCHIVE_FIXTURES_PASS: '+','.join(data['files']),flush=True)
        return 0
    except (OSError,KeyError,ValueError,RuntimeError,zipfile.BadZipFile) as e:
        print('OX_R02_RT02C_FIXTURE_REFUSED: '+str(e),file=sys.stderr,flush=True)
        return 1
if __name__=='__main__':raise SystemExit(main())
