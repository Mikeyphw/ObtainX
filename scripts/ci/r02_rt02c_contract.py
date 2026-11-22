#!/usr/bin/env python3
"""RT02C source/stale-receipt gate. This is NOT Android runtime qualification."""
from __future__ import annotations
import argparse
import ast
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
R00='scripts/ci/r00_source_contract.py'
R00_TEST='scripts/ci/test_r00_source_contract.py'
SOURCE_WF='.github/workflows/obtainx-r00-contracts.yml'
WF='.github/workflows/obtainx-r02-rt02c.yml'
FIX='scripts/ci/r02_rt02c_fixture.py'
HOST='scripts/ci/r02_rt02c_hosted.py'
SINGLE='scripts/ci/r02_rt02c_single_session.py'
WATCHDOG='scripts/ci/r02c_watchdog.py'
WATCHDOG_TEST='scripts/ci/test_r02c_watchdog.py'
POLL='scripts/ci/obtainx_ci_optimization_opt06_rt02c_polling.py'
TEST='scripts/ci/test_r02_rt02c_contract.py'
DART='integration_test/r02c_archive_install_test.dart'
DOC='docs/R02_RT02C_ARCHIVE_RUNTIME_ACCEPTANCE.md'
BASE_HOST='scripts/ci/r02_rt02_hosted.py'
BASE_FIX='scripts/ci/r02_rt02_fixture.py'
PATHS=(R00,R00_TEST,SOURCE_WF,WF,FIX,HOST,SINGLE,POLL,TEST,DART,DOC,BASE_HOST,BASE_FIX,WATCHDOG,WATCHDOG_TEST)
CASES=('apks','apkm','xapk','zip','tar.gz','traversal','ambiguous')

def inspect(root:Path=ROOT)->list[str]:
    errors=[];docs={}
    for rel in PATHS:
        p=root/rel
        if not p.is_file():errors.append('missing source '+rel);docs[rel]=''
        else:docs[rel]=p.read_text('utf8')
    f=docs[FIX];w=docs[WF];h=docs[HOST];d=docs[DART]
    anchors={
      R00:("'obtainx-r02-rt02c.yml'",'unexpected = names - EXPECTED_WORKFLOWS',
           'missing = EXPECTED_WORKFLOWS - names'),
      R00_TEST:("'obtainx-r02-rt02c.yml'",'test_valid_strict_workflows'),
      SOURCE_WF:('python3 scripts/ci/r02_rt02c_contract.py --check',),
      WF:('permissions:\n  contents: read','persist-credentials: false',
          'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"',
          'flutter analyze integration_test lib test',
          'python3 -B scripts/ci/r02_rt02_fixture.py --out',
          'python3 -B scripts/ci/r02_rt02c_fixture.py --out',
          'python3 -B scripts/ci/r02_rt02c_hosted.py run --out',
          'python3 -B scripts/ci/r02_rt02c_hosted.py verify --out',
          'ReactiveCircus/android-emulator-runner@a421e43855164a8197daf9d8d40fe71c6996bb0d',
          "'system-images;android-36;google_apis;x86_64'",'api-level: 36','arch: x86_64',
          'test -c /dev/kvm','rt02c-receipt.json','rt02c-progress.json',
          'rt02c_inventory.json','if: always()',
          'actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02'),
      FIX:("POSITIVE=('apks','apkm','xapk','zip','tar.gz')",
           "NEGATIVE=('traversal','ambiguous')",'source_sha',
           'pack_zip(entries)','pack_tar(entries)',
           "members['../escape.apk']=base", "members['payload/another-base.apk']=base",
           'sha(base)==expected', "'release_qualified':False"),
      HOST:("CASES=POSITIVE+NEGATIVE",'base.installed_state(2,True,fixtures)',
            'baseline_v1(fixtures)', "'STOCK_INSTALLER_CALL'",'base._tap_confirmed_install_dialog()',
            "receipt['status']='PASS_FIVE_ARCHIVES_TWO_PREINSTALL_REFUSALS'",
            'source_sha', "'status':'NOT_RUN'", "data['status']='FAILED'",
            "'physical_device_qualified':False", "'full_r02_matrix_qualified':False",
            "'user_facing_import_qualified':False", "'release_qualified':False",
            "'publication_allowed':False", 'sha(fixtures/name)',
            'not called and taps==0', 'installed_signed_members_verified',
            'len(cases)==7', 'rt02c-progress.json',
            "obj.get('runner_probe_count')",
            "obj.get('runner_probe_skipped')",
            'controller.run()', "obj.get('flutter_launches')==1",
            'from r02_rt02c_single_session import ControlHandler,SingleSession',
            "obj.get('flutter_launches')==1"),
      SINGLE:('class SingleSession:', 'class ControlHandler(FixtureServer):',
              "self.base.adb('install', '-t', str(self.fixtures / 'base_v1.apk')",
              'not self.called and self.taps == 0',
              'subprocess.Popen(args', 'self.next_index += 1', 'self.launches = 1',
              'self.base.installed_state(2, True, self.fixtures)',
              'self.H.baseline_v1(self.fixtures)',
              'self.base._tap_confirmed_install_dialog()',
              'self.need(self.next_index == len(CASES)',
              "self.headers.get('X-RT02C-Token')",
              'from obtainx_ci_optimization_opt06_rt02c_polling import should_probe_runner',
              'should_probe_runner(now, self.runner_probe_last, runner_stage)',
              'self.runner_probe_skipped += 1',
              'from r02c_watchdog import RT02CWatchdog',
              'RT02CWatchdog(started)', 'watchdog.tick(',
              'OX_RT02C_WATCHDOG_REFUSED',
              "self.receipt['runner_probe_count'] = self.runner_probe_count"),
      WATCHDOG:('class RT02CWatchdog:', 'TOTAL_SECONDS=1200',
                "'TEST_APK_INSTALL':360", 'ACTIVE_CASE_SECONDS=420',
                'PRE_DART_APK_INSTALL_STALL', 'case_elapsed>=ACTIVE_CASE_SECONDS'),
      WATCHDOG_TEST:('test_first_apks_install_stall_refused',
                     'test_healthy_all_seven_cases_unaffected',
                     'test_total_cap_cannot_be_evaded_by_log_phase_churn'),
      POLL:('GRADLE_PROBE_INTERVAL_SECONDS = 8.0',
            'def should_probe_runner(', "phase != 'GRADLE_BUILD'"),
      DART:('IntegrationTestWidgetsFlutterBinding.ensureInitialized()',
            'extractZipOffIsolate(', 'extractTarballOffIsolate(',
            'resolveInstallBundlePlan(', 'installArtifactFormat(fileName)',
            'StockInstaller(SettingsProvider()).installApk(',
            'sha256.convert(bytes).toString() != archiveSha',
            'actual.toString() != expected', 'expect(plan.sessionPaths.length, 2)',
            "caseName == 'traversal'", "caseName == 'ambiguous'",
            'OX_R02C_DART_STAGE=PREINSTALL_REFUSED',
            'OX_R02C_DART_STAGE=INSTALL_CALL',
            'OX_R02C_DART_STAGE=INSTALL_RETURNED',
            "await control('prepare', name)",
            "await control('finish', name",
            "await control('call', caseName)",
            'request.contentLength = payload.length;',
            'request.add(payload);'),
      BASE_HOST:('def installed_state(', 'def _tap_confirmed_install_dialog(',
                 "APP='dev.bikram.obtainx.debug'"),
      BASE_FIX:("PKG = 'dev.bikram.obtainx.rt02.fixture'",'key.unlink(missing_ok=True)'),
      DOC:('NOT full R02', 'five archive formats', 'Production StockInstaller',
           'No releases','No merges','source-bound'),
      TEST:('test_valid_source','test_preinstall_rejects_traversal',
            'test_exact_seven_archive_cases','test_no_mock_installer',
            'test_opt06_missing_probe_count_refused',
            'test_opt06_missing_skipped_count_refused',
            'test_opt06_boolean_probe_count_refused',
            'test_opt06_excessive_skipped_count_refused'),
    }
    for p,markers in anchors.items():
        for m in markers:
            if m not in docs[p]:errors.append(p+': protected source evidence missing '+m)
    if any(w.count(token)!=1 for token in ('python3 -B scripts/ci/r02_rt02_fixture.py --out',
                                            'python3 -B scripts/ci/r02_rt02c_fixture.py --out')):
        errors.append('one pre-emulator build per fixture category required')
    if not re.search(r'(?s)name: Compile and verify signed APK and archive before emulator boot.*?name: Real Android archive update sessions',w):
        errors.append('archive fixture preflight must be ahead of Android runner')
    if re.search(r'(?m)^\s*(?:contents|pull-requests|actions|issues|packages|id-token):\s*write\s*$',w):
        errors.append('GitHub workflow write permission forbidden')
    if re.search(r'(?i)gh\s+release\s+create|flutter\s+build\s+apk.*--release',w):
        errors.append('publication forbidden')
    if d.count('extractZipOffIsolate(')!=2 or d.count('resolveInstallBundlePlan(')!=2 or d.count('OX_R02C_DART_STAGE=PREINSTALL_REFUSED')!=2:
        errors.append('archive scenario redundancy or negative path missing')
    if docs[R00_TEST].count("'obtainx-r02-rt02c.yml'") < 5:
        errors.append('R00 tests must cover new workflow in every allowlist fixture')
    if 'setMockMethodCallHandler' in d or 'mockito' in d:
        errors.append('platform installer mocks forbidden')
    if 'script: bash -c' not in w or 'r02_rt02c_hosted.py run --out "$RUNNER_TEMP/obtainx-rt02c"' not in w:
        errors.append('actual hosted emulator sessions required')
    for key in ('physical_device_qualified','full_r02_matrix_qualified',
                'user_facing_import_qualified','release_qualified','publication_allowed'):
        t="'"+key+"':False"
        if h.count(t)!=2 or "'"+key+"':True" in h:
            errors.append('unverified scope admission: '+key)
    if ('controller.run()' not in h or
            'not self.called and self.taps == 0' not in docs[SINGLE] or
            'self.base.installed_state(2, True, self.fixtures)' not in docs[SINGLE]):
        errors.append('negative/positive acceptance distinction bypassed')
    if "self.base.adb('install', '-t', str(self.fixtures / 'base_v1.apk')" not in docs[SINGLE]:
        errors.append('known v1 signed baseline absent')
    if 'raw_device_logs_uploaded' not in h or 'private.log' not in h:
        errors.append('private Flutter logs must stay ephemeral')
    if "'../escape.apk'" not in f or 'payload/another-base.apk' not in f:
        errors.append('adversarial archive fixtures missing')
    if re.search(r'\bfor\s+attempt\s+in\s*\(', docs[SINGLE]):
        errors.append('HF02 single-session retry loop forbidden')
    # RT02C HF09: enforce an atomic observation, not a stale clock sampled
    # before the control-server thread advances the active case start time.
    if not re.search(
        r'(?m)^    def snapshot\(self\):\n'
        r'(?:        \#[^\n]*\n)*'
        r'        with self\.lock:\n'
        r'            now = time\.monotonic\(\)\n'
        r'            active = self\.active\n'
        r'            case_elapsed = now - self\.case_started_at if active is not None else None\n',
        docs[SINGLE]):
        errors.append('HF09 atomic monotonic clock/case-start lock missing')
    if (docs[SINGLE].count('failure, case_elapsed) = self.snapshot()')!=1 or
        docs[SINGLE].count('case_elapsed=case_elapsed)')!=1 or
        'case_elapsed=(now-self.case_started_at' in docs[SINGLE]):
        errors.append('HF09 runner must consume the same atomic clock snapshot')
    if docs[SINGLE].count('subprocess.Popen(')!=1:
        errors.append('HF01 must launch exactly one Flutter process')
    if docs[SINGLE].count('self.H.baseline_v1(self.fixtures)')!=2:
        errors.append('HF01 must verify v1 before and after negative')
    if docs[SINGLE].count('self.next_index += 1')!=1:
        errors.append('HF01 must independently advance every Android boundary')
    if docs[DART].count("await control('prepare', name)")!=1 or \
            docs[DART].count("await control('finish', name")!=1:
        errors.append('HF01 must use host handshake before and after every scenario')
    try:ast.parse(h);ast.parse(f);ast.parse(docs[SINGLE])
    except SyntaxError:errors.append('fixture or host Python syntax invalid')
    return errors

def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');p.parse_args()
    errs=inspect()
    for msg in errs:print('OX_R02_RT02C_SOURCE_REFUSED: '+msg)
    if errs:return 1
    print('OX_R02_RT02C_SOURCE_CONTRACT_PASS: Android runtime not performed',flush=True)
    return 0
if __name__=='__main__':raise SystemExit(main())
