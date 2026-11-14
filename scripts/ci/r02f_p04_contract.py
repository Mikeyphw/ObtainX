#!/usr/bin/env python3
"""R02F P04A fail-closed broadcast provenance contract; NOT Android runtime proof."""
from __future__ import annotations
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROVIDER = 'lib/providers/apps_provider_install.dart'
BRIDGE = 'lib/providers/installer_provider.dart'
EXTERNAL = 'lib/installers/external_installer.dart'
CLASSIFY = 'lib/services/third_party_install_evidence.dart'
STOCK = 'lib/installers/stock_installer.dart'
SHIZUKU = 'lib/installers/shizuku_installer.dart'
DHIZUKU = 'lib/installers/dhizuku_installer.dart'
DART_TEST = 'test/r02f_p04_backend_matrix_test.dart'
DOC = 'docs/R02F_P04_INSTALLER_BACKEND_MATRIX.md'
SOURCE_CI = '.github/workflows/obtainx-r00-contracts.yml'
PATHS = (PROVIDER, BRIDGE, EXTERNAL, CLASSIFY, STOCK, SHIZUKU, DHIZUKU,
         DART_TEST, DOC, SOURCE_CI)


def inspect(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    docs: dict[str, str] = {}
    for path in PATHS:
        f = root / path
        if not f.is_file() or f.is_symlink():
            errors.append('missing or linked P04 source ' + path)
            docs[path] = ''
        else:
            docs[path] = f.read_text('utf-8')
    p = docs[PROVIDER]
    label = 'Future<void> recordThirdPartyInstallBroadcast(String packageName) async {'
    start = p.find(label)
    end = p.find('  Future<void> _recordPendingInstall(', start) if start >= 0 else -1
    block = p[start:end] if start >= 0 and end > start else ''
    helper = p[p.find('bool p04PendingMatchesInstalledPackage('):p.find(label)]
    required = (
        'pending != null', 'pending.belongsTo(app)', 'pending.matchesPackage(installedInfo)',
        'installedInfo.packageName == app.id',
    )
    if not all(x in helper for x in required):
        errors.append('P04 exact pending source/package/version verification removed')
    if p.count('bool p04PendingMatchesInstalledPackage(') != 1:
        errors.append('P04 helper missing or duplicated')
    for anchor in (
        'apps.values', 'entry.app.id == packageName',
        'installedInfo.packageName != packageName',
        'if (p04PendingMatchesInstalledPackage(entry.app, pending, installedInfo)) {',
        'recordConfirmedInstall(entry.app, pending, installedInfo)',
        'getCorrectedInstallStatusAppIfPossible(',
        'thirdPartyInstallIndicatorTimers.remove(listingKey)?.cancel();',
    ):
        if anchor not in block:
            errors.append('P04 broadcast scope/confirmation anchor missing ' + anchor)
    if 'final entry = apps[packageName];' in block:
        errors.append('P04 old single-listing broadcast handler was reintroduced')
    if (block.count('recordConfirmedInstall(') != 1 or
        block.find('if (p04PendingMatchesInstalledPackage(') > block.find('recordConfirmedInstall(') or
        block.find('if (p04PendingMatchesInstalledPackage(') < 0):
        errors.append('P04 recordConfirmedInstall bypasses validated pending receipt')
    if "classifyUnverifiedThirdPartyHandoff(changed)" not in docs[EXTERNAL]:
        errors.append('external installer no longer returns unverified handoff')
    if 'InstallResult.success()' in docs[CLASSIFY] or \
            'return InstallResult.handedOff();' not in docs[CLASSIFY]:
        errors.append('bridge change/timeout wrongly claims Android installation success')
    for path, mode in ((STOCK,'system'),(EXTERNAL,'external'),
                       (SHIZUKU,'shizuku'),(DHIZUKU,'dhizuku')):
        if ("String get modeKey => '"+mode+"';") not in docs[path]:
            errors.append('P04 installer strategy changed or missing '+mode)
    if 'launchInstallIntent' not in docs[BRIDGE] or \
            'expectedPackageName' not in docs[BRIDGE]:
        errors.append('third-party target/package correlation missing')
    tests = docs[DART_TEST]
    for marker in (
        "stale v1 package broadcast cannot confirm the requested v2",
        'same version number from another package cannot confirm',
        'missing intent cannot be upgraded by a spurious broadcast',
        'source change invalidates the old pending receipt',
        'wrong versionCode even with same versionName is not a match',
        'stock result codes are distinct from external handoff',
    ):
        if marker not in tests:
            errors.append('P04 Dart negative missing: '+marker)
    if 'p04PendingMatchesInstalledPackage(' not in tests:
        errors.append('P04 tests do not invoke production verifier')
    if '**NOT_QUALIFIED** for real external' not in docs[DOC] or \
            '**NOT_AVAILABLE / NOT_QUALIFIED**' not in docs[DOC] or \
            'P04B' not in docs[DOC]:
        errors.append('P04 absent binder/external/physical runtimes falsely qualified')
    if 'run: python3 -B scripts/ci/r02f_p04_contract.py --check' not in docs[SOURCE_CI]:
        errors.append('mandatory source workflow P04 guard missing')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.parse_args()
    issues = inspect()
    for issue in issues:
        print('OX_R02F_P04A_SOURCE_REFUSED: ' + issue)
    if issues:
        return 1
    print('OX_R02F_P04A_BROADCAST_PROVENANCE_AND_BACKEND_SCOPE_PASS; '
          'EXTERNAL_SHIZUKU_DHIZUKU_RUNTIME=NOT_QUALIFIED',flush=True)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
