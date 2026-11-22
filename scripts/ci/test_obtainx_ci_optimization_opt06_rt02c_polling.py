"""OPT06 adversarial phase/clock regressions and protected source anchors."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import tempfile
import shutil
import unittest

ROOT = Path(__file__).resolve().parents[2]
HELPER = 'scripts/ci/obtainx_ci_optimization_opt06_rt02c_polling.py'
SESSION = 'scripts/ci/r02_rt02c_single_session.py'
CONTRACT = 'scripts/ci/r02_rt02c_contract.py'

spec=importlib.util.spec_from_file_location('opt06_polling',ROOT/HELPER)
P=importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)


class ProbeSafety(unittest.TestCase):
    def test_first_probe_always_immediate(self):
        for phase in ('GRADLE_BUILD','FLUTTER_STARTING','TEST_APK_INSTALL',
                      'DART_TEST_STARTED','STOCK_INSTALLER_CALL'):
            self.assertTrue(P.should_probe_runner(0.0,None,phase))

    def test_only_gradle_probe_suppressed(self):
        for phase in ('FLUTTER_STARTING','TEST_APK_INSTALL','DART_TEST_STARTED',
                      'STOCK_INSTALLER_CALL','STOCK_INSTALLER_RETURNED',
                      'ANDROID_V2_SPLIT_VERIFIED','PREINSTALL_REFUSED'):
            self.assertTrue(P.should_probe_runner(100.1,100.0,phase),phase)

    def test_gradle_cadence_exact_boundary(self):
        self.assertFalse(P.should_probe_runner(107.999,100.0,'GRADLE_BUILD'))
        self.assertTrue(P.should_probe_runner(108.0,100.0,'GRADLE_BUILD'))
        self.assertTrue(P.should_probe_runner(109.0,100.0,'GRADLE_BUILD'))

    def test_gradle_long_compile_has_bounded_probes(self):
        last=None; actual=[]
        for second in range(205):
            if P.should_probe_runner(float(second),last,'GRADLE_BUILD'):
                last=float(second);actual.append(second)
        self.assertEqual(actual,list(range(0,205,8)))
        self.assertLessEqual(len(actual),26)

    def test_immediate_exit_gradle_transition(self):
        self.assertFalse(P.should_probe_runner(102.,100.,'GRADLE_BUILD'))
        self.assertTrue(P.should_probe_runner(102.,100.,'TEST_APK_INSTALL'))
        self.assertTrue(P.should_probe_runner(102.,100.,'DART_TEST_STARTED'))

    def test_monotonic_clock_rollback_refused(self):
        with self.assertRaises(ValueError):P.should_probe_runner(98.,100.,'GRADLE_BUILD')

    def test_nonfinite_clock_refused(self):
        for number in (float('inf'),float('nan'),-1.,True,'3'):
            with self.subTest(number=number):
                with self.assertRaises(ValueError):P.should_probe_runner(number,None,'GRADLE_BUILD')

    def test_nonfinite_prior_refused(self):
        for value in (float('inf'),float('nan'),-1.,False,'3'):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):P.should_probe_runner(100.,value,'GRADLE_BUILD')

    def test_invalid_phase_refused(self):
        for value in ('',None,3,{},False):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):P.should_probe_runner(3.,2.,value)

    def test_probe_statistics_are_not_qualification(self):
        s=(ROOT/SESSION).read_text('utf8')
        self.assertIn("self.receipt['runner_probe_count'] = self.runner_probe_count",s)
        self.assertIn("self.receipt['runner_probe_skipped'] = self.runner_probe_skipped",s)
        self.assertIn('should_probe_runner(now, self.runner_probe_last, runner_stage)',s)
        self.assertIn("self.base.adb('shell', 'appops', 'set', self.base.APP,",s)
        self.assertIn('self.base._tap_confirmed_install_dialog()',s)
        self.assertIn('self.base.installed_state(2, True, self.fixtures)',s)

    def test_contract_refuses_missing_probe_integration(self):
        spec=importlib.util.spec_from_file_location('opt06_rt02c_contract',ROOT/CONTRACT)
        contract=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(contract)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for rel in contract.PATHS:
                dest=root/rel
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/rel,dest)
            self.assertEqual(contract.inspect(root),[])
            sess=root/SESSION
            txt=sess.read_text('utf8')
            self.assertIn('should_probe_runner(now, self.runner_probe_last, runner_stage)',txt)
            sess.write_text(txt.replace('should_probe_runner(now, self.runner_probe_last, runner_stage)','True',1))
            self.assertTrue(contract.inspect(root))

    def test_contract_refuses_removed_helper(self):
        spec=importlib.util.spec_from_file_location('opt06_rt02c_contract_missing',ROOT/CONTRACT)
        contract=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(contract)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for rel in contract.PATHS:
                dest=root/rel
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/rel,dest)
            (root/HELPER).unlink()
            self.assertTrue(any(HELPER in err for err in contract.inspect(root)))


if __name__=='__main__':unittest.main()
