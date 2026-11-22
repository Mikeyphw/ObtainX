#!/usr/bin/env python3
"""R02 HF02 source and CI regression audit (not Android runtime acceptance)."""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def inspect(root: Path = ROOT) -> list[str]:
    problems: list[str] = []
    def read(relative: str) -> str:
        file = root / relative
        if not file.is_file() or file.is_symlink():
            problems.append(f'missing or linked source: {relative}')
            return ''
        return file.read_text(encoding='utf-8')

    app = read('lib/providers/apps_provider_install.dart')
    planner = read('lib/services/install_bundle_plan.dart')
    flutter = read('.github/workflows/obtainx-r00-flutter.yml')
    contracts = read('.github/workflows/obtainx-r00-contracts.yml')
    legacy_contract = read('scripts/ci/r01_hf02_contract.py')
    legacy_tests = read('scripts/ci/test_r01_hf02_contract.py')
    audit = read('docs/R02_HF02_ANALYZER_RECOVERY.md')

    def check(ok: bool, message: str) -> None:
        if not ok:
            problems.append(message)

    check('if (apps[resolvedAppId]?.installedInfo == null) {' in app,
          'icon extraction must remain gated on absent installed package')
    check('await storeIconFromApkArchive(resolvedAppId, parsedArchivePath);' in app,
          'icon extraction must still use the parsed APK path')
    check('if (parsedArchivePath != null &&' not in app,
          'obsolete nullable path assertion reintroduced')
    check('final selectedConfig = [...nonAbi, ?abiMember, ...selectedLocales, ?densityMember]' in planner,
          'null-aware split selection marker missing')
    check('if (abiMember != null) abiMember' not in planner,
          'stale Dart collection-if source reintroduced')
    check("throw const FormatException('No compatible ABI configuration split');" in planner,
          'mandatory incompatible ABI rejection missing')
    check('id: full_flutter_tests' in flutter and
          "if: ${{ failure() && steps.full_flutter_tests.outcome == 'failure' }}" in flutter,
          'golden triage must depend on actual failed full suite')
    check('flutter analyze lib test' in flutter and
          'flutter test --no-pub test/r02_install_bundle_plan_test.dart' in flutter and
          'flutter test --no-pub --reporter expanded' in flutter and
          'flutter build apk --debug --flavor normal --no-pub' in flutter,
          'hosted analyze, R02 test, full suite or APK build gate weakened')
    check('if: ${{ failure() && steps.golden_triage.outcome == \'success\' }}' in flutter and
          'flutter test --no-pub --update-goldens test/apps_scroll_work_test.dart' in flutter,
          'guarded visual review flow missing')
    check("steps.full_flutter_tests.outcome == 'failure'" in legacy_contract,
          'inherited HF02 golden workflow contract stale')
    check('test_golden_triage_after_analyzer_failure_refused' in legacy_tests and
          'test_full_suite_step_id_removal_refused' in legacy_tests,
          'inherited HF02 negative tests stale')
    check('python3 scripts/ci/r02_hf02_contract.py --check' in contracts and
          "python3 -m unittest discover -s scripts/ci -p 'test_*.py' -v" in contracts,
          'hosted mandatory HF02 source contract or mutation test missing')
    check('NO RELEASE' in audit and 'NOT' in audit,
          'HF02 release/device boundary documentation missing')
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.parse_args()
    issues = inspect()
    for issue in issues:
        print('OX_R02_HF02_CONTRACT_FAIL:', issue)
    if issues:
        return 1
    print('OX_R02_HF02_CONTRACT_PASS')
    print('OX_R02_ANDROID_RUNTIME=NOT_QUALIFIED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
