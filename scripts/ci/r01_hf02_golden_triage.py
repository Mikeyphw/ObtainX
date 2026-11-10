#!/usr/bin/env python3
"""Fail-closed classifier for a known preexisting golden-platform drift.

Never updates goldens itself. It authorizes emitting review *artifacts* only
when the entire Flutter full-suite failure consists of exactly the two app-row
appearance tests. This does not turn the hosted test run green.
"""
from __future__ import annotations
import json
from pathlib import Path
import re
import sys

EXPECTED = {
    'row appearance is preserved with reduced effects false',
    'row appearance is preserved with reduced effects true',
}
TARGET = 'test/apps_scroll_work_test.dart'


def classify(text: str) -> dict:
    text=re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', text).replace('\r','\n')
    failures=[]
    # The expanded Flutter test reporter includes one [E] status per failed test.
    for line in text.splitlines():
        if not re.search(r'\[E\]\s*$', line):
            continue
        match=re.search(r'(test/\S+\.dart):\s*(.+?)\s*\[E\]\s*$', line)
        if not match:
            raise ValueError('Unclassified Flutter test error: '+line[-350:])
        failures.append((match.group(1),match.group(2).strip()))
    if len(failures)!=2 or set(failures)!={(TARGET,name) for name in EXPECTED}:
        raise ValueError('Unrelated or missing failures: '+repr(failures)[:900])
    if text.count('Golden "goldens/app-row-')!=6:
        raise ValueError('Unexpected golden-failure count or missing golden evidence')
    # Flutter's expanded reporter includes a skipped-test counter only when
    # nonzero: "+823 ~1 -2: Some tests failed."  A previous parser accepted
    # "+823 -2" but rejected this legitimate, fully accounted-for result.
    # Count the FINAL reporter summary, not an incidental "-2" in a test line.
    progress = re.findall(
        r'(?m)^\d{2}:\d{2}\s+\+\d+(?:\s+~\d+)?\s+-(\d+):\s+Some tests failed\.\s*$',
        text,
    )
    prose = re.findall(
        r'(?m)^\d+ tests passed, (\d+) failed(?:, \d+ skipped)?\.\s*$',
        text,
    )
    if len(progress) + len(prose) != 1 or (progress + prose) != ['2']:
        raise ValueError('Full-suite failure total not exactly 2')
    if not ('Pixel test failed' in text and 'app-row-swiping' in text):
        raise ValueError('Golden mismatch evidence incomplete')
    return {'schema':1,'classification':'GOLDEN_ONLY_FAILURE','expected_failures':sorted(EXPECTED),
            'required_golden_count':6,'full_suite_passed':False,'other_test_failures':0}


def main(argv: list[str]) -> int:
    if len(argv)!=3:
        print('Usage: r01_hf02_golden_triage.py <flutter-full-suite.log> <review.json>',file=sys.stderr)
        return 2
    try:
        result=classify(Path(argv[1]).read_text(errors='replace'))
        output=Path(argv[2]);output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
        print('OX_R01_HF02_GOLDEN_ONLY_FAILURE_VERIFIED',json.dumps(result,sort_keys=True))
        return 0
    except (OSError,ValueError) as e:
        print('OX_R01_HF02_GOLDEN_TRIAGE_REFUSED:',str(e),file=sys.stderr)
        return 1

if __name__=='__main__':
    raise SystemExit(main(sys.argv))
