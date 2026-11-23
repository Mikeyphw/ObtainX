#!/usr/bin/env python3
"""API36-only Shizuku/Dhizuku availability and explicitly authorized read-only probes.

Never starts a privileged service, grants a permission, changes device owner,
installs an APK, or writes to a physical device. Actual privileged package
installation remains NOT_QUALIFIED and requires a separate future acceptance.
"""
from __future__ import annotations
import argparse,hashlib,json,re,subprocess,sys,time
from pathlib import Path
import r02_rt02_hosted as base

RECEIPT='r02f-p04-backend-availability.json'
STATUS='PASS_EMULATOR_BACKENDS_UNAVAILABLE_NOT_INSTALL_QUALIFIED'
AUTH_STATUS='PASS_AUTHORIZED_READ_ONLY_BACKEND_AVAILABLE_NOT_INSTALL_QUALIFIED'
PACKAGES={'shizuku':'moe.shizuku.privileged.api','dhizuku':'com.rosan.dhizuku'}
MARKERS=('OX_P04_SHIZUKU_REAL_ABSENCE_PASS','OX_P04_DHIZUKU_REAL_ABSENCE_PASS')
PROBE_TEST='integration_test/r02f_p04_backend_unavailable_test.dart'
ACK='I_AUTHORIZE_DISPOSABLE_API36_READ_ONLY_BACKEND_PROBE'
class Refused(RuntimeError):pass
def need(ok,reason):
    if not ok:raise Refused(reason)
def sha(p:Path):return hashlib.sha256(p.read_bytes()).hexdigest()

def permission_probe_planned(mode:str,ack:str)->bool:
    return mode in PACKAGES and ack == ACK

def safe_schema(receipt:dict,source:str,run_id:str,log_digest:str)->bool:
    fields={'schema','status','source_sha','run_id','mode','backend_packages',
            'shizuku_unavailable','dhizuku_unavailable','selected_backend',
            'selected_backend_authorized_read_only','signed_fixture_source_bound',
            'private_log_sha256','privileged_install_performed','backend_install_qualified',
            'physical_device_qualified','release_qualified','raw_logs_uploaded'}
    if set(receipt)!=fields:return False
    if receipt.get('schema')!=1 or receipt.get('source_sha')!=source or str(receipt.get('run_id'))!=run_id:return False
    if receipt.get('backend_packages')!=PACKAGES or receipt.get('private_log_sha256')!=log_digest:return False
    if any(receipt.get(k) is not False for k in ('privileged_install_performed','backend_install_qualified',
            'physical_device_qualified','release_qualified','raw_logs_uploaded')):return False
    if receipt.get('signed_fixture_source_bound') is not True:return False
    if receipt.get('mode')=='unavailable':
        return (receipt.get('status')==STATUS and receipt.get('selected_backend') is None and
                receipt.get('shizuku_unavailable') is True and receipt.get('dhizuku_unavailable') is True and
                receipt.get('selected_backend_authorized_read_only') is False)
    if receipt.get('mode')=='authorized_read_only':
        sel=receipt.get('selected_backend')
        return (receipt.get('status')==AUTH_STATUS and sel in PACKAGES and
                receipt.get('selected_backend_authorized_read_only') is True and
                receipt.get('shizuku_unavailable') is False and receipt.get('dhizuku_unavailable') is False)
    return False

def package_presence(pkg:str)->bool:
    # Exact package path from a disposable emulator; any parse ambiguity refuses.
    output=base.adb('shell','pm','path',pkg,timeout=25,allow_failure=True)
    if not output:return False
    paths=output.splitlines()
    need(len(paths)>=1 and all(re.fullmatch(r'package:/data/app/[A-Za-z0-9_+./~=-]+\.apk',p) for p in paths),
         'unexpected backend service package path')
    return True

def check_fixture(out:Path,source:str):
    fx=out/'fixtures';inventory=json.loads((fx/'fixture_inventory.json').read_text())
    need(inventory.get('source_sha')==source,'signed fixture does not match exact HEAD')
    for n in ('base_v1.apk','base_v2.apk'):
        need(sha(fx/n)==inventory['files'][n]['sha256'], 'signed APK fixture mutated: '+n)
    return fx

def run(out:Path, *, mode='unavailable', backend=None, ack='') -> int:
    source,runid=base.host_check()
    need(out.is_dir() and out.is_absolute() and not out.is_symlink(),'real hosted evidence root required')
    check_fixture(out,source)
    receipt=out/RECEIPT;need(not receipt.exists() and not receipt.is_symlink(),'stale backend receipt refused')
    if mode=='authorized_read_only':
        need(permission_probe_planned(backend or '',ack),'explicit read-only authorized backend acknowledgement missing')
    else:need(mode=='unavailable' and backend is None and not ack,'unavailable mode cannot assume authorization')
    presence={k:package_presence(v) for k,v in PACKAGES.items()}
    if mode=='unavailable':need(presence=={'shizuku':False,'dhizuku':False},'clean emulator backend unexpectedly installed')
    else:need(presence[backend] is True,'selected backend service not installed on disposable emulator')
    log=out/'r02f-p04-backend-private.log'
    cmd=['flutter','test',PROBE_TEST,'-d',base.SERIAL,'--flavor','normal',
         '--no-pub','--reporter','expanded',
         '--dart-define=OX_P04_BACKEND_TEST_MODE='+mode]
    if backend:cmd.append('--dart-define=OX_P04_BACKEND_SELECTED='+backend)
    with log.open('wb') as f:
        p=subprocess.run(cmd,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,timeout=300)
    private=log.read_text('utf8','replace')
    need(p.returncode==0 and 'All tests passed!' in private,
         'native backend plugin unavailable/authorization contract failed; private log retained')
    if mode=='unavailable':
        need(all(private.count(x)==1 for x in MARKERS),'both native backend absence markers required')
    else:
        need(private.count('OX_P04_BACKEND_EXPLICIT_AUTHORIZED_READ_ONLY_PASS')==1,
             'selected native backend explicit authorization marker missing')
    data={'schema':1,'status':STATUS if mode=='unavailable' else AUTH_STATUS,
          'source_sha':source,'run_id':runid,'mode':mode,'backend_packages':PACKAGES,
          'shizuku_unavailable':mode=='unavailable','dhizuku_unavailable':mode=='unavailable',
          'selected_backend':backend,'selected_backend_authorized_read_only':mode!='unavailable',
          'signed_fixture_source_bound':True,'private_log_sha256':sha(log),
          'privileged_install_performed':False,'backend_install_qualified':False,
          'physical_device_qualified':False,'release_qualified':False,'raw_logs_uploaded':False}
    need(safe_schema(data,source,runid,sha(log)),'generated backend receipt invalid')
    receipt.write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')
    print('OX_P04_REAL_BACKEND_'+('ABSENCE' if mode=='unavailable' else 'EXPLICIT_READ_ONLY_AUTH')+'_PASS; INSTALL_NOT_QUALIFIED',flush=True)
    return 0

def verify(out:Path)->int:
    source,runid=base.identity_check() # independent offline: no ADB in verifier
    receipt=out/RECEIPT;log=out/'r02f-p04-backend-private.log'
    need(out.is_absolute() and not out.is_symlink() and receipt.is_file() and
         not receipt.is_symlink() and 100<receipt.stat().st_size<4096 and
         log.is_file() and not log.is_symlink(),'backend receipt or private log missing/unsafe')
    data=json.loads(receipt.read_text('utf8'))
    need(safe_schema(data,source,runid,sha(log)),'backend evidence schema/source/qualification drift')
    fx=check_fixture(out,source)
    need((fx/'base_v1.apk').is_file(),'host fixture missing')
    print('OX_P04_BACKEND_OFFLINE_SOURCE_BOUND_RECEIPT_PASS; NO_INSTALL_CLAIM',flush=True)
    return 0

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('command',choices=('run','verify','authorized-read-only'))
    ap.add_argument('--out',required=True,type=Path)
    ap.add_argument('--backend',choices=('shizuku','dhizuku'))
    ap.add_argument('--ack',default='')
    a=ap.parse_args()
    try:
        if a.command=='verify':
            need(not a.backend and not a.ack,'offline verify accepts no probe settings')
            return verify(a.out)
        if a.command=='authorized-read-only':
            return run(a.out,mode='authorized_read_only',backend=a.backend,ack=a.ack)
        return run(a.out,backend=a.backend,ack=a.ack)
    except (OSError,ValueError,TypeError,KeyError,Refused,base.Refused,subprocess.TimeoutExpired) as e:
        print('OX_P04_BACKEND_REFUSED '+str(e),file=sys.stderr)
        return 2
if __name__=='__main__':raise SystemExit(main())
