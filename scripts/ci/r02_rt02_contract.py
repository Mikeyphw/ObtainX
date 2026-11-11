#!/usr/bin/env python3
"""RT02 A fail-closed source/stale-test contract; NOT a runtime pass."""
from __future__ import annotations
import argparse
import ast
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
WORKFLOW='.github/workflows/obtainx-r02-rt02.yml'
R00='scripts/ci/r00_source_contract.py'
R00_TEST='scripts/ci/test_r00_source_contract.py'
SOURCE_GATE='.github/workflows/obtainx-r00-contracts.yml'
DART='integration_test/r02_real_installer_test.dart'
HOST='scripts/ci/r02_rt02_hosted.py'
FIXTURE='scripts/ci/r02_rt02_fixture.py'
TEST='scripts/ci/test_r02_rt02_contract.py'
DOC='docs/R02_RT02_REAL_INSTALL_GATE.md'
PUBSPEC='pubspec.yaml'
PATHS=(WORKFLOW,R00,R00_TEST,SOURCE_GATE,DART,HOST,FIXTURE,TEST,DOC,PUBSPEC)


def _functions(source:str)->dict[str,str]:
    tree=ast.parse(source)
    lines=source.splitlines()
    return {node.name:'\n'.join(lines[node.lineno-1:node.end_lineno])
            for node in tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))}


def inspect(root:Path=ROOT)->list[str]:
    errors=[];files={}
    for path in PATHS:
        p=root/path
        if not p.is_file():
            errors.append('missing required file: '+path);files[path]=''
        else:
            files[path]=p.read_text('utf-8')
    w=files[WORKFLOW];r00=files[R00];r00test=files[R00_TEST]
    host=files[HOST];fixture=files[FIXTURE];dart=files[DART];docs=files[DOC]
    requirements={
        R00:("'obtainx-r02-rt02.yml'",'unexpected = names - EXPECTED_WORKFLOWS',
             'missing = EXPECTED_WORKFLOWS - names','errors.extend(check_workflows(workflows))'),
        R00_TEST:('test_reviewed_rt02_required_and_release_is_still_prohibited',
                  "del omitted['obtainx-r02-rt02.yml']",'rogue-release.yml'),
        SOURCE_GATE:('run: python3 scripts/ci/r02_rt02_contract.py --check',),
        PUBSPEC:('integration_test:', 'sdk: flutter'),
        WORKFLOW:('permissions:\n  contents: read','persist-credentials: false',
                  'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"',
                  "python3 -B scripts/ci/r02_rt02_fixture.py --out",
                  'python3 -B scripts/ci/r02_rt02_hosted.py run --out',
                  'python3 -B scripts/ci/r02_rt02_hosted.py verify --out',
                  'flutter analyze integration_test lib test',
                  'test -c /dev/kvm', "'system-images;android-36;google_apis;x86_64'",
                  'ReactiveCircus/android-emulator-runner@a421e43855164a8197daf9d8d40fe71c6996bb0d',
                  'api-level: 36','target: google_apis','arch: x86_64',
                  'if: always()', 'rt02-receipt.json','progress.json','fixture_inventory.json',
                  'actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02'),
        DART:("IntegrationTestWidgetsFlutterBinding.ensureInitialized()",
              'OX_R02_RT02_DART_STAGE=INSTALL_CALL',
              "const version = scenario == 'standalone' ? 1 : 2;",
              'StockInstaller(SettingsProvider()).installApk(',
              'resolveInstallBundlePlan(',"expectedPackageName:packageName",
              "sha256.convert(data).toString() != expected",
              "scenario == 'split' ? 2 : 1", "result.isSuccess, isTrue",
              "format:scenario == 'standalone' ? InstallArtifactFormat.apk : InstallArtifactFormat.apks"),
        FIXTURE:("PKG = 'dev.bikram.obtainx.rt02.fixture'",'secrets.token_hex',
                 "'keytool', '-genkeypair'", "str(aapt2), 'link'",
                 "str(zipalign), '-f'", "str(signer), 'sign'",
                 "str(signer), 'verify'", "key.unlink(missing_ok=True)",
                 "('base_v1.apk', 'base_v2.apk', 'config.x86_64.apk')",
                 "'signed_with_ephemeral_ci_key':True"),
        HOST:("APP='dev.bikram.obtainx.debug'", "FIXTURE='dev.bikram.obtainx.rt02.fixture'",
              "SERIAL='emulator-5554'",'identity_check()',
              "adb('shell','getprop','ro.kernel.qemu')=='1'",
              "adb('shell','getprop','ro.build.version.sdk')=='36'",
              "'flutter','test'", "'--flavor','normal'",
              "scenario in ('standalone','split')",
              "_tap_confirmed_install_dialog()",
              'APPROVERS=', 'NAME=',
              "label in ('Install','Update','Install app','Update app')",
              "tap_count==1", "'All tests passed!' in text",
              "installed_state(1 if scenario=='standalone' else 2",
              'RT02_FLUTTER_TIMEOUT', 'flutter_phase(logfile)',
              'record_flutter_progress(out,scenario,phase',
              "'shell','sha256sum'", "'shell','pm','path'",
              "'status']='PASS_TWO_ANDROID_SYSTEM_SESSIONS'",
              "'full_r02_matrix_qualified':False",
              "'physical_device_qualified':False",
              "'release_qualified':False", "'publication_allowed':False",
              "'action',choices=['run','verify']"),
        DOC:('NOT full R02 runtime-matrix acceptance','No releases','No merges',
             'Cinderbox-Companion','eee62aa6d0b6eadec5543d6ed0ee67e3fc57e373'),
    }
    for path,needles in requirements.items():
        for needle in needles:
            if needle not in files[path]:errors.append(path+': required contract missing: '+needle)
    if not re.search(r'(?m)^  integration_test:\s*\n    sdk: flutter\s*$', files[PUBSPEC]):
        errors.append('pubspec Flutter integration_test SDK dependency not configured')
    for label in ("'full_r02_matrix_qualified':False", "'release_qualified':False",
                  "'physical_device_qualified':False", "'publication_allowed':False"):
        if host.count(label) != 2:
            errors.append('runtime gate false admission flag missing in initial receipt: '+label)
    if host.count('phase=flutter_phase(logfile)') != 2:
        errors.append('runtime progress phase probes missing or duplicated')
    # The verification must be source-bound and require both distinct scenarios.
    if "for scenario in ('standalone','split')" not in host:
        errors.append('real installer host must execute both actual Android sessions')
    if 'valid_scenarios' not in host:
        errors.append('independent receipt verification lacks exact two-session proof')
    if "'status':'NOT_RUN'" not in host or "v['status']='FAILED'" not in host:
        errors.append('no fail-closed RT02 status lifecycle')
    # AAPT2 cannot resolve android:configForSplit; for a base-targeting
    # config split omit configForSplit entirely and keep only split identity.
    if 'android:configForSplit="' in fixture or 'configForSplit="base"' in fixture:
        errors.append('fixture declares an invalid configForSplit attribute')
    if ('def fixture_manifest(version: int, split: bool) -> str:' not in fixture
            or "'split=\"config.x86_64\" ' if split else ''" not in fixture
            or "manifest.write_text(fixture_manifest(version, split), encoding='utf-8')" not in fixture):
        errors.append('fixture manifest must use checked base-targeting split generator')
    for name in ('test_config_split_targets_base_without_invalid_attribute',
                 'test_standalone_manifest_has_no_split_identity',
                 'test_namespaced_config_for_split_is_refused',
                 'test_fixture_preflight_is_mandatory'):
        if name not in files[TEST]:
            errors.append('stale RT02 fixture regression missing: ' + name)
    for name in ('test_split_zero_dialog_valid_only_when_exact_platform_proof_recorded',
                 'test_split_no_dialog_requires_verified_split_and_version',
                 'test_standalone_first_install_approval_required',
                 'test_split_no_dialog_wrong_version_refused'):
        if name not in files[TEST]:
            errors.append('HF05 approval regression missing: '+name)
    if 'RT02A HF05' not in docs:
        errors.append('HF05 approval-scope docs missing')
    if ('- name: Compile and validate disposable APK fixtures before emulator boot' not in w
            or 'test -s "$RUNNER_TEMP/obtainx-rt02/fixtures/fixture_inventory.json"' not in w):
        errors.append('RT02 fixture build must be a separate pre-emulator hard gate')
    if (w.count('python3 -B scripts/ci/r02_rt02_fixture.py --out') != 1
            or "script: bash -c 'set -euo pipefail; python3 -B scripts/ci/r02_rt02_hosted.py run" not in w):
        errors.append('fixture generation must occur exactly once before the emulator')
    if 'setMockMethodCallHandler' in dart or 'mockito' in dart:
        errors.append('platform installer must never be mocked in real acceptance')
    if re.search(r'(?i)gh\s+release\s+create|flutter\s+build\s+apk.*--release',w):
        errors.append('CI must not publish or build release')
    if re.search(r'(?m)^\s+(?:contents|pull-requests|actions|issues|id-token):\s*write\s*$',w):
        errors.append('CI write permission forbidden')
    try:
        hf=_functions(host);ff=_functions(fixture)
        for name,needles in {
            'installed_state': ('sha_file(fixture_dir/', "'shell','sha256sum'", "digest[0]==expected[name]", "str(expected_version) in matches", "'shell','dumpsys','package'"),
            'one_scenario': ('flutter', "classify_android_approval(scenario,tap_count,actual)", "'All tests passed!' in text",
                             'flutter_phase(logfile)', 'record_flutter_progress(out,scenario,phase'),
            '_tap_confirmed_install_dialog': ('APPROVERS',"NAME in", "label in ('Install','Update'"),
            'execute': ("for scenario in ('standalone','split')", "'status']='PASS_TWO_ANDROID_SYSTEM_SESSIONS'"),
            'verify': ("'status':'PASS_TWO_ANDROID_SYSTEM_SESSIONS'", "valid_scenarios"),
        }.items():
            body=hf.get(name,'')
            for needle in needles:
                if needle not in body:errors.append('host proof bypassed: '+name+' / '+needle)
        approval=hf.get('classify_android_approval','')
        for needle in ("tap_count in (0,1)", "need(tap_count==1,",
                       "'platform_committed_no_dialog'", "actual.get('version_code')==2",
                       "actual.get('installed_path_count')==2",
                       "actual.get('config_x86_64_present') is True"):
            if needle not in approval:
                errors.append('Android platform approval classifier bypassed: '+needle)
        scenario_body=hf.get('one_scenario','')
        verify_pos=scenario_body.find("actual=installed_state(1 if scenario=='standalone' else 2,")
        admission_pos=scenario_body.find('approval_path=classify_android_approval(scenario,tap_count,actual)')
        if verify_pos<0 or admission_pos<0 or verify_pos>=admission_pos:
            errors.append('installed version/hash must precede approval classification')
        checker=hf.get('verify','')
        if "(0,'platform_committed_no_dialog')" not in checker or "(1,'explicit_dialog')" not in checker:
            errors.append('independent receipt must verify both exact update approval modes')
        if 'key.unlink(missing_ok=True)' not in ff.get('signed_fixture',''):
            errors.append('ephemeral signing key deletion bypassed')
    except SyntaxError:
        errors.append('host or fixture Python syntax invalid')
    return errors


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');ap.parse_args()
    errors=inspect()
    for e in errors:print('OX_R02_RT02_CONTRACT_REFUSED: '+e)
    if errors:return 1
    print('OX_R02_RT02_SOURCE_CONTRACT_PASS: real installer scoped; runtime not performed')
    return 0
if __name__=='__main__':raise SystemExit(main())
