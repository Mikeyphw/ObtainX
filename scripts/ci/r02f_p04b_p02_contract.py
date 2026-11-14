#!/usr/bin/env python3
"""P04B P02 positive external target, hosted runtime and receipt safety contract."""
from __future__ import annotations
import argparse,ast,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
TARGET='scripts/ci/r02f_p04b_p02_target.py'
HOST='scripts/ci/r02f_p04b_p02_hosted.py'
DART='integration_test/r02f_p04b_p02_external_positive_test.dart'
DOC='docs/R02F_P04B_P02_EXTERNAL_POSITIVE.md'
RUNTIME='.github/workflows/obtainx-r02-rt02c.yml'
SOURCE='.github/workflows/obtainx-r00-contracts.yml'
PATHS=(TARGET,HOST,DART,DOC,RUNTIME,SOURCE)

def inspect(root:Path=ROOT)->list[str]:
    problems=[];data={}
    for path in PATHS:
        f=root/path
        if not f.is_file() or f.is_symlink():problems.append('missing or symlinked '+path);data[path]=''
        else:data[path]=f.read_text('utf8')
    t,h,d,doc,w,ci=(data[x] for x in PATHS)
    for x in (TARGET,HOST):
        try:ast.parse(data[x],filename=x)
        except SyntaxError:problems.append('invalid Python '+x)
    def check(ok,reason):
        if not ok:problems.append(reason)
    for s in ('GITHUB_ACTIONS','RUNNER_OS','GITHUB_SHA','android-36','35.0.0',
              'REQUEST_INSTALL_PACKAGES','USER_ACTION_REQUIRED','PackageInstaller.SessionParams.MODE_FULL_INSTALL',
              'session.openWrite("base.apk",0L,-1L)','session.fsync(output)',
              'session.commit(pending.getIntentSender())','PendingIntent.FLAG_MUTABLE',
              'PackageInstaller.STATUS_PENDING_USER_ACTION','PackageInstaller.STATUS_SUCCESS',
              'Installer.abandonSession', 'only_disposable_fixture_install',
              'signed_disposable_target','requires_system_user_approval'):
        if s=='Installer.abandonSession':continue
        check(s in t,'positive target missing '+s)
    check('installer.abandonSession(id)' in t,'session cleanup on failure missing')
    check('Runtime.getRuntime().exec(' not in t and 'ProcessBuilder(' not in t and
          'pm install' not in t and 'su -c' not in t,
          'positive target attempted privileged shell path')
    check(t.count('session.commit(pending.getIntentSender())')==1 and
          t.count('session.openWrite("base.apk",0L,-1L)')==1,
          'positive installer sessions duplicated or redirected')
    for s in ('installApkViaThirdParty(', 'expectedPackageName: _fixture',
              'targetPackage: _target','targetActivity: _component',
              'classifyUnverifiedThirdPartyHandoff(bridge)',
              'expect(result.isHandedOff, isTrue)', 'expect(result.isSuccess, isFalse)',
              'sha256.convert(bytes).toString() != _sha','real Android'):
        check(s in d,'production Dart external positive handoff missing '+s)
    check('StockInstaller(' not in d and 'adb' not in d and 'shell' not in d,
          'positive test bypassed production native external bridge')
    for s in ('base.adb(\'shell\',\'appops\',\'set\',target.PACKAGE',
              'approve_if_verified()', 'uiautomator','com.google.android.packageinstaller',
              'com.google.android.permissioncontroller','package_observation(fx,1)',
              'package_observation(fx,2)','target_observation()',
              "observed.get('status') in",'approvals==1',
              "'status':'system_status_success'",'signed_bytes_verified',
              'sha(fx/target.APK)','sha(fx/\'base_v2.apk\')',
              "obj['flutter_log_sha256']==sha(out/'r02f-p04b-p02-private.log')",
              'base.identity_check()', 'base.host_check()',
              'raw_logs_uploaded\':False'):
        check(s in h,'real positive Android observation/gate missing '+s)
    for s in ("obj['target_sha256']", "obj['after']=={'version_code':2", 'obj[\'system_approval_taps\']==1'):
        check(s in h,'positive independent verifier missing '+s)
    check('return True' not in h[h.index('def verify('):] and
          'base.adb(' not in h[h.index('def verify('):],
          'post-emulator verifier must be offline and fail closed')
    checks=(
        'python3 -B scripts/ci/r02f_p04b_p02_target.py --out',
        'python3 -B scripts/ci/r02f_p04b_p02_hosted.py run --out',
        'python3 -B scripts/ci/r02f_p04b_p02_hosted.py verify --out',
        'r02f-p04b-p02-positive.json',
    )
    for s in checks:check(s in w,'P04B positive hosted workflow missing '+s)
    check(w.count('scripts/ci/r02f_p04b_p02_hosted.py run --out')==1 and
          w.count('scripts/ci/r02f_p04b_p02_hosted.py verify --out')==1,
          'positive hosted run/verify must execute once')
    if 'scripts/ci/r02f_p04b_hosted.py verify --out' in w and 'scripts/ci/r02f_p04b_p02_hosted.py run --out' in w:
        check(w.index('scripts/ci/r02f_p04b_hosted.py verify --out') < w.index('scripts/ci/r02f_p04b_p02_hosted.py verify --out'),
              'prior decline verification must be retained and precede positive verification')
    check('run: python3 -B scripts/ci/r02f_p04b_p02_contract.py --check' in ci,
          'P04B P02 source contract missing from mandatory CI')
    check('NOT_QUALIFIED' in doc and 'P04B P03' in doc and 'Shizuku' in doc and
          'Dhizuku' in doc and 'physical' in doc,'scope disclosure missing')
    return problems

def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');p.parse_args()
    issues=inspect()
    for i in issues:print('OX_P04B_P02_SOURCE_REFUSED '+i)
    if issues:return 2
    print('OX_P04B_P02_SOURCE_CONTRACT_PASS; REAL_ANDROID_RUNTIME_NOT_PERFORMED',flush=True)
    return 0
if __name__=='__main__':raise SystemExit(main())
