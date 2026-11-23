#!/usr/bin/env python3
"""Real hosted API36 external ACTION_VIEW decline, independent signed v1 observation.

Must run inside RT02C's already-provisioned emulator after P03's independent audit.
Raw Flutter stdout and APK/signing materials never leave the ephemeral runner.
"""
from __future__ import annotations
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import xml.etree.ElementTree as ET

import r02_rt02_hosted as base
import r02_rt02c_hosted as rt02c
import r02f_p04b_target as target

RECEIPT='r02f-p04b-external-decline.json'
STATUS='PASS_EXTERNAL_EXPLICIT_ACTIVITY_RECEIVED_AND_DECLINED_APK_V1_INTACT'
MARKER='OX_R02F_P04B_DART_REAL_DECLINE_NO_FALSE_SUCCESS_PASS'
PORT=18783

class Refused(RuntimeError):pass

def need(ok:bool,message:str):
    if not ok:raise Refused(message)

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()

class FixtureHandler(BaseHTTPRequestHandler):
    base_file:Path
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path!='/base_v2.apk':self.send_error(404);return
        data=self.base_file.read_bytes()
        if not 300<len(data)<16*1024*1024:self.send_error(422);return
        self.send_response(200)
        self.send_header('Content-Type','application/vnd.android.package-archive')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers();self.wfile.write(data)

def target_receipt()->dict:
    # This read is allowed only for the disposable target APK, debuggable in CI.
    # No personal app data, root, or PACKAGE_ADDED broadcast injection.
    xml=base.adb('shell','run-as',target.PACKAGE,'cat','shared_prefs/p04b.xml',timeout=20)
    need(len(xml)<4096 and xml.startswith('<?xml'),'bounded external receiver evidence missing')
    node=ET.fromstring(xml)
    need(node.tag=='map','unexpected external receiver evidence schema')
    values={x.attrib.get('name'):x.text for x in node if x.tag=='string'}
    need(set(values)=={'status','sha256'},'unexpected external receiver evidence fields')
    return values

def run(out:Path)->int:
    source,runid=base.host_check()
    need(out.is_absolute() and out.is_dir() and not out.is_symlink(), 'existing absolute evidence directory required')
    fx=out/'fixtures'
    inv=json.loads((fx/'fixture_inventory.json').read_text())
    tv=json.loads((fx/'p04b_target_inventory.json').read_text())
    need(inv.get('source_sha')==source and tv.get('source_sha')==source,'source SHA drift')
    need(tv.get('package')==target.PACKAGE and tv.get('activity')==target.ACTIVITY,
         'unapproved external target')
    need(tv.get('can_install_apks') is False and tv.get('only_reads_content_uri') is True,
         'privileged/mutating target refused')
    need(sha(fx/target.APK)==tv.get('sha256') and
         sha(fx/'base_v2.apk')==inv['files']['base_v2.apk']['sha256'],
         'signed fixture digest mismatch')
    receipt=out/RECEIPT
    need(not receipt.exists(),'stale P04B evidence refused')
    server=None;before=None
    try:
        base.adb('install','-r','-t',str(fx/target.APK),timeout=90)
        base.adb('install','-r','-t',str(fx/'base_v1.apk'),timeout=90)
        before=rt02c.baseline_v1(fx)
        FixtureHandler.base_file=fx/'base_v2.apk'
        server=ThreadingHTTPServer(('127.0.0.1',PORT),FixtureHandler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base.adb('reverse',f'tcp:{PORT}',f'tcp:{PORT}')
        output=out/'r02f-p04b-private.log'
        cmd=['flutter','test','integration_test/r02f_p04b_external_decline_test.dart',
             '-d',base.SERIAL,'--flavor','normal','--no-pub','--reporter','expanded',
             '--dart-define=OX_P04B_BASE_SHA='+inv['files']['base_v2.apk']['sha256']]
        # Keep private output on runner; only a digest is published.
        with output.open('wb') as f:
            p=subprocess.run(cmd,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,timeout=790)
        private=output.read_text('utf-8','replace')
        need(p.returncode==0 and 'All tests passed!' in private and private.count(MARKER)==1,
             'Flutter real external handoff declined/failed; raw log retained privately')
        observed=target_receipt()
        need(observed['status']=='received_and_declined' and
             observed['sha256']==inv['files']['base_v2.apk']['sha256'],
             'external Android target did not receive exact shared signed APK')
        after=rt02c.baseline_v1(fx)
        need(before==after,'external handoff modified installed signed v1 APK bytes')
        data={'schema':1,'status':STATUS,'source_sha':source,'run_id':runid,
              'target_component':target.ACTIVITY,'signed_target_sha256':tv['sha256'],
              'received_v2_sha256':observed['sha256'],'expected_v2_sha256':inv['files']['base_v2.apk']['sha256'],
              'signed_v1_before':before,'signed_v1_after':after,
              'flutter_log_sha256':sha(output),'native_external_activity_invoked':True,
              'external_target_declined_without_install':True,
              'independent_android_v1_checked':True,'external_positive_install_qualified':False,
              'physical_device_qualified':False,'shizuku_qualified':False,
              'dhizuku_qualified':False,'release_qualified':False,'raw_logs_uploaded':False}
        receipt.write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')
        print('OX_R02F_P04B_REAL_EXTERNAL_DECLINE_AND_V1_BYTES_PASS',flush=True)
        return 0
    finally:
        if server is not None:server.shutdown();server.server_close()
        base.adb('reverse','--remove',f'tcp:{PORT}',allow_failure=True)
        base.adb('shell','pm','uninstall',target.PACKAGE,allow_failure=True)
        base.adb('shell','pm','uninstall',base.FIXTURE,allow_failure=True)

def verify(out:Path)->int:
    source,runid=base.identity_check()
    receipt=out/RECEIPT
    need(out.is_absolute() and receipt.is_file() and not receipt.is_symlink()
         and 100<receipt.stat().st_size<=8192,'missing/bounded P04B receipt')
    data=json.loads(receipt.read_text())
    fields={'schema','status','source_sha','run_id','target_component','signed_target_sha256',
            'received_v2_sha256','expected_v2_sha256','signed_v1_before','signed_v1_after',
            'flutter_log_sha256','native_external_activity_invoked',
            'external_target_declined_without_install','independent_android_v1_checked',
            'external_positive_install_qualified','physical_device_qualified',
            'shizuku_qualified','dhizuku_qualified','release_qualified','raw_logs_uploaded'}
    need(set(data)==fields,'P04B receipt schema drift')
    need(data['schema']==1 and data['status']==STATUS and
         data['source_sha']==source and str(data['run_id'])==runid,'P04B status/source/run drift')
    need(data['target_component']==target.ACTIVITY and
         data['signed_v1_before']==data['signed_v1_after'],'P04B target/baseline mismatch')
    fx=out/'fixtures';inv=json.loads((fx/'fixture_inventory.json').read_text())
    tv=json.loads((fx/'p04b_target_inventory.json').read_text())
    need(inv.get('source_sha')==source and tv.get('source_sha')==source,
         'P04B signed fixture inventories not bound to this source')
    need(tv.get('signed_disposable_target') is True and
         tv.get('only_reads_content_uri') is True and tv.get('can_install_apks') is False,
         'P04B target scope widened or fixture inventory untrusted')
    need(data['received_v2_sha256']==data['expected_v2_sha256']==inv['files']['base_v2.apk']['sha256'] and
         data['signed_target_sha256']==tv['sha256'] and
         sha(fx/'base_v2.apk')==data['received_v2_sha256'] and
         sha(fx/target.APK)==data['signed_target_sha256'],
         'P04B artifact provenance mismatch')
    need(data['flutter_log_sha256']==sha(out/'r02f-p04b-private.log'),'P04B private log drift')
    need(all(data[k] is True for k in ('native_external_activity_invoked',
              'external_target_declined_without_install','independent_android_v1_checked')),
         'P04B missing Android evidence')
    need(all(data[k] is False for k in ('external_positive_install_qualified',
             'physical_device_qualified','shizuku_qualified','dhizuku_qualified',
             'release_qualified','raw_logs_uploaded')),'P04B false qualification')
    print('OX_R02F_P04B_INDEPENDENT_SOURCE_BOUND_RECEIPT_PASS',flush=True)
    return 0

def main():
    a=argparse.ArgumentParser();a.add_argument('command',choices=['run','verify']);
    a.add_argument('--out',type=Path,required=True);args=a.parse_args()
    try:return run(args.out) if args.command=='run' else verify(args.out)
    except (OSError,ValueError,KeyError,TypeError,Refused,subprocess.TimeoutExpired,base.Refused,rt02c.Refused) as ex:
        print('OX_R02F_P04B_REFUSED '+str(ex),file=sys.stderr,flush=True);return 2
if __name__=='__main__':raise SystemExit(main())
