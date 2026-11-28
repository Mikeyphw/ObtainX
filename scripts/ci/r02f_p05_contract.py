#!/usr/bin/env python3
"""P05 production device-profile/OBB evidence and real hosted read-only gate."""
from __future__ import annotations
import argparse,ast,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
MODEL='lib/services/r02f_p05_device_profile.dart'
PROVIDER='lib/providers/apps_provider_install.dart'
PLANNER='lib/services/install_bundle_plan.dart'
OBB='lib/services/verified_obb_delivery.dart'
DART='test/r02f_p05_device_profile_test.dart'
OBB_TEST='test/r02f_p05_obb_ancestor_test.dart'
HOST='scripts/ci/r02f_p05_hosted.py'
PHYSICAL='scripts/ci/r02f_p05_physical_probe.py'
R00='.github/workflows/obtainx-r00-contracts.yml'
FLUTTER='.github/workflows/obtainx-r00-flutter.yml'
RT02C='.github/workflows/obtainx-r02-rt02c.yml'
DOC='docs/R02F_P05_DEVICE_COMPAT_OBB.md'
PATHS=(MODEL,PROVIDER,PLANNER,OBB,DART,OBB_TEST,HOST,PHYSICAL,R00,FLUTTER,RT02C,DOC)

def inspect(root:Path=ROOT)->list[str]:
    errors=[];data={}
    for name in PATHS:
        p=root/name
        if not p.is_file() or p.is_symlink() or p.stat().st_size>220000:
            errors.append('missing, symlink or oversized P05 source '+name);data[name]=''
        else:data[name]=p.read_text('utf-8')
    def req(ok,label):
        if not ok:errors.append(label)
    for name in (HOST,PHYSICAL):
        try:ast.parse(data[name],filename=name)
        except SyntaxError:errors.append('P05 invalid Python source '+name)
    model=data[MODEL];provider=data[PROVIDER];obb=data[OBB]
    req(model.startswith('///') and re.search(r'\Alibrary;',model) is None and
        re.match(r'\A(?:///[^\n]*\n)+library;\n',model) is not None,
        'P05 Dart library directive missing (analyzer warning)')
    for anchor in ('validateP05DeviceProfile(', 'verifyP05SdkEnvelope(',
                   'p05DirectObbDeliveryEligible(',
                   'supportedAbis.isEmpty','sdk < 1','densityDpi < 80',
                   'plan.targetSdkVersion!', 'member.targetSdkVersion != plan.targetSdkVersion',
                   'androidSdk < 30','storagePermissionGranted'):
        req(anchor in model,'P05 model safety missing '+anchor)
    req('p05DirectObbDeliveryEligible(' in data[DART] and
        'resolveInstallBundlePlan(' in data[DART] and
        'verifyP05SdkEnvelope(' in data[DART],
        'P05 tests must exercise actual RT02D planner and OBB policy')
    start=provider.find('final int? uiDensityDpi = views.isNotEmpty')
    profile=provider.find('validateP05DeviceProfile(',start)
    plan=provider.find('final plan = resolveInstallBundlePlan(',start)
    sdk=provider.find('verifyP05SdkEnvelope(',plan)
    end=provider.find('final baseInfo = infoByPath[plan.baseApkPath]',plan)
    req(start>=0 and start<profile<plan<sdk<end,
        'P05 production profile and SDK validation not around real RT02D plan')
    for anchor in ('supportedAbis: device.supportedAbis',
                   'deviceLocales: uiLocales','deviceDensityDpi: uiDensityDpi',
                   'deviceSdkVersion: device.version.sdkInt',
                   'OBB payload cannot be installed by this backend on Android 11+'):
        req(anchor in provider,'P05 inherited production gate changed '+anchor)
    req('resolveInstallBundlePlan(' in data[PLANNER] and
        'validateStagedObbPaths(' in data[PLANNER],
        'P05 inherited RT02D planner lost')
    req(obb.count('_assertNoSymlinkAncestors(destinationFolder);')==2 and
        'FileSystemEntity.typeSync(path, followLinks: false)' in obb and
        'OBB destination ancestor is symlink' in obb and
        obb.count('sha256.bind(')==2 and obb.count('isCancelled?.call()')==2,
        'P05 OBB ancestor / SHA / cancellation safety changed')
    req('symlink ancestor' in data[OBB_TEST] and
        'copyVerifiedObbFile(' in data[OBB_TEST],
        'P05 OBB real file-system tests missing')
    host=data[HOST];physical=data[PHYSICAL]
    for anchor in ('base.host_check()','base.identity_check()',
                   "RECEIPT = 'r02f-p05-device-profile.json'",
                   'ro.product.cpu.abilist','ro.sf.lcd_density',
                   'persist.sys.locale','source_sha','signed_v1_sha256',
                   "'direct_obb_api30_plus_refused':True",
                   "'obb_delivery_qualified':False",
                   "'physical_device_qualified':False",'inventory(out,source)'):
        req(anchor in host,'P05 hosted profile or qualifier missing '+anchor)
    offline=host.split('def verify(',1)[-1].split('def main(',1)[0]
    req('base.adb(' not in offline and 'return True' not in offline,
        'P05 independent receipt verifier must remain offline')
    req('I_AUTHORIZE_READ_ONLY_DEVICE_PROBE' in physical and
        "'device_writes':False" in physical and "'release_qualified':False" in physical and
        "'install'" in physical and "'root'" in physical and
        "def prop(x):return adb(serial,'shell','getprop',x)" in physical and
        "report=profile(a.serial, a.ack)" in physical,
        'P05 physical read-only nonqualifying opt-in probe missing')
    for anchor in ('python3 -B scripts/ci/r02f_p05_hosted.py run --out',
                   'python3 -B scripts/ci/r02f_p05_hosted.py verify --out',
                   'r02f-p05-device-profile.json'):
        req(anchor in data[RT02C],'P05 hosted read-only receipt not wired '+anchor)
    run_earlier=data[RT02C].find('r02f_p04_backends_hosted.py run --out')
    p05run=data[RT02C].find('r02f_p05_hosted.py run --out')
    req(0<=run_earlier<p05run,'P05 hosted profile must follow P04 acceptance')
    req('python3 -B scripts/ci/r02f_p05_contract.py --check' in data[R00],
        'P05 mandatory source contract omitted')
    for test_name in ('r02f_p05_device_profile_test.dart',
                      'r02f_p05_obb_ancestor_test.dart'):
        req('flutter test --no-pub test/'+test_name in data[FLUTTER],
            'P05 mandatory Flutter regression omitted '+test_name)
    for term in ('API36','ARM64','OBB','Android 11+','physical',
                 'P06','NOT_QUALIFIED','R03','R12'):
        req(term in data[DOC],'P05 roadmap/qualification disclosure missing '+term)
    return errors

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');ap.parse_args()
    issues=inspect()
    for x in issues:print('OX_P05_SOURCE_REFUSED '+x)
    if issues:return 2
    print('OX_P05_DEVICE_PROFILE_OBB_SOURCE_CONTRACT_PASS; PHYSICAL=NOT_QUALIFIED')
    return 0
if __name__=='__main__':raise SystemExit(main())
