#!/usr/bin/env python3
"""Explicit R01 HF02 stale fixture and CI contract (additive to R00/R01)."""
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
MOCKS=('test/source_provider_test.dart','test/version_order_test.dart','test/multi_source_app_actions_test.dart')
WORKFLOW='.github/workflows/obtainx-r00-flutter.yml'

def inspect(root: Path=ROOT) -> list[str]:
    problems=[]
    lock=root/'pubspec.lock'
    if not lock.exists() or not re.search(r'(?m)^  device_info_plus:.*?\n(?:.*\n){0,10}?    version: "13\.3\.0"',lock.read_text()):
        problems.append('Expected pinned device_info_plus 13.3.0 changed; re-audit test mocks')
    for rel in MOCKS:
        p=root/rel
        s=p.read_text() if p.is_file() else ''
        if not re.search(r"'time'\s*:\s*\d+",s):
            problems.append('DeviceInfo mock missing required int Build.TIME: '+rel)
        if s.count('BaseDeviceInfo({')!=1:
            problems.append('DeviceInfo mock shape changed: '+rel)
    p=root/WORKFLOW;s=p.read_text() if p.is_file() else ''
    must=('flutter analyze lib test','flutter test --no-pub --reporter expanded',
          'set -o pipefail','r01_hf02_golden_triage.py',
          'flutter test --no-pub --update-goldens test/apps_scroll_work_test.dart',
          'actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02',
          'obtainx-r01-hf02-golden-review-${{ github.event.pull_request.head.sha }}',
          "if: ${{ failure() && steps.golden_triage.outcome == 'success' }}",
          'flutter test --no-pub test/archive_extraction_security_test.dart',
          'flutter build apk --debug --flavor normal --no-pub')
    for needle in must:
        if needle not in s:problems.append('Required CI gate missing: '+needle)
    if 'if: ${{ failure() }}' not in s or 'id: golden_triage' not in s:
        problems.append('Diagnostic golden generation must be failure-only')
    golden=root/'test/apps_scroll_work_test.dart'
    if not golden.is_file() or golden.read_text().count('matchesGoldenFile(')!=3:
        problems.append('Strict app-row golden matcher was changed or removed')
    for rel in ('scripts/ci/r01_hf02_golden_triage.py','docs/R01_HF02_FULL_SUITE_AUDIT.md'):
        if not (root/rel).is_file(): problems.append('Missing HF02 audit artifact: '+rel)
    return problems

if __name__=='__main__':
    p=inspect()
    for item in p:print('OX_R01_HF02_CONTRACT_FAIL',item)
    if p:sys.exit(1)
    print('OX_R01_HF02_SOURCE_AND_STALE_FIXTURE_CONTRACT_PASS')
