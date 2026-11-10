"""HF02 contract mutation and triage rejection tests."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
def module(rel):
    path=ROOT/rel
    spec=importlib.util.spec_from_file_location(Path(rel).stem,path)
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj
C=module('scripts/ci/r01_hf02_contract.py')
T=module('scripts/ci/r01_hf02_golden_triage.py')

class HF02(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ox-hf02-')
        self.root=Path(self.temp.name)
        paths=[*C.MOCKS,C.WORKFLOW,'pubspec.lock','test/apps_scroll_work_test.dart',
               'scripts/ci/r01_hf02_golden_triage.py','docs/R01_HF02_FULL_SUITE_AUDIT.md']
        for rel in paths:
            dest=self.root/rel;dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/rel,dest)
    def tearDown(self):self.temp.cleanup()
    def mutate(self,rel,old,new):
        path=self.root/rel
        s=path.read_text();self.assertIn(old,s)
        path.write_text(s.replace(old,new,1))
    def test_valid(self):self.assertEqual(C.inspect(self.root),[])
    def test_missing_build_time_refused(self):
        self.mutate('test/source_provider_test.dart',"'time': 0","'notTime': 0")
        self.assertTrue(any('Build.TIME' in s for s in C.inspect(self.root)))
    def test_missing_flutter_tests_refused(self):
        self.mutate(C.WORKFLOW,'flutter test --no-pub --reporter expanded','echo skipped')
        self.assertTrue(C.inspect(self.root))
    def test_unconditional_golden_updates_refused(self):
        self.mutate(C.WORKFLOW,'if: ${{ failure() }}','if: ${{ always() }}')
        self.assertTrue(C.inspect(self.root))
    def test_golden_matchers_must_remain(self):
        self.mutate('test/apps_scroll_work_test.dart','matchesGoldenFile(','neverMatch(',)
        self.assertTrue(C.inspect(self.root))
    def test_rejects_unrelated_behavior_failure(self):
        data='00:21 +810 -2: test/source_provider_test.dart: ABI failure [E]\nGolden "goldens/app-row-false.png": Pixel test failed\n2 failed\n'
        with self.assertRaises(ValueError):T.classify(data)
    def test_rejects_absent_golden_evidence(self):
        data='\n'.join('00:21 +810 -2: test/apps_scroll_work_test.dart: '+s+' [E]' for s in sorted(T.EXPECTED))+'\n2 failed\n'
        with self.assertRaises(ValueError):T.classify(data)
    def test_exact_golden_only_evidence(self):
        data='\n'.join('00:21 +810 -2: test/apps_scroll_work_test.dart: '+s+' [E]' for s in sorted(T.EXPECTED))+'\n'+\
            'Golden "goldens/app-row-x.png": Pixel test failed\n'*6+'app-row-swiping\n2 failed\n'
        self.assertEqual(T.classify(data)['classification'],'GOLDEN_ONLY_FAILURE')

if __name__=='__main__':unittest.main()
