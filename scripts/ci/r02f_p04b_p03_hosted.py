#!/usr/bin/env python3
"""P04B P03: hosted API36 adversarial third-party handoff acceptance.

This exercises real native MethodChannel and signed disposable APKs. It NEVER
interprets a package signal as a verified installation; no privileged install,
root, physical-device write, raw UI XML or Flutter log artifact is permitted.
"""
from __future__ import annotations
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET

import r02_rt02_hosted as base
import r02_rt02c_hosted as rt02c
import r02f_p04b_p03_target as target

RECEIPT='r02f-p04b-p03-adversarial.json'
DIAGNOSTIC='r02f-p04b-p03-diagnostics.json'
STATUS='PASS_HOSTED_ADVERSARIAL_HANDOFFS_SIGNED_V1_UNCHANGED'
PORT=18785
PKG='dev.bikram.obtainx.rt02.fixture'
MARKERS=(
    'OX_P04B_P03_PARALLEL_HANDOFF_REFUSED_PASS',
    'OX_P04B_P03_SPOOF_ACTION_UNTRUSTED_PASS',
    'OX_P04B_P03_DELAYED_SIGNAL_UNVERIFIED_PASS',
    'OX_P04B_P03_MISMATCHED_PACKAGE_NO_FALSE_SUCCESS_PASS',
)
PROBE_ACTION='dev.bikram.obtainx.P04B_P03_UNTRUSTED_FAKE_CHANGE'

class Refused(RuntimeError):pass

def need(condition,reason):
    if not condition:raise Refused(reason)

def sha(path:Path):return hashlib.sha256(path.read_bytes()).hexdigest()

class ProbeHandler(BaseHTTPRequestHandler):
    signed_v2:Path
    counts={'spoof':0,'late':0}
    counts_lock=threading.Lock()
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path=='/base_v2.apk':
            raw=self.signed_v2.read_bytes()
            if not 300<len(raw)<16*1024*1024:self.send_error(422);return
            self.send_response(200)
            self.send_header('Content-Type','application/vnd.android.package-archive')
            self.send_header('Content-Length',str(len(raw)))
            self.end_headers();self.wfile.write(raw)
            return
        label=self.path.removeprefix('/p03/')
        if self.path not in ('/p03/spoof','/p03/late'):
            self.send_error(404);return
        with self.counts_lock:
            if self.counts[label]!=0:
                self.send_error(409);return
            # Never spoof ACTION_PACKAGE_REPLACED. Android protects it. Instead
            # send a custom, explicitly untrusted event carrying the same URI.
            try:
                base.adb('shell','am','broadcast','-a',PROBE_ACTION,
                         '-d','package:'+PKG,timeout=25)
            except (OSError,subprocess.TimeoutExpired,base.Refused):
                self.send_error(503);return
            self.counts[label]+=1
        self.send_response(200)
        self.send_header('Content-Type','text/plain')
        self.end_headers();self.wfile.write(b'untrusted_broadcast_sent')

def private_target_receipt():
    raw=base.adb('shell','run-as',target.PACKAGE,'cat','shared_prefs/p04b.xml',timeout=25)
    need(raw.startswith('<?xml') and len(raw)<4096,'target private receipt absent/unbounded')
    root=ET.fromstring(raw)
    need(root.tag=='map','target receipt malformed')
    result={x.attrib.get('name'):x.text for x in root if x.tag=='string'}
    need(set(result)=={'status','sha256'},'target receipt unexpected fields')
    return result

def _source_bound(out:Path,source:str):
    need(out.is_absolute() and out.is_dir() and not out.is_symlink(),
         'hosted evidence root must be real and absolute')
    fx=out/'fixtures';f3=fx/'p04b_p03'
    need(f3.is_dir() and not f3.is_symlink(),'P03 fixture directory missing')
    inv=json.loads((fx/'fixture_inventory.json').read_text())
    target_inventory=json.loads((f3/'p04b_target_inventory.json').read_text())
    need(inv['source_sha']==source and target_inventory['source_sha']==source,
         'P03 signed fixture/source identities mismatch')
    need(target_inventory['package']==target.PACKAGE and
         target_inventory['activity']==target.ACTIVITY and
         target_inventory['signed_disposable_target'] is True and
         target_inventory['only_reads_content_uri'] is True and
         target_inventory['can_install_apks'] is False,
         'P03 delayed fixture unsafe or wrong target')
    for name in ('base_v1.apk','base_v2.apk'):
        need(sha(fx/name)==inv['files'][name]['sha256'],
             'source-bound signed APK bytes changed: '+name)
    need(sha(f3/target.APK)==target_inventory['sha256'],
         'signed delayed-decline target bytes changed')
    return fx,f3,inv,target_inventory

def refuse(out:Path,source:str,runid:str,stage:str,reason:str,log:Path,elapsed:float):
    stages={'PRECHECK','SIGNED_BASELINE','START_FLUTTER','WAIT_FLUTTER',
            'CHECK_TARGET','CHECK_V1','WRITE_RECEIPT'}
    reasons={'TIMEOUT','FLUTTER_FAILURE','ANDROID_NEGATIVE_FAILURE',
             'SIGNED_BYTES_MISMATCH','OTHER'}
    data={'schema':1,'status':'REFUSED_NOT_QUALIFIED','source_sha':source,
          'run_id':runid,'stage':stage if stage in stages else 'PRECHECK',
          'reason':reason if reason in reasons else 'OTHER',
          'elapsed_seconds':min(3600,max(0,int(elapsed))),
          'private_log_sha256':sha(log) if log.is_file() else None,
          'android_p03_qualified':False,'physical_device_qualified':False,
          'release_qualified':False,'raw_logs_uploaded':False}
    (out/DIAGNOSTIC).write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')
    print('OX_P04B_P03_DIAGNOSTIC_REFUSAL stage='+data['stage']+' reason='+data['reason'],flush=True)

def run(out:Path):
    source,runid=base.host_check()
    started=time.monotonic();stage='PRECHECK';log=out/'r02f-p04b-p03-private.log'
    server=None;process=None
    try:
        fx,f3,inv,tv=_source_bound(out,source)
        receipt=out/RECEIPT
        need(not receipt.exists() and not receipt.is_symlink(), 'stale P03 result refused')
        ProbeHandler.signed_v2=fx/'base_v2.apk'
        ProbeHandler.counts={'spoof':0,'late':0}
        stage='SIGNED_BASELINE'
        base.adb('install','-r','-t',str(f3/target.APK),timeout=90)
        base.adb('install','-r','-t',str(fx/'base_v1.apk'),timeout=90)
        before=rt02c.baseline_v1(fx)
        stage='START_FLUTTER'
        server=ThreadingHTTPServer(('127.0.0.1',PORT),ProbeHandler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base.adb('reverse',f'tcp:{PORT}',f'tcp:{PORT}')
        argv=['flutter','test','integration_test/r02f_p04b_p03_adversarial_test.dart',
              '-d',base.SERIAL,'--flavor','normal','--no-pub','--reporter','expanded',
              '--dart-define=OX_P04B_P03_BASE_SHA='+inv['files']['base_v2.apk']['sha256']]
        stage='WAIT_FLUTTER'
        with log.open('wb') as output:
            process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,
                                     stdout=output,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+360
            next_report=0
            while process.poll() is None and time.monotonic()<deadline:
                elapsed=int(time.monotonic()-started)
                if elapsed>=next_report:
                    print('OX_P04B_P03_PROGRESS elapsed='+str(elapsed)+'s '
                          'custom_probes='+str(sum(ProbeHandler.counts.values())),flush=True)
                    next_report=elapsed+25
                time.sleep(2)
            if process.poll() is None:
                process.kill();process.wait(timeout=12)
                raise Refused('P03 Flutter adversarial runtime timed out')
        private=log.read_text('utf8','replace')
        need(process.returncode==0 and 'All tests passed!' in private,
             'P03 Flutter adversarial test failed; private log retained')
        need(all(private.count(marker)==1 for marker in MARKERS),
             'P03 Flutter four adversarial markers absent/duplicated')
        need(ProbeHandler.counts=={'spoof':1,'late':1},
             'P03 hosted custom broadcast count mismatch')
        stage='CHECK_TARGET'
        target_receipt=private_target_receipt()
        need(target_receipt=={'status':'received_and_declined',
                             'sha256':inv['files']['base_v2.apk']['sha256']},
             'P03 signed delayed target did not decline exact APK')
        stage='CHECK_V1'
        after=rt02c.baseline_v1(fx)
        need(before==after,'P03 negative adversarial path changed installed v1 signed bytes')
        need(after['version_code']==1 and after['installed_original_intact'] is True,
             'mismatched expected v2 was promoted despite signed installed v1')
        print('OX_P04B_P03_WRONG_VERSION_REAL_SIGNED_V1_RETAINED_PASS',flush=True)
        stage='WRITE_RECEIPT'
        data={'schema':1,'status':STATUS,'source_sha':source,'run_id':runid,
              'signed_target_sha256':tv['sha256'],
              'received_v2_sha256':target_receipt['sha256'],
              'v2_sha256':inv['files']['base_v2.apk']['sha256'],
              'before':before,'after':after,'spoof_custom_broadcasts':1,
              'late_custom_broadcasts':1,'parallel_handoffs_refused':1,
              'mismatched_expected_package_unverified':True,
              'signed_v1_unchanged':True,
              'private_flutter_log_sha256':sha(log),
              'untrusted_broadcast_not_install_proof':True,
              'positive_install_qualified_by_p03':False,
              'physical_device_qualified':False,'shizuku_qualified':False,
              'dhizuku_qualified':False,'release_qualified':False,
              'raw_logs_uploaded':False}
        receipt.write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')
        print('OX_P04B_P03_REAL_FOUR_ADVERSARIAL_HANDOFFS_V1_INTACT_PASS',flush=True)
        return 0
    except (OSError,ValueError,TypeError,KeyError,Refused,base.Refused,
            rt02c.Refused,subprocess.TimeoutExpired,ET.ParseError) as exc:
        msg=str(exc).lower()
        reason=('TIMEOUT' if 'timed out' in msg else
                'SIGNED_BYTES_MISMATCH' if 'signed' in msg or 'sha' in msg else
                'FLUTTER_FAILURE' if 'flutter' in msg else
                'ANDROID_NEGATIVE_FAILURE' if 'p03' in msg or 'android' in msg else 'OTHER')
        if out.is_dir() and out.is_absolute() and not out.is_symlink():
            refuse(out,source,runid,stage,reason,log,time.monotonic()-started)
        raise
    finally:
        if process is not None and process.poll() is None:process.kill();process.wait(timeout=12)
        if server is not None:server.shutdown();server.server_close()
        base.adb('reverse','--remove',f'tcp:{PORT}',allow_failure=True)
        base.adb('shell','pm','uninstall',target.PACKAGE,allow_failure=True)
        base.adb('shell','pm','uninstall',PKG,allow_failure=True)

def verify(out:Path):
    source,runid=base.identity_check()
    receipt=out/RECEIPT
    need(out.is_absolute() and receipt.is_file() and not receipt.is_symlink() and
         200<receipt.stat().st_size<8192, 'P03 offline receipt absent, linked or oversized')
    obj=json.loads(receipt.read_text())
    expected={'schema','status','source_sha','run_id','signed_target_sha256',
              'received_v2_sha256','v2_sha256','before','after','spoof_custom_broadcasts',
              'late_custom_broadcasts','parallel_handoffs_refused',
              'mismatched_expected_package_unverified','signed_v1_unchanged',
              'private_flutter_log_sha256','untrusted_broadcast_not_install_proof',
              'positive_install_qualified_by_p03','physical_device_qualified',
              'shizuku_qualified','dhizuku_qualified','release_qualified',
              'raw_logs_uploaded'}
    need(set(obj)==expected and type(obj['schema']) is int and obj['schema']==1 and
         obj['status']==STATUS and obj['source_sha']==source and
         str(obj['run_id'])==str(runid), 'P03 offline source/receipt schema drift')
    fx,f3,inv,tv=_source_bound(out,source)
    baseline={'version_code':1,'installed_path_count':1,
              'base_sha256':sha(fx/'base_v1.apk'),
              'installed_original_intact':True}
    need(obj['before']==baseline and obj['after']==baseline,
         'P03 signed v1 Android before/after mismatch')
    need(obj['signed_target_sha256']==tv['sha256']==sha(f3/target.APK) and
         obj['received_v2_sha256']==obj['v2_sha256']==
         inv['files']['base_v2.apk']['sha256']==sha(fx/'base_v2.apk'),
         'P03 signed source artifact provenance mismatch')
    need(obj['private_flutter_log_sha256']==sha(out/'r02f-p04b-p03-private.log'),
         'P03 private Flutter log integrity drift')
    for f in ('spoof_custom_broadcasts','late_custom_broadcasts','parallel_handoffs_refused'):
        need(type(obj[f]) is int and obj[f]==1,'P03 negative case count mismatch '+f)
    for f in ('mismatched_expected_package_unverified','signed_v1_unchanged',
              'untrusted_broadcast_not_install_proof'):
        need(obj[f] is True,'P03 negative proof missing '+f)
    for f in ('positive_install_qualified_by_p03','physical_device_qualified',
              'shizuku_qualified','dhizuku_qualified','release_qualified',
              'raw_logs_uploaded'):
        need(obj[f] is False,'P03 false qualification '+f)
    print('OX_P04B_P03_INDEPENDENT_ADVERSARIAL_OFFLINE_VERIFY_PASS',flush=True)
    return 0

def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=['run','verify'])
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    try:return run(a.out) if a.action=='run' else verify(a.out)
    except (OSError,ValueError,TypeError,KeyError,Refused,base.Refused,
            rt02c.Refused,subprocess.TimeoutExpired) as exc:
        print('OX_P04B_P03_REFUSED '+str(exc),file=sys.stderr,flush=True)
        return 2

if __name__=='__main__':raise SystemExit(main())
