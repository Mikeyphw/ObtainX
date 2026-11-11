#!/usr/bin/env python3
"""Fail-closed qualification and CI-cost controls for ObtainX RT02F OPT01.

Source-only assurance; this script never certifies Android runtime behavior.
"""
from __future__ import annotations
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = '.github/workflows/obtainx-r00-contracts.yml'
FLUTTER = '.github/workflows/obtainx-r00-flutter.yml'
HEAVY = (
    '.github/workflows/obtainx-r02-api36.yml',
    '.github/workflows/obtainx-r02-rt02.yml',
    '.github/workflows/obtainx-r02-rt02b.yml',
    '.github/workflows/obtainx-r02-rt02c.yml',
)
FILES = (SOURCE, FLUTTER, *HEAVY)
POLICY = 'scripts/ci/obtainx_ci_policy.py'
RISK = 'scripts/ci/*optimization*'
LABEL = 'ci:development-only'
EVENT_TYPES = 'types: [opened, reopened, synchronize, labeled, unlabeled]'
DEFER_EXPR = "github.event_name != 'pull_request' || !contains(github.event.pull_request.labels.*.name, 'ci:development-only')"
REFUSE_EXPR = "github.event_name == 'pull_request' && contains(github.event.pull_request.labels.*.name, 'ci:development-only')"
UPLOAD = 'actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02'
EMULATOR = 'ReactiveCircus/android-emulator-runner@a421e43855164a8197daf9d8d40fe71c6996bb0d'


def inspect(root: Path = ROOT) -> list[str]:
    errors=[]
    files={}
    for rel in FILES:
        p=root/rel
        if not p.is_file() or p.is_symlink():
            errors.append('missing or symlinked protected workflow: '+rel)
            files[rel]=''
        else:
            files[rel]=p.read_text(encoding='utf8')
    source=files[SOURCE]
    flutter=files[FLUTTER]
    policy_path=root/POLICY
    policy=policy_path.read_text(encoding='utf8') if policy_path.is_file() and not policy_path.is_symlink() else ''
    if not policy or "'"+RISK+"'" not in policy:
        errors.append('CI optimization Python changes must be classified as high-risk')
    for rel,content in files.items():
        if EVENT_TYPES not in content:
            errors.append('label add/remove must rerun checks: '+rel)
        if '  workflow_dispatch:' not in content or 'permissions:\n  contents: read' not in content:
            errors.append('manual full gate or read-only permission missing: '+rel)
        if 'cancel-in-progress: true' not in content:
            errors.append('obsolete PR run cancellation missing: '+rel)
    # Keep the RED development-only guard on the SAME source-contracts runner.
    # A separate runner-only refusal job can remain indefinitely queued.
    guard_name='      - name: Development-only cannot qualify (same runner)\n'
    contract_step=('      - name: Enforce bounded CI optimization and dev-only qualification guard\n'
                   '        run: python3 -B scripts/ci/obtainx_ci_optimization_contract.py --check\n')
    guarded=source.split(guard_name,1)[1] if source.count(guard_name)==1 else ''
    if (source.count('  source-contracts:')!=1 or
            '  development-only-not-qualified:' in source or
            source.count(guard_name)!=1 or
            source.count(contract_step)!=1 or
            source.find(guard_name)<source.find(contract_step) or
            '        if: ${{ '+REFUSE_EXPR+' }}\n' not in guarded or
            'OX_CI_DEVELOPMENT_ONLY_NOT_QUALIFIED' not in guarded or
            '          exit 1\n' not in guarded or
            '  runs-on: ubuntu-24.04' not in source):
        errors.append('development-only guard must be RED at end of source-contracts on same runner')
    if 'python3 -B scripts/ci/obtainx_ci_optimization_contract.py --check' not in source or \
            "python3 -m unittest discover -s scripts/ci -p 'test_*.py' -v" not in source:
        errors.append('optimization/security source tests must be mandatory')
    if "needs.scope.outputs.full_flutter == 'true' && !contains(github.event.pull_request.labels.*.name, 'ci:development-only')" not in flutter:
        errors.append('full Flutter must be deferred only with explicit development-only label')
    if 'needs.scope.outputs.targeted_flutter' not in flutter or \
            'flutter test --no-pub test/archive_extraction_security_test.dart' not in flutter or \
            'flutter test --no-pub --reporter expanded' not in flutter or \
            'flutter build apk --debug --flavor normal --no-pub' not in flutter:
        errors.append('full/targeted Flutter and security/compile paths must remain intact')
    for rel in HEAVY:
        content=files[rel]
        if DEFER_EXPR not in content or \
                '    if: ${{ '+DEFER_EXPR+' }}' not in content:
            errors.append('Android gate not conditionally deferred safely: '+rel)
        if '  pull_request:\n    paths:' not in content or \
                ".github/workflows/**'" not in content:
            errors.append('high-risk Android PR path trigger lost: '+rel)
        if "      - '"+RISK+"'" not in content:
            errors.append('CI optimizer source change could skip Android gate: '+rel)
        if content.count(EMULATOR)!=1 or 'api-level: 36' not in content:
            errors.append('exact pinned API36 emulator changed or duplicated: '+rel)
        if content.count(UPLOAD)!=1 or \
                '      - name: Publish minimized emulator-only evidence even on failure\n        if: always()\n        timeout-minutes: 3\n' not in content or \
                'if-no-files-found: warn' not in content:
            errors.append('mandatory bounded evidence upload missing: '+rel)
        if 'Record only bounded receipt hashes before artifact upload' not in content or \
                'GITHUB_STEP_SUMMARY' not in content or 'sha256sum' not in content or \
                'if: always()' not in content:
            errors.append('bounded evidence fallback summary missing: '+rel)
        # Source-pinned Java 21 Gradle cache parity is an optimization ONLY;
        # keep fresh disposable emulator, APK fixtures and independent receipts.
        java_start='      - name: Set up Java 21\n'
        java=(content.split(java_start,1)[1].split('\n      - name:',1)[0]
              if content.count(java_start)==1 else '')
        cache_parts=(
            'actions/setup-java@cf277c60eb25467037889841efdb72551f06f6c3',
            "java-version: '21'",
            '          cache: gradle\n',
            '          cache-dependency-path: |\n',
            '            android/gradle/wrapper/gradle-wrapper.properties\n',
            '            android/**/*.gradle*',
        )
        if not java or any(java.count(k)!=1 for k in cache_parts):
            errors.append('pinned Gradle cache parity missing or altered: '+rel)
        if 'continue-on-error: true' in content:
            errors.append('unsafe Android CI failure suppression detected: '+rel)
    return errors


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check',action='store_true')
    p.parse_args()
    errors=inspect()
    for error in errors:
        print('OX_CI_OPT01_REFUSED: '+error,flush=True)
    if errors:
        return 1
    print('OX_CI_OPT01_SOURCE_PASS DEV_ONLY=NOT_QUALIFIED FULL_ANDROID=MANDATORY_ON_LABEL_REMOVAL',flush=True)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
