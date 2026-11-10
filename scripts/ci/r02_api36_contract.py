#!/usr/bin/env python3
"""R02 RT01 API36 hosted emulator safety/staleness source contract."""
from __future__ import annotations
import argparse
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = '.github/workflows/obtainx-r02-api36.yml'
SMOKE = 'scripts/ci/r02_api36_smoke.py'
TEST = 'scripts/ci/test_r02_api36_contract.py'
DOC = 'docs/R02_API36_BOOTSTRAP.md'
INHERITED_CI = '.github/workflows/obtainx-r00-contracts.yml'
R00_CONTRACT = 'scripts/ci/r00_source_contract.py'
R00_TEST = 'scripts/ci/test_r00_source_contract.py'


def inspect(root: Path = ROOT) -> list[str]:
    p = []
    files = {}
    for name in (WORKFLOW, SMOKE, TEST, DOC, INHERITED_CI, R00_CONTRACT, R00_TEST):
        path = root / name
        if not path.is_file():
            p.append('missing source: ' + name)
            files[name] = ''
        else:
            files[name] = path.read_text()
    w, s, docs = files[WORKFLOW], files[SMOKE], files[DOC]
    inherited = files[INHERITED_CI]
    r00_contract = files[R00_CONTRACT]
    r00_test = files[R00_TEST]
    # Do not disable the strict workflow inventory; R00 must explicitly list
    # this one reviewed workflow, while still refusing unknown workflows.
    if "'obtainx-r02-api36.yml'," not in r00_contract:
        p.append('R00 must register the exact API36 workflow in its strict inventory')
    if 'unexpected = names - EXPECTED_WORKFLOWS' not in r00_contract or \
       'missing = EXPECTED_WORKFLOWS - names' not in r00_contract or \
       "errors.extend(check_workflows(workflows))" not in r00_contract:
        p.append('R00 default-deny workflow inventory must remain enforced')
    for fragment in ('test_reviewed_api36_required_and_no_unknown_workflows',
                     'test_reviewed_emulator_still_read_only_and_no_release'):
        if fragment not in r00_test:
            p.append('R00 workflow mutation regression missing: '+fragment)
    if 'run: python3 scripts/ci/r02_api36_contract.py --check' not in inherited:
        p.append('inherited Python contract gate lacks R02 API36 audit')
    required_workflow = (
      'permissions:\n  contents: read', 'persist-credentials: false',
      'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"',
      'flutter build apk --debug --flavor normal --no-pub',
      "test -c /dev/kvm", 'test -r /dev/kvm && test -w /dev/kvm',
      "'system-images;android-36;google_apis;x86_64'",
      '(( available_kib >= 4 * 1024 * 1024 ))',
      'ReactiveCircus/android-emulator-runner@a421e43855164a8197daf9d8d40fe71c6996bb0d',
      'api-level: 36', 'target: google_apis', 'arch: x86_64',
      'script: python3 -B scripts/ci/r02_api36_smoke.py run',
      'python3 -B scripts/ci/r02_api36_smoke.py verify',
      'if: always()',
      'actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02',
      'obtainx-r02-api36/receipt.json', 'obtainx-r02-api36/app_launch.png',
      'python3 -B scripts/ci/r02_api36_contract.py --check',
      "-p 'test_r02_api36_contract.py'",
    )
    for needle in required_workflow:
        if needle not in w:
            p.append('hosted API36 workflow requirement missing: ' + needle)
    if w.count('test "$(git rev-parse HEAD)" = "$GITHUB_SHA"') != 2:
        p.append('source binding required in both bootstrap and receipt initialization')
    if ('uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262' not in w
        or 'flutter-version: \'3.47.6\'' not in w):
        p.append('checkout/Flutter must remain pinned')
    if ('if: ${{ failure() }}' in w or '--update-goldens' in w):
        p.append('emulator workflow must not regenerate goldens on error')
    if re.search(r'flutter\s+build\s+(?:apk|appbundle).*--release', w):
        p.append('emulator workflow cannot sign/build a release')
    if 'apk' not in w or 'R02 / API 36' not in w:
        p.append('R02 bootstrap context missing')
    required_smoke = (
        "PACKAGE = 'dev.bikram.obtainx.debug'",
        "SERIAL = 'emulator-5554'",
        "COMPONENT = 'dev.bikram.obtainx.debug/dev.imranr.obtainium.MainActivity'",
        "adb('shell', 'getprop', 'ro.kernel.qemu') == '1'",
        "adb('shell', 'getprop', 'ro.build.version.sdk') == '36'",
        "f\"package: name='{PACKAGE}'\" in badging",
        "'verify', '--print-certs'",
        'verify_fresh_package_absent()',
        "'shell', 'pm', 'path', PACKAGE",
        "'shell', 'cmd', 'package', 'list', 'packages', '--user', '0', PACKAGE",
        'result.returncode in (0, 1) and not stdout and not stderr',
        'need(not listing.strip()',
        "stage('VERIFY_FRESH_PACKAGE')",
        "stage('INSTALL_DEBUG_APK')",
        "stage('VERIFY_INSTALLED_APK_BYTES')",
        "detail = (result.stderr.decode(errors='replace').strip()",
        "or result.stdout.decode(errors='replace').strip()",
        "adb('install', '-t', str(APK)",
        "adb('shell', 'sha256sum', remote_path)",
        "installed_sha_text[0] == apk_sha",
        "adb('shell', 'am', 'start', '-W', '-n', COMPONENT",
        "adb('shell', 'pidof', PACKAGE) == pid",
        "adb('exec-out', 'screencap', '-p'",
        "data['app_apk_sha256'] == data['installed_apk_sha256']",
        "data['app_launch_png_sha256']",
        "'status': 'NOT_RUN'", "'status':'PASS'",
        "'physical_device_qualified': False",
        "'split_install_e2e_qualified': False",
        "'obtainx_installer_e2e_qualified': False",
        "'release_qualified': False", "'publication_allowed': False",
        'source_sha', 'run_id',
    )
    for needle in required_smoke:
        if needle not in s:
            p.append('emulator safety/proof code missing: ' + needle)
    for proof_test in (
        'test_absent_pm_path_rc1_with_independent_listing',
        'test_absent_pm_path_rc0_with_independent_listing',
        'test_nonfresh_pm_path_refused',
        'test_nonfresh_package_listing_refused',
        'test_ambiguous_pm_path_status_refused',
        'test_ambiguous_pm_path_stderr_refused',
        'test_failed_second_probe_refused',
        'test_command_failure_logs_argv_and_stdout',
        'test_command_failure_logs_stderr',
    ):
        if proof_test not in files[TEST]:
            p.append('missing exact-package probe mutation regression: '+proof_test)
    if s.count('    verify_fresh_package_absent()\n') != 1:
        p.append('mandatory fresh-package probe invocation missing or duplicated')
    if s.count("'split_install_e2e_qualified': False") != 2:
        p.append('split-install admission flag must remain false at init and independent verify')
    if s.count("'package': PACKAGE") != 1 or s.count("'package':PACKAGE") != 1:
        p.append('app identity must be bound at capture and receipt verification')
    if re.search(r'\b(?:(?:allow|permit)_release|publication_allowed|release_qualified)\b[\'\"]?\s*:\s*True', s):
        p.append('release/publication must never be marked qualified')
    if 'NOT a split-install E2E qualification' not in docs:
        p.append('scope disclaimer absent')
    if 'Cinderbox-Companion' not in docs:
        p.append('emulator provenance absent')
    if 'dd297f3e0e503e1a1b59b0ce2a0b629e05808204' not in docs:
        p.append('source base pin missing')
    return p


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.parse_args()
    failures = inspect()
    for failure in failures:
        print('OX_R02_API36_CONTRACT_FAIL: '+failure)
    if failures:
        return 1
    print('OX_R02_API36_CONTRACT_PASS: pinned emulator, fail-closed receipts, no release claims')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
