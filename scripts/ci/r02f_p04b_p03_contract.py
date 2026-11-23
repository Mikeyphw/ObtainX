#!/usr/bin/env python3
"""P04B P03 fail-closed source contract for four hosted Android negatives."""
from __future__ import annotations
import argparse
import ast
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
MAIN='android/app/src/main/kotlin/dev/imranr/obtainium/MainActivity.kt'
TARGET='scripts/ci/r02f_p04b_p03_target.py'
HOST='scripts/ci/r02f_p04b_p03_hosted.py'
DART='integration_test/r02f_p04b_p03_adversarial_test.dart'
DOC='docs/R02F_P04B_P03_ADVERSARIAL.md'
WORKFLOW='.github/workflows/obtainx-r02-rt02c.yml'
SOURCE='.github/workflows/obtainx-r00-contracts.yml'
PATHS=(MAIN,TARGET,HOST,DART,DOC,WORKFLOW,SOURCE)

def inspect(root:Path=ROOT)->list[str]:
    errors=[];contents={}
    for path in PATHS:
        p=root/path
        if not p.is_file() or p.is_symlink():
            errors.append('missing, linked source '+path);contents[path]=''
        else: contents[path]=p.read_text('utf8')
    k,t,h,d,doc,w,source=(contents[p] for p in PATHS)
    def check(condition:bool,reason:str):
        if not condition:errors.append(reason)
    for path in (TARGET,HOST):
        try:ast.parse(contents[path],filename=path)
        except SyntaxError:errors.append('P03 invalid Python '+path)
    # The production method channel must refuse the second owner before any
    # unique cache file is allocated, and never replace a live InstallWatcher.
    start=k.find('private fun launchInstallIntent(')
    end=k.find('private fun releaseFileToContentUri(',start)
    block=k[start:end] if start>=0 and end>start else ''
    guard=(
        'val activeExternalWatcher = installWatcher\n'
        '        if (activeExternalWatcher != null && !activeExternalWatcher.responded) {\n'
        '            methodResult.error("INSTALL_IN_PROGRESS", "An external install handoff is already active", null)\n'
        '            return\n'
        '        }'
    )
    check(block.count(guard)==1 and 'val releaseFiles = sourceFiles.map' in block and
          block.index(guard)<block.index('val releaseFiles = sourceFiles.map')
          if guard in block and 'val releaseFiles = sourceFiles.map' in block else False,
          'parallel tracked handoff guard missing or placed after cache allocation')
    check('if (session.receiver !== this) return' in block and
          'if (installWatcher === session && !session.responded)' in block and
          'if (installWatcher !== sessionWatcher || sessionWatcher.responded)' in block,
          'native delayed callback could escape watcher identity/fence')
    action_guard=('if (broadcastIntent.action != Intent.ACTION_PACKAGE_ADDED &&\n'
                  '                    broadcastIntent.action != Intent.ACTION_PACKAGE_REPLACED) return')
    check(action_guard in block and
          'if (broadcastIntent.data?.scheme != "package") return' in block,
          'native watcher action/scheme filter removed')
    # Reuse P01's signed, non-installing fixture: only a longer foreground delay
    # differs. A test target with install capabilities would invalidate P03.
    for x in ('import r02f_p04b_target as delegate',
              "APK='p04b-p03-delayed-decline.apk'", "OLD='}, 1500L);'",
              "NEW='}, 12000L);'", 'delegate.JAVA=original_java.replace(OLD,NEW,1)',
              'delegate.build(out)','delegate.APK=original_apk'):
        check(x in t,'P03 signed delayed target builder weakened: '+x)
    check('import android.content.pm.PackageInstaller' not in t and
          'subprocess.run' not in t,
          'P03 standalone fixture gained installer/privileged subprocess code')
    # Test must actually invoke the production plugin, not a simulated API.
    for x in ('installApkViaThirdParty(',"expect(refusal,'INSTALL_IN_PROGRESS'",
              "await _probe('spoof')", "await _probe('late')",
              'expectedPackageName:\'$_fixture.mismatched\'',
              'classifyUnverifiedThirdPartyHandoff(observed)',
              'expect(verdict.isSuccess,isFalse)', 'expect(wrongPackage,isFalse)',
              "sha256.convert(bytes).toString()!=_sha"):
        check(x in d,'P03 live Dart negative assertion missing: '+x)
    for marker in ('PARALLEL_HANDOFF_REFUSED_PASS','SPOOF_ACTION_UNTRUSTED_PASS',
                   'DELAYED_SIGNAL_UNVERIFIED_PASS','MISMATCHED_PACKAGE_NO_FALSE_SUCCESS_PASS'):
        check(d.count('OX_P04B_P03_'+marker)==1,
              'P03 Flutter test success marker missing/duplicated '+marker)
    check('StockInstaller(' not in d and 'adb' not in d and 'pm install' not in d,
          'P03 Dart must use production third-party bridge')
    for x in ('base.host_check()', 'base.identity_check()',
              'rt02c.baseline_v1(fx)', "before==after",
              "'status':'received_and_declined'",'signed_v1_unchanged',
              "'positive_install_qualified_by_p03':False", 'raw_logs_uploaded',
              "obj['private_flutter_log_sha256']==sha(out/'r02f-p04b-p03-private.log')",
              'sha(f3/target.APK)', 'ProbeHandler.counts',
              'OX_P04B_P03_REAL_FOUR_ADVERSARIAL_HANDOFFS_V1_INTACT_PASS',
              "'untrusted_broadcast_not_install_proof':True",
              "inv['files']['base_v2.apk']['sha256']==sha(fx/'base_v2.apk')"):
        check(x in h,'P03 independent Android negative/receipt proof missing: '+x)
    check('android.intent.action.PACKAGE_REPLACED' not in h and
          "PROBE_ACTION='dev.bikram.obtainx.P04B_P03_UNTRUSTED_FAKE_CHANGE'" in h,
          'P03 must not spoof privileged Android package-change action')
    ver=h.split('def verify(',1)[-1]
    check('base.adb(' not in ver and 'return True' not in ver,
          'P03 offline verifier must not perform Android writes or be vacuous')
    for x in ('python3 -B scripts/ci/r02f_p04b_p03_target.py --out',
              'python3 -B scripts/ci/r02f_p04b_p03_hosted.py run --out',
              'python3 -B scripts/ci/r02f_p04b_p03_hosted.py verify --out',
              'r02f-p04b-p03-adversarial.json',
              'r02f-p04b-p03-diagnostics.json',
              'fixtures/p04b_p03/p04b_target_inventory.json'):
        check(x in w,'P03 required hosted compile/run/verify/evidence missing: '+x)
    check(w.count('scripts/ci/r02f_p04b_p03_hosted.py run --out')==1 and
          w.count('scripts/ci/r02f_p04b_p03_hosted.py verify --out')==1 and
          w.index('scripts/ci/r02f_p04b_p02_hosted.py run --out') <
          w.index('scripts/ci/r02f_p04b_p03_hosted.py run --out'),
          'P02 Android positive acceptance must precede P03 adversarial negative test')
    check('run: python3 -B scripts/ci/r02f_p04b_p03_contract.py --check' in source,
          'P03 source contract must run in R00')
    check('**NOT_QUALIFIED until the P03 source tests and all six exact-HEAD hosted workflows pass.**' in doc and
          'physical' in doc and 'Shizuku' in doc and 'Dhizuku' in doc and
          'R03' in doc and 'R12' in doc,
          'P03 scope / remaining roadmap disclosure removed')
    return errors

def main():
    argparse.ArgumentParser(description=__doc__).add_argument('--check',action='store_true')
    issues=inspect()
    for issue in issues: print('OX_P04B_P03_SOURCE_REFUSED '+issue,file=sys.stderr)
    if issues:return 2
    print('OX_P04B_P03_SOURCE_CONTRACT_PASS; HOSTED_ANDROID_NOT_PERFORMED',flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
