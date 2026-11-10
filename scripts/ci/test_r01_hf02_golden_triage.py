"""Negative and positive examples for HF02 golden-only classifier."""
from pathlib import Path
import importlib.util
import unittest

p=Path(__file__).with_name('r01_hf02_golden_triage.py')
spec=importlib.util.spec_from_file_location('r01_hf02_golden_triage',p)
t=importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)

def runlog(failures=None,diffcount=6,count=2):
    if failures is None:failures=sorted(t.EXPECTED)
    return ('\n'.join(f'00:29 +810 -{count}: test/apps_scroll_work_test.dart: {name} [E]'
                      for name in failures)+'\n'+
            ('Golden "goldens/app-row-false.png": Pixel test failed\n'*diffcount)+
            'app-row-swiping\n'
            f'810 tests passed, {count} failed, 1 skipped.\n')

class GoldenTriage(unittest.TestCase):
    def test_expected_is_accepted(self):
        data=t.classify(runlog())
        self.assertEqual(data['classification'],'GOLDEN_ONLY_FAILURE')
        self.assertFalse(data['full_suite_passed'])
    def test_flutter_expanded_reporter_end_marker(self):
        data=runlog().replace('810 tests passed, 2 failed, 1 skipped.',
                              '00:41 +810 -2: Some tests failed.')
        self.assertEqual(t.classify(data)['other_test_failures'],0)
    def test_behavioral_failure_added_refused(self):
        s=runlog()+'00:30 +810 -3: test/source_provider_test.dart: ABI regression [E]\n'
        with self.assertRaises(ValueError):t.classify(s)
    def test_golden_evidence_missing_refused(self):
        with self.assertRaises(ValueError):t.classify(runlog(diffcount=5))
    def test_success_cannot_be_called_golden_failure(self):
        with self.assertRaises(ValueError):t.classify(runlog(count=0))
    def test_changed_case_refused(self):
        with self.assertRaises(ValueError):t.classify(runlog(failures=['row appearance is preserved with reduced effects false']))

if __name__=='__main__':unittest.main()
