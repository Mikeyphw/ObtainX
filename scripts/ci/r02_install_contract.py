#!/usr/bin/env python3
"""R02 source/test/CI staleness audit; supplements mandatory real Flutter tests.

This deliberately cannot certify Android split installation or signing.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]

# This guard is anchored at the archive metadata discovery/catch boundary.
# A cleanup call in an unrelated branch, or a commented-out cleanup in this
# branch, must not pass the source contract.
_BAD_ARCHIVE_CLEANUP_RE = re.compile(
    r"""
    parsedArchivePath\s*=\s*plan\.baseApkPath;\s*
    \}\s*catch\s*\(_\)\s*\{\s*
    //\s*Discard\s+any\s+archive\s+whose\s+package\s+inventory\s+is\s+invalid\.\s*
    final\s+extracted\s*=\s*Directory\(apkDirPath\);\s*
    if\s*\(\s*extracted\.existsSync\(\)\s*\)\s*\{\s*
    extracted\.deleteSync\(\s*recursive:\s*true\s*\);\s*
    \}\s*rethrow;\s*\}
    """,
    re.VERBOSE,
)


def archive_inventory_cleanup_intact(provider: str) -> bool:
    """Require stage disposal *and* exception propagation at this exact boundary."""
    return _BAD_ARCHIVE_CLEANUP_RE.search(provider) is not None


def inspect(root: Path = ROOT) -> list[str]:
    problems=[]
    def require(condition: bool, description: str) -> None:
        if not condition: problems.append(description)
    def read(path: str) -> str:
        f=root/path
        if not f.is_file():
            problems.append(f'missing R02 file: {path}')
            return ''
        return f.read_text(encoding='utf-8')
    planner=read('lib/services/install_bundle_plan.dart')
    provider=read('lib/providers/apps_provider_install.dart')
    app=read('lib/providers/apps_provider.dart')
    formats=read('lib/app_sources/app_package_formats.dart')
    tests=read('test/r02_install_bundle_plan_test.dart')
    flutter=read('.github/workflows/obtainx-r00-flutter.yml')
    contracts=read('.github/workflows/obtainx-r00-contracts.yml')
    release=read('docs/SECURITY_RELEASE_POLICY.md')
    read('docs/R02_INSTALL_PLAN_AUDIT.md')
    pin_raw=read('docs/R02_SOURCE_BASELINE.json')
    try:
        pin=json.loads(pin_raw)
        require(pin.get('schema') == 1 and
                pin.get('r01_qualified_head') == '3a57cfdced5940d3cdebd2396ba9c86c21d4926c' and
                pin.get('r01_qualified_run') == 42859288599 and
                pin.get('release_authorized') is False and
                pin.get('device_runtime_qualified') is False,
                'source baseline or release boundary drift')
    except ValueError:
        problems.append('malformed source baseline receipt')
    for check in ('class InstallBundlePlan', 'resolveInstallBundlePlan',
                  'expectedPackageName != packageName', 'versionCode != versionCode',
                  'No compatible ABI configuration split',
                  'Bundle requires exactly one unambiguous base APK',
                  'Multiple APK splits for the same ABI',
                  'Invalid APK member path',
                  'validateObbFileNames', 'isConfigurationSplitApk'):
        require(check in planner, f'install-plan validation missing: {check}')
    require(planner.count('minSdkVersion! > deviceSdkVersion') == 2,
            'base and split minimum Android API gates both mandatory')
    for check in ('_inspectInstallBundle(', 'resolveInstallBundlePlan(',
                  'plan.baseApkPath', 'plan.configApkPaths',
                  'expectedPackageName: dir.appId', 'validateObbFileNames(',
                  'FileSystemEntity.typeSync(file.path, followLinks: false)',
                  'apkFiles.add(file)', 'obbFiles.add(file)',
                  'if (wasInstalled)', 'await moveObbFile(obb, plan.packageName)',
                  'await dir.extracted.delete(recursive: true)',
                  'installArtifactFormat(originalAssetName)',
                  'originalSplits.difference(retained).isNotEmpty',
                  'extracted.deleteSync(recursive: true)'):
        require(check in provider, f'R02 install source integration missing: {check}')
    require(archive_inventory_cleanup_intact(provider),
            'invalid archive inventory must delete published extraction and rethrow')
    require('_preferMatchingApk(' not in provider,
            'legacy lossy first-APK selector resurrected')
    require('await moveObbFile(file, dir.appId)' not in provider,
            'OBB pre-install side effect resurrected')
    require('apks[0]' not in provider and 'apkFiles[0]' not in provider,
            'install still selects an arbitrary first archive member')
    require('DownloadedDirType { xapk, apks, apkm, zip, tarball }' in app,
            'APKS/APKM type mapping removed')
    require("'.tar'" in formats, 'raw TAR extension support removed')
    require(tests.count("test('") >= 19, 'adversarial R02 tests removed')
    for check in ('cross', 'arm64', 'x86_64', 'OBB', 'split version mismatch',
                  'missing', 'SDK', 'comma', 'standalone', 'unsupported'):
        # The tests differ in phrasing; test case inventory is also audited
        # through count and actual execution on hosted Flutter.
        if check in ('cross', 'unsupported'):
            continue
        require(check.lower() in tests.lower(), f'R02 fixture coverage missing: {check}')
    require('flutter test --no-pub test/r02_install_bundle_plan_test.dart' in flutter and
            'flutter analyze lib test' in flutter and 'flutter test --no-pub --reporter expanded' in flutter and
            'flutter build apk --debug --flavor normal --no-pub' in flutter,
            'hosted Flutter qualification not mandatory')
    require('python3 scripts/ci/r02_install_contract.py --check' in contracts and
            "python3 -m unittest discover -s scripts/ci -p 'test_*.py' -v" in contracts,
            'source contracts missing from hosted push/PR CI')
    require('NO PUBLIC RELEASE QUALIFIED' in release,
            'release forbidden-state assertion removed')
    return problems


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check', action='store_true')
    p.parse_args()
    issues=inspect()
    for issue in issues:
        print('OX_R02_CONTRACT_FAIL:',issue)
    if issues:
        return 1
    print('OX_R02_SOURCE_CONTRACT_PASS')
    print('OX_R02_DEVICE_RUNTIME=NOT_QUALIFIED')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
