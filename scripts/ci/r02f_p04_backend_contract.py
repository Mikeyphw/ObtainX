#!/usr/bin/env python3
"""P04 Shizuku/Dhizuku read-only backend availability contract, no privilege writes."""
from __future__ import annotations
import argparse,ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
PLUGIN='lib/installers/shizuku_plugin.dart'
MODEL='lib/services/r02f_p04_backend_availability.dart'
DART='integration_test/r02f_p04_backend_unavailable_test.dart'
DART_TEST='test/r02f_p04_backend_availability_test.dart'
HOST='scripts/ci/r02f_p04_backends_hosted.py'
DOC='docs/R02F_P04_BACKEND_AVAILABILITY.md'
MATRIX='docs/R02F_P04_INSTALLER_BACKEND_MATRIX.md'
CI='.github/workflows/obtainx-r02-rt02c.yml'
R00='.github/workflows/obtainx-r00-contracts.yml'
PATHS=(PLUGIN,MODEL,DART,DART_TEST,HOST,DOC,MATRIX,CI,R00)

def inspect(root:Path=ROOT)->list[str]:
    issues=[];d={}
    for path in PATHS:
        f=root/path
        if not f.is_file() or f.is_symlink() or f.stat().st_size>180000:
            issues.append('missing/linked/oversized '+path);d[path]=''
        else:d[path]=f.read_text('utf8')
    p,m,dt,t,h,doc,mat,ci,r00=(d[x] for x in PATHS)
    # HF01: cheap mandatory source checks for Dart analyzer regressions that
    # previously blocked all hosted Flutter and Android workflows.
    # A leading /// library documentation comment requires a library directive;
    # the mode selection is a compile-time constant (prefer_const_declarations).
    if not (m.count('\nlibrary;\n')==1 and
            m.split('import ',1)[0].rstrip().endswith('library;')):
        issues.append('HF01 dangling backend model library documentation comment')
    if (dt.count("const mode = _selected == 'shizuku' ? InstallerMode.shizuku : InstallerMode.dhizuku;")!=1
            or "final mode = _selected == 'shizuku'" in dt):
        issues.append('HF01 backend integration test must use const mode')
    def check(ok,label):
        if not ok:issues.append(label)
    try:ast.parse(h,filename=HOST)
    except SyntaxError:issues.append('invalid backend hosted Python')
    for item in ('probeP04BackendAvailability(', 'if (!userInitiated)',
                 'checkShizukuPluginPermission(mode)', 'classifyP04Backend(mode, raw'):
        check(item in p,'plugin read-only explicit-entrypoint missing '+item)
    for item in ('InstallerMode.dhizuku',
                 "'granted_adb'", "'granted_root'", "'granted_owner'",
                 "'services_not_found'", "'denied'", "'old_shizuku'",
                 'P04BackendState.wrongBackendPermission',
                 'P04BackendState.authorizedUnqualified',
                 'bool get canClaimInstallSuccess => false;',
                 'bool get releaseQualified => false;',
                 'bool get physicalDeviceQualified => false;',
                 'userInitiated && hostedApi36 && signedDisposableFixture'):
        check(item in m,'backend availability classifier weakened '+item)
    for item in ('probeP04BackendAvailability(', 'InstallerMode.shizuku',
                 'InstallerMode.dhizuku', 'OX_P04_SHIZUKU_REAL_ABSENCE_PASS',
                 'OX_P04_DHIZUKU_REAL_ABSENCE_PASS',
                 'OX_P04_BACKEND_EXPLICIT_AUTHORIZED_READ_ONLY_PASS',
                 'expect(p.canClaimInstallSuccess, false)'):
        check(item in dt,'real native plugin/absence check missing '+item)
    for item in ('authorizationRequired', 'wrongBackendPermission','hostedApi36'):
        check(item in t or item in m,'Dart backend negatives missing '+item)
    for item in ('base.host_check()', 'base.identity_check()',
                 'I_AUTHORIZE_DISPOSABLE_API36_READ_ONLY_BACKEND_PROBE',
                 'permission_probe_planned(', 'r02f-p04-backend-availability.json',
                 'shizuku_unavailable', 'dhizuku_unavailable',
                 "'backend_install_qualified':False", 'privileged_install_performed',
                 'private_log_sha256', 'raw_logs_uploaded',
                 "'source_sha'", "'mode'", 'check_fixture(out,source)'):
        check(item in h,'hosted availability/receipt guard missing '+item)
    check('pm install' not in h and "base.adb('install'" not in h and
          'set-device-owner' not in h and 'requestPermission(' not in h and
          'su -c' not in h,'privileged backend test attempted mutation/provision')
    ver=h.split('def verify(',1)[-1].split('def main(',1)[0]
    check('base.adb(' not in ver and 'return True' not in ver,
          'backend receipt verifier must remain offline')
    for item in ('python3 -B scripts/ci/r02f_p04_backends_hosted.py run --out',
                 'python3 -B scripts/ci/r02f_p04_backends_hosted.py verify --out',
                 'r02f-p04-backend-availability.json'):
        check(item in ci,'P04 actual API36 availability test/receipt missing '+item)
    check(ci.count('scripts/ci/r02f_p04_backends_hosted.py run --out')==1 and
          ci.count('scripts/ci/r02f_p04_backends_hosted.py verify --out')==1 and
          ci.index('scripts/ci/r02f_p04b_p03_hosted.py run --out') <
          ci.index('scripts/ci/r02f_p04_backends_hosted.py run --out')
          if 'scripts/ci/r02f_p04b_p03_hosted.py run --out' in ci and
             'scripts/ci/r02f_p04_backends_hosted.py run --out' in ci else False,
          'positive and adversarial P04B acceptance must precede backend checks')
    check('python3 -B scripts/ci/r02f_p04_backend_contract.py --check' in r00,
          'mandatory R00 P04 backend source gate missing')
    check(mat.count('**NOT_AVAILABLE / NOT_QUALIFIED**')>=3 and
          '**NOT_QUALIFIED** for real external' in mat,
          'existing backend matrix was falsely marked ready')
    check('**NOT_QUALIFIED** for real Shizuku/Dhizuku installation.' in doc,
          'explicit backend-install scope was weakened')
    for item in ('NOT_QUALIFIED','Shizuku','Dhizuku','P04B P03',
                 'explicit','read-only','device owner','R12'):
        check(item in doc,'P04 scope/roadmap disclosure missing '+item)
    return issues

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');ap.parse_args()
    errors=inspect()
    for error in errors:print('OX_P04_BACKEND_SOURCE_REFUSED '+error)
    if errors:return 2
    print('OX_P04_BACKEND_SOURCE_CONTRACT_PASS; AUTHORIZED_PRIVILEGED_INSTALL_NOT_PERFORMED',flush=True)
    return 0
if __name__=='__main__':raise SystemExit(main())
