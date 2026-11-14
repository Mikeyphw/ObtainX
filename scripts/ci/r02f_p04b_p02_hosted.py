#!/usr/bin/env python3
"""Hosted API36 external positive installation with independent signed bytes.

Receives Android user approval in ephemeral emulator only. No privileged/root
installer and no physical-device writes. Raw Flutter logs never uploaded.
"""
from __future__ import annotations
import argparse,hashlib,json,re,subprocess,sys,threading,time,xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import r02_rt02_hosted as base
import r02f_p04b_p02_target as target

RECEIPT='r02f-p04b-p02-positive.json'
STATUS='PASS_EXTERNAL_TARGET_SYSTEM_APPROVAL_AND_SIGNED_V2_BYTES'
PORT=18784
MARKERS=('OX_P04B_P02_REAL_EXTERNAL_HANDOFF_STARTED',
         'OX_P04B_P02_REAL_EXTERNAL_BRIDGE_NO_FALSE_SUCCESS_PASS')
PKG='dev.bikram.obtainx.rt02.fixture'
class Refused(RuntimeError): pass
def need(ok,msg):
    if not ok:raise Refused(msg)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
class FixtureServer(BaseHTTPRequestHandler):
    apk:Path
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path!='/base_v2.apk':self.send_error(404);return
        raw=self.apk.read_bytes();need(300<len(raw)<16*1024*1024,'fixture size invalid')
        self.send_response(200);self.send_header('Content-Type','application/vnd.android.package-archive')
        self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)

def package_observation(fixtures:Path,version:int)->dict:
    paths=base.adb('shell','pm','path',PKG,timeout=25).splitlines()
    need(len(paths)==1 and paths[0].startswith('package:/data/app/') and paths[0].endswith('/base.apk'),
         'PackageManager did not report one expected signed base APK')
    match=re.fullmatch(r'package:(/data/app/[A-Za-z0-9_+./~=-]+/base\.apk)',paths[0])
    need(match is not None,'unexpected installed package path')
    digest=base.adb('shell','sha256sum',match.group(1),timeout=60).split()
    expected=sha(fixtures/('base_v1.apk' if version==1 else 'base_v2.apk'))
    need(len(digest)==2 and digest[0]==expected,'installed signed APK bytes differ')
    data=base.adb('shell','dumpsys','package',PKG,timeout=55)
    versions=re.findall(r'\bversionCode=(\d+)\b',data)
    need(str(version) in versions and str(3-version) not in versions,
         'expected Android versionCode not proven')
    return {'version_code':version,'base_sha256':expected,'split_count':0}

def target_observation()->dict:
    raw=base.adb('shell','run-as',target.PACKAGE,'cat','shared_prefs/p04b_positive.xml',timeout=25)
    need(raw.lstrip().startswith('<?xml') and len(raw)<4096,'target receipt missing or unbounded')
    root=ET.fromstring(raw);need(root.tag=='map','target receipt malformed')
    out={x.attrib.get('name'):x.text for x in root if x.tag=='string'}
    need(set(out)=={'sha256','status'},'target receipt fields unexpected')
    return out

def approve_if_verified()->bool:
    # Emulator-only verification of an actual PackageInstaller-owned dialog.
    # Refuse generic screen tapping or uncontrolled permission grants.
    try:
        base.adb('shell','uiautomator','dump','/sdcard/p04b-approval.xml',timeout=20)
        xml=base.adb('shell','cat','/sdcard/p04b-approval.xml',timeout=20)
        root=ET.fromstring(xml)
    except (Exception,subprocess.TimeoutExpired):return False
    for node in root.iter('node'):
        item=node.attrib
        pkg=item.get('package','')
        title=item.get('text','').strip().lower()
        if pkg not in ('com.google.android.packageinstaller','com.android.packageinstaller',
                       'com.google.android.permissioncontroller',
                       'com.android.permissioncontroller'):
            continue
        if title not in ('install','update','continue','install app','update app'):
            continue
        if item.get('clickable')!='true' or item.get('enabled')!='true':continue
        m=re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]',item.get('bounds',''))
        if m is None:continue
        x1,y1,x2,y2=map(int,m.groups())
        if not (0<=x1<x2<=2000 and 0<=y1<y2<=3000):continue
        base.adb('shell','input','tap',str((x1+x2)//2),str((y1+y2)//2),timeout=15)
        return True
    return False

def run(out:Path)->int:
    source,runid=base.host_check()
    need(out.is_absolute() and out.is_dir() and not out.is_symlink(),'CI evidence root invalid')
    fx=out/'fixtures'; inv=json.loads((fx/'fixture_inventory.json').read_text())
    tv=json.loads((fx/'p04b_positive_inventory.json').read_text())
    need(inv.get('source_sha')==source and tv.get('source_sha')==source and
         tv.get('package')==target.PACKAGE and tv.get('activity')==target.ACTIVITY,
         'signed fixture source/target identity drift')
    need(tv.get('requires_system_user_approval') is True and
         tv.get('only_disposable_fixture_install') is True and
         tv.get('signed_disposable_target') is True,
         'target is not scoped to disposable system user approval')
    for name,want in ((target.APK,tv['sha256']),
                      ('base_v1.apk',inv['files']['base_v1.apk']['sha256']),
                      ('base_v2.apk',inv['files']['base_v2.apk']['sha256'])):
        need(sha(fx/name)==want,'source-bound signed fixture mutated')
    dest=out/RECEIPT;need(not dest.exists() and not dest.is_symlink(),'stale positive receipt')
    server=None;process=None;approvals=0
    try:
        base.adb('install','-r','-t',str(fx/target.APK),timeout=90)
        base.adb('shell','appops','set',target.PACKAGE,'REQUEST_INSTALL_PACKAGES','allow',timeout=30)
        base.adb('install','-r','-t',str(fx/'base_v1.apk'),timeout=90)
        before=package_observation(fx,1)
        FixtureServer.apk=fx/'base_v2.apk'
        server=ThreadingHTTPServer(('127.0.0.1',PORT),FixtureServer)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base.adb('reverse',f'tcp:{PORT}',f'tcp:{PORT}')
        log=out/'r02f-p04b-p02-private.log'
        argv=['flutter','test','integration_test/r02f_p04b_p02_external_positive_test.dart',
              '-d',base.SERIAL,'--flavor','normal','--no-pub','--reporter','expanded',
              '--dart-define=OX_P04B_P02_BASE_SHA='+inv['files']['base_v2.apk']['sha256']]
        with log.open('wb') as writer:
            process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=writer,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+720
            while process.poll() is None and time.monotonic()<deadline:
                # Poll for an explicit PackageInstaller approval only after the
                # disposable target reports that it committed its session.
                observed=None
                try:observed=target_observation()
                except (Refused,base.Refused,subprocess.TimeoutExpired,ValueError,ET.ParseError):pass
                if approvals==0 and observed is not None and observed.get('status') in (
                        'approval_pending','user_approval_requested'):
                    if approve_if_verified():
                        approvals+=1
                        print('OX_P04B_P02_REAL_SYSTEM_APPROVAL_TAPPED',flush=True)
                time.sleep(3)
            if process.poll() is None:
                process.kill();process.wait(timeout=15)
                raise Refused('hosted Flutter external positive test timed out')
        private=log.read_text('utf8','replace')
        need(process.returncode==0 and 'All tests passed!' in private and
             all(private.count(marker)==1 for marker in MARKERS),
             'production Flutter external handoff test refused; private log retained')
        need(approvals==1,'system PackageInstaller approval not observed exactly once')
        # The PackageInstaller terminal callback can arrive after Flutter has
        # returned from its broadcast waiter. This is a bounded observation,
        # NEVER a synthetic success on timeout.
        terminal_deadline=time.monotonic()+30
        terminal={}
        while time.monotonic()<terminal_deadline:
            terminal=target_observation()
            if terminal.get('status')=='system_status_success':break
            time.sleep(0.5)
        need(terminal=={
             'sha256':inv['files']['base_v2.apk']['sha256'],
             'status':'system_status_success'},
             'disposable third-party target did not report Android status success')
        after=package_observation(fx,2)
        need(before['version_code']==1 and after['version_code']==2 and
             before['base_sha256'] != after['base_sha256'],
             'independent signed v1 to v2 package replacement not proved')
        receipt={'schema':1,'status':STATUS,'source_sha':source,'run_id':runid,
                 'target_component':target.ACTIVITY,'target_sha256':tv['sha256'],
                 'v2_sha256':inv['files']['base_v2.apk']['sha256'],
                 'target_received_sha256':target_observation()['sha256'],
                 'before':before,'after':after,'system_approval_taps':approvals,
                 'flutter_log_sha256':sha(log),'external_mode':'production_native_intent',
                 'android_install_status_verified':True,'signed_bytes_verified':True,
                 'dart_handoff_not_success':True,'physical_device_qualified':False,
                 'shizuku_qualified':False,'dhizuku_qualified':False,
                 'release_qualified':False,'raw_logs_uploaded':False}
        dest.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
        print('OX_P04B_P02_REAL_EXTERNAL_SYSTEM_APPROVED_SIGNED_V2_BYTES_PASS',flush=True)
        return 0
    finally:
        if process is not None and process.poll() is None:process.kill();process.wait(timeout=15)
        if server is not None:server.shutdown();server.server_close()
        base.adb('reverse','--remove',f'tcp:{PORT}',allow_failure=True)
        base.adb('shell','pm','uninstall',target.PACKAGE,allow_failure=True)
        base.adb('shell','pm','uninstall',PKG,allow_failure=True)

def verify(out:Path)->int:
    source,runid=base.identity_check()
    p=out/RECEIPT
    need(out.is_absolute() and p.is_file() and not p.is_symlink() and 100<p.stat().st_size<8192,
         'positive receipt missing or invalid')
    obj=json.loads(p.read_text())
    fields={'schema','status','source_sha','run_id','target_component','target_sha256',
            'v2_sha256','target_received_sha256','before','after','system_approval_taps',
            'flutter_log_sha256','external_mode','android_install_status_verified',
            'signed_bytes_verified','dart_handoff_not_success','physical_device_qualified',
            'shizuku_qualified','dhizuku_qualified','release_qualified','raw_logs_uploaded'}
    need(set(obj)==fields and obj['schema']==1 and obj['status']==STATUS and
         obj['source_sha']==source and str(obj['run_id'])==runid and
         obj['target_component']==target.ACTIVITY,'positive receipt schema/source drift')
    fx=out/'fixtures';inv=json.loads((fx/'fixture_inventory.json').read_text())
    tv=json.loads((fx/'p04b_positive_inventory.json').read_text())
    need(inv.get('source_sha')==source and tv.get('source_sha')==source and
         tv.get('requires_system_user_approval') is True and
         tv.get('only_disposable_fixture_install') is True,
         'positive fixture inventory source/safety drift')
    need(obj['target_sha256']==tv['sha256']==sha(fx/target.APK) and
         obj['v2_sha256']==obj['target_received_sha256']==
         inv['files']['base_v2.apk']['sha256']==sha(fx/'base_v2.apk'),
         'positive signed fixture/package provenance mismatch')
    need(obj['before']=={'version_code':1,'base_sha256':sha(fx/'base_v1.apk'),'split_count':0} and
         obj['after']=={'version_code':2,'base_sha256':sha(fx/'base_v2.apk'),'split_count':0},
         'independently verified before/after installed bytes missing')
    need(obj['system_approval_taps']==1 and obj['external_mode']=='production_native_intent' and
         all(obj[k] is True for k in ('android_install_status_verified','signed_bytes_verified',
                                      'dart_handoff_not_success')) and
         all(obj[k] is False for k in ('physical_device_qualified','shizuku_qualified',
                                       'dhizuku_qualified','release_qualified','raw_logs_uploaded')),
         'system approval/package evidence missing or false qualification')
    need(obj['flutter_log_sha256']==sha(out/'r02f-p04b-p02-private.log'),
         'private Flutter runtime log SHA changed')
    print('OX_P04B_P02_POSITIVE_RECEIPT_INDEPENDENT_OFFLINE_VERIFY_PASS',flush=True)
    return 0

def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['run','verify']);
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    try:return run(a.out) if a.command=='run' else verify(a.out)
    except (OSError,ValueError,KeyError,TypeError,Refused,base.Refused,subprocess.TimeoutExpired) as e:
        print('OX_P04B_P02_REFUSED '+str(e),file=sys.stderr,flush=True);return 2
if __name__=='__main__':raise SystemExit(main())
