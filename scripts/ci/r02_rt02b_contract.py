#!/usr/bin/env python3
"""RT02B negative Android acceptance source contract; never runtime qualification."""
from __future__ import annotations
import argparse
import ast
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
R00='scripts/ci/r00_source_contract.py'
R00_TEST='scripts/ci/test_r00_source_contract.py'
INHERITED='.github/workflows/obtainx-r00-contracts.yml'
WORKFLOW='.github/workflows/obtainx-r02-rt02b.yml'
HOST='scripts/ci/r02_rt02b_hosted.py'
FIXTURE='scripts/ci/r02_rt02b_fixture.py'
TEST='scripts/ci/test_r02_rt02b_contract.py'
DART='integration_test/r02b_rejection_test.dart'
DOC='docs/R02_RT02B_REJECTION_ACCEPTANCE.md'
BASEHOST='scripts/ci/r02_rt02_hosted.py'
BASEFIX='scripts/ci/r02_rt02_fixture.py'
PATHS=(R00,R00_TEST,INHERITED,WORKFLOW,HOST,FIXTURE,TEST,DART,DOC,BASEHOST,BASEFIX)


def inspect(root:Path=ROOT)->list[str]:
    errors=[];docs={}
    for rel in PATHS:
        p=root/rel
        if not p.is_file():
            errors.append('missing source '+rel);docs[rel]=''
        else: docs[rel]=p.read_text('utf8')
    w=docs[WORKFLOW];h=docs[HOST];f=docs[FIXTURE];d=docs[DART]
    must={
        R00:("'obtainx-r02-rt02b.yml'", 'unexpected = names - EXPECTED_WORKFLOWS',
             'missing = EXPECTED_WORKFLOWS - names'),
        R00_TEST:("'obtainx-r02-rt02b.yml'",'test_reviewed_rt02_required_and_release_is_still_prohibited'),
        INHERITED:('python3 scripts/ci/r02_rt02b_contract.py --check',),
        WORKFLOW:('permissions:\n  contents: read','persist-credentials: false',
                  'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"',
                  'flutter analyze integration_test lib test',
                  'python3 -B scripts/ci/r02_rt02_fixture.py --out',
                  'python3 -B scripts/ci/r02_rt02b_fixture.py --out',
                  'python3 -B scripts/ci/r02_rt02b_hosted.py run --out',
                  'python3 -B scripts/ci/r02_rt02b_hosted.py verify --out',
                  'ReactiveCircus/android-emulator-runner@a421e43855164a8197daf9d8d40fe71c6996bb0d',
                  "'system-images;android-36;google_apis;x86_64'",'api-level: 36',
                  'target: google_apis','arch: x86_64','test -c /dev/kvm',
                  'rt02b-receipt.json','rt02b-progress.json','rt02b_inventory.json',
                  'if: always()',
                  'actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02'),
        FIXTURE:("WRONG = 'wrong_signer_v3.apk'",'secrets.token_hex',
                 "'keytool','-genkeypair'", "str(signer),'sign'",'orig_cert!=wrong_cert',
                 'key.unlink(missing_ok=True)',"'release_qualified':False",
                 "previous['files'].items()", "'source_sha':sha"),
        DART:('IntegrationTestWidgetsFlutterBinding.ensureInitialized()',
              'for (final testCase in negativeCases)',
              'OX_R02B_WRONG_SHA256', 'OX_R02B_DOWNGRADE_SHA256',
              'StockInstaller(SettingsProvider()).installApk(',
              'resolveInstallBundlePlan(', 'sha256.convert(bytes).toString()!=fixtureDigest',
              'expect(result.isError,isTrue',
              'await awaitHostAck(testCase)',
              'OX_R02B_EVENT=$testCase:REJECTED',
              'OX_R02B_EVENT=$testCase:ACKED',
              'OX_R02_RT02_DART_STAGE=INSTALL_CALL',
              'OX_R02_RT02_DART_STAGE=INSTALL_RETURNED'),
        HOST:("CASES=('signature_mismatch','downgrade')",'baseline_unchanged(fixtures)',
              'base.adb(\'install\',\'-t\'',
              'base._tap_confirmed_install_dialog()',
              "'STOCK_INSTALLER_CALL'", 'stock_installer_error_observed',
              "'status':'NOT_RUN'", "'PASS_TWO_REAL_ANDROID_REJECTIONS'",
              "'physical_device_qualified':False", "'full_r02_matrix_qualified':False",
              "'release_qualified':False", "'publication_allowed':False",
              'bounded Flutter negative-test timeout',"d['status']='FAILED'",'rt02b-progress.json',
              'EVENTS=tuple((case,step) for case in CASES',
              "for step in ('START','INSTALL_CALL','REJECTED','ACKED')",
              'state.acks[pending].set()',
              'proof=baseline_unchanged(fixtures)',
              "'flutter_launches':1", "'host_acknowledgement_order':list(CASES)",
              'session_log_sha256', 'events_from_log(log)',
              'start_new_session=True'),
        DOC:('NOT full R02', 'Production StockInstaller','No merges','No releases',
             'source-pinned', 'wrong certificate', 'downgrade'),
        BASEHOST:("APP='dev.bikram.obtainx.debug'",'def installed_state(',
                  'def _tap_confirmed_install_dialog('),
        BASEFIX:("PKG = 'dev.bikram.obtainx.rt02.fixture'",'key.unlink(missing_ok=True)'),
        TEST:('test_valid_source', 'test_no_downgrade_case_rejected',
              'test_missing_wrong_certificate_rejected',
              'test_runtime_receipt_missing_case_refused'),
    }
    for path,needles in must.items():
        for needle in needles:
            if needle not in docs[path]: errors.append(path+': missing protected requirement '+needle)
    if w.count('python3 -B scripts/ci/r02_rt02b_fixture.py --out')!=1:
        errors.append('RT02B wrong signing key must be generated once')
    if w.count('python3 -B scripts/ci/r02_rt02_fixture.py --out')!=1:
        errors.append('RT02B baseline fixture must be generated once')
    if 'script: bash -c' not in w or 'rt02b_hosted.py run --out "$RUNNER_TEMP/obtainx-rt02b"' not in w:
        errors.append('Android harness not invoked on disposable emulator')
    if re.search(r'(?m)^\s*(?:contents|pull-requests|actions|id-token):\s*write\s*$',w):
        errors.append('RT02B GitHub write permission forbidden')
    if re.search(r'(?i)gh\s+release\s+create|flutter\s+build\s+apk.*--release',w):
        errors.append('RT02B workflow cannot publish release')
    if 'setMockMethodCallHandler' in d or 'mockito' in d:
        errors.append('RT02B real StockInstaller may not be mocked')
    # Admission flags must be false both in the initial receipt and in the
    # independent verifier, not just present somewhere in the source.
    for field in ('physical_device_qualified','full_r02_matrix_qualified',
                  'release_qualified','publication_allowed'):
        token="'"+field+"':False"
        if h.count(token)!=2 or "'"+field+"':True" in h:
            errors.append('RT02B unsafe admission flag: '+field)
    if "need('2' in versions and '3' not in versions and '1' not in versions" not in h:
        errors.append('Android version unchanged proof missing')
    if "digest[0]==expected" not in h or "len(paths)==1" not in h:
        errors.append('Android installed bytes unchanged proof missing')
    if 'orig_cert!=wrong_cert' not in f or "extra['original_cert_sha256']!=extra['wrong_cert_sha256']" not in h:
        errors.append('cert mismatch evidence missing')
    if ("EVENTS=tuple((case,step) for case in CASES" not in h or
            "for step in ('START','INSTALL_CALL','REJECTED','ACKED')" not in h or
            'proof=baseline_unchanged(fixtures)' not in h or
            'state.acks[pending].set()' not in h):
        errors.append('both independent negative device checks and host barrier required')
    if "if installed and phase=='STOCK_INSTALLER_CALL' and taps[pending]==0" not in h:
        errors.append('unbounded or pre-Dart UI probe prohibited')
    if (h.count("args=['flutter','test'")!=1 or
            h.count('subprocess.Popen(args')!=1 or
            "'flutter_launches':1" not in h or
            'events==EVENTS[:len(events)]' not in h or
            "sequence==EVENTS and done==list(CASES)" not in h):
        errors.append('OPT05 single Flutter session and ordered case proof absent')
    if (d.count('StockInstaller(SettingsProvider()).installApk(')!=1 or
            'await awaitHostAck(testCase)' not in d or
            'wrongDigest==downgradeDigest' not in d):
        errors.append('OPT05 distinct runtime-bound signed fixtures and host ack required')
    if 'key.unlink(missing_ok=True)' not in f:
        errors.append('ephemeral wrong-signing key deletion missing')
    try:
        ast.parse(h);ast.parse(f)
    except SyntaxError:
        errors.append('RT02B Python syntax invalid')
    return errors


def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');p.parse_args()
    failures=inspect()
    for msg in failures: print('OX_R02_RT02B_SOURCE_REFUSED: '+msg)
    if failures:return 1
    print('OX_R02_RT02B_SOURCE_CONTRACT_PASS: Android negative runtime not performed',flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
