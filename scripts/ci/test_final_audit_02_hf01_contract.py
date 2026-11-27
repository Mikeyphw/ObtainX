"""Repeat every direct source-contract check from the hosted source lane.

Unit-test-only qualification missed a separately invoked production contract.
The tests below preserve the actual hosted commands, with an independent
source-level guard for the four recorded analyzer diagnostics.
"""
from pathlib import Path
import os
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]


class FinalAudit02HF01Contract(unittest.TestCase):
    def test_all_hosted_source_contract_commands(self):
        workflow = (ROOT / '.github/workflows/obtainx-r00-contracts.yml').read_text()
        commands = re.findall(r'^\s*run: python3 (?:-B )?(scripts/ci/[a-z0-9_]+\.py) --check\s*$', workflow, re.M)
        self.assertIn('scripts/ci/r04_completion_contract.py', commands)
        self.assertGreaterEqual(len(commands), 25)
        self.assertEqual(len(commands), len(set(commands)))
        for script in commands:
            with self.subTest(script=script):
                result = subprocess.run([sys.executable, '-B', script, '--check'], cwd=ROOT,
                                        capture_output=True, text=True, timeout=60,
                                        env={**os.environ, 'PYTHONPATH': str(ROOT / 'scripts/ci'),
                                             'PYTHONSAFEPATH': '1'})
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_selected_archive_digest_stays_mandatory_and_bound(self):
        text = (ROOT / 'lib/app_sources/github.dart').read_text()
        start = text.index('if (archive.archiveSha256 == null)')
        refusal = text.index('throw const R04ActionsFailure(', start)
        checked = text.index('final archiveDigest = archive.archiveSha256!;', refusal)
        evidence = text.index("'archiveSha256': archiveDigest,", checked)
        candidate = text.index('SourceAssetDigest(candidate.key, candidate.value, archiveDigest)', evidence)
        self.assertLess(start, refusal)
        self.assertLess(refusal, checked)
        self.assertLess(checked, evidence)
        self.assertLess(evidence, candidate)

    def test_analyzer_regression_sites(self):
        resource = (ROOT / 'lib/services/artifact_resource_budget.dart').read_text()
        self.assertFalse(resource.startswith('///'))
        timeline = (ROOT / 'lib/services/r07_operation_timeline.dart').read_text()
        self.assertIn("'o.finished = 1'", timeline)
        history = (ROOT / 'lib/services/r11_history.dart').read_text()
        for record in ('download', 'timeline'):
            self.assertIn(f'if (record.{record} != null) {{\n    return {{', history)


if __name__ == '__main__':
    unittest.main()
