#!/usr/bin/env python3
"""P04B P01: exact external decline runtime wiring, evidence, and safety guards.

This source guard is NOT an Android runtime qualification. Real hosted API36
must execute the Flutter bridge/receiver and independently audit signed bytes.
"""
from __future__ import annotations
import argparse
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
TARGET='scripts/ci/r02f_p04b_target.py'
HOST='scripts/ci/r02f_p04b_hosted.py'
DART='integration_test/r02f_p04b_external_decline_test.dart'
WORKFLOW='.github/workflows/obtainx-r02-rt02c.yml'
DOC='docs/R02F_P04B_EXTERNAL_DECLINE.md'
PATHS=(TARGET,HOST,DART,WORKFLOW,DOC)

def inspect(root:Path=ROOT)->list[str]:
    issues=[];docs={}
    for path in PATHS:
        f=root/path
        if not f.is_file() or f.is_symlink():
            issues.append('missing/linked P04B source: '+path);docs[path]=''
        else:docs[path]=f.read_text('utf-8')
    t,h,d,w,doc=(docs[p] for p in PATHS)
    def check(ok,msg):
        if not ok:issues.append(msg)
    for anchor in ('GITHUB_ACTIONS','RUNNER_OS','GITHUB_SHA','keytool',
                   'javac','d8','aapt2','zipalign','apksigner',
                   'signed_disposable_target','only_reads_content_uri',
                   'can_install_apks\':False','SHA-256','received_and_declined',
                   'try (InputStream input = getContentResolver().openInputStream(uri))',
                   'getSharedPreferences("p04b", MODE_PRIVATE)',
                   'new Handler(Looper.getMainLooper()).postDelayed(',
                   '}, 1500L);'):
        # SHA-256 appears inside Java target; never accept a label alone as proof.
        check(anchor in t,'missing protected target anchor '+anchor)
    check('Runtime.getRuntime().exec(' not in t and 'ProcessBuilder(' not in t and
          'session.commit' not in t and 'startActivity(' not in t and 'PackageInstaller' in t,
          'test target gained install privilege or false continuation')
    run_region=h.split('def run(out:Path)',1)[-1].split('def verify(out:Path)',1)[0]
    check("sha(fx/target.APK)==tv.get('sha256')" in run_region,
          'P04B runtime no longer verifies signed APK target before receipt')
    check('observed=target_receipt()' in h and h.count('rt02c.baseline_v1(fx)')==2,
          'P04B bypassed receiver or independent before/after Android observation')
    for anchor in ('target_receipt()','run-as','received_and_declined',
                   'p04b_target_inventory.json','sha(fx/target.APK)',
                   'source_sha','base.adb(\'install\'','rt02c.baseline_v1(fx)',
                   'before==after','str(data[\'run_id\'])==runid',
                   'external_positive_install_qualified\':False',
                   'raw_logs_uploaded\':False',
                   'data[\'flutter_log_sha256\']==sha(out/\'r02f-p04b-private.log\')'):
        check(anchor in h,'P04B independent Android proof missing '+anchor)
    for anchor in ('installApkViaThirdParty(', 'targetPackage: _targetPackage',
                   'targetActivity: _targetActivity', 'expectedPackageName: _package',
                   'classifyUnverifiedThirdPartyHandoff(bridge)',
                   'expect(result.isSuccess, isFalse)',
                   'expect(bridge, isFalse',
                   'sha256.convert(bytes).toString() != _expectedSha',
                   'OX_R02F_P04B_DART_REAL_DECLINE_NO_FALSE_SUCCESS_PASS'):
        check(anchor in d,'P04B production bridge/UI negative omitted '+anchor)
    check('StockInstaller' not in d and 'install-abandon' not in d,
          'P04B external test substituted stock or host-abandon path')
    for anchor in ("      - 'scripts/ci/r02f_p04b_*'",
                   'python3 -B scripts/ci/r02f_p04b_target.py --out',
                   'python3 -B scripts/ci/r02f_p04b_hosted.py run --out',
                   'python3 -B scripts/ci/r02f_p04b_hosted.py verify --out',
                   'r02f-p04b-external-decline.json'):
        check(anchor in w,'P04B GitHub Actions runtime/evidence missing '+anchor)
    check(w.count('scripts/ci/r02f_p04b_hosted.py run --out')==1 and
          w.count('scripts/ci/r02f_p04b_hosted.py verify --out')==1,
          'P04B runtime must execute once inside same emulator and verify once outside')
    check(w.index('scripts/ci/r02f_p03_hosted.py audit --out') <
          w.index('scripts/ci/r02f_p04b_hosted.py run --out'),
          'P03 independent baseline audit must precede P04B test') if (
          'scripts/ci/r02f_p03_hosted.py audit --out' in w and
          'scripts/ci/r02f_p04b_hosted.py run --out' in w) else None
    check('**NOT_QUALIFIED** for positive' in doc,
          'P04B positive installer acceptance falsely marked qualified')
    for anchor in ('NOT_QUALIFIED','decline','positive','Shizuku','Dhizuku','physical'):
        check(anchor in doc,'P04B qualification limit missing '+anchor)
    return issues

def main():
    a=argparse.ArgumentParser();a.add_argument('--check',action='store_true');a.parse_args()
    issues=inspect()
    for x in issues:print('OX_R02F_P04B_SOURCE_REFUSED '+x)
    if issues:return 1
    print('OX_R02F_P04B_SOURCE_CONTRACT_PASS RUNTIME=NOT_PERFORMED',flush=True)
    return 0
if __name__=='__main__':raise SystemExit(main())
