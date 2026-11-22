"""RT02 HF07: source-bound split pre-Dart stall recovery tests (not emulator proof)."""
from __future__ import annotations
import importlib.util,inspect,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/ci'))
SPEC=importlib.util.spec_from_file_location('r02_rt02_hosted',ROOT/'scripts/ci/r02_rt02_hosted.py')
assert SPEC and SPEC.loader
H=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(H)

class PredartPolicy(unittest.TestCase):
    def test_only_split_first_attempt_predart_without_approval_retries(self):
        for phase in ('FLUTTER_STARTING','GRADLE_BUILD','TEST_APK_INSTALL'):
            self.assertTrue(H.split_pre_dart_recovery_allowed('split',1,phase,False,0))
            for wrong in [('standalone',1,phase,False,0),('split',2,phase,False,0),
                          ('split',1,phase,True,0),('split',1,phase,False,1),
                          ('split',1,phase,False,True)]:
                self.assertFalse(H.split_pre_dart_recovery_allowed(*wrong),wrong)
        for phase in ('STOCK_INSTALLER_CALL','STOCK_INSTALLER_RETURNED','ANDROID_PACKAGE_STATE_VERIFIED'):
            self.assertFalse(H.split_pre_dart_recovery_allowed('split',1,phase,False,0))

    def test_idle_watchdog_is_bounded_and_does_not_touch_dart(self):
        self.assertFalse(H.split_pre_dart_stalled('split',1,'TEST_APK_INSTALL',359,300))
        self.assertFalse(H.split_pre_dart_stalled('split',1,'TEST_APK_INSTALL',400,179))
        self.assertTrue(H.split_pre_dart_stalled('split',1,'TEST_APK_INSTALL',400,181))
        self.assertFalse(H.split_pre_dart_stalled('standalone',1,'TEST_APK_INSTALL',400,181))
        self.assertFalse(H.split_pre_dart_stalled('split',2,'TEST_APK_INSTALL',400,181))
        self.assertFalse(H.split_pre_dart_stalled('split',1,'STOCK_INSTALLER_CALL',400,181))

    def test_split_pre_dart_retries_only_with_exact_android_v1(self):
        source=inspect.getsource(H.one_scenario)
        self.assertIn("installed_state(1,False,out/'fixtures')",source)
        self.assertIn('split_pre_dart_recovery_allowed(',source)
        self.assertIn('terminate_flutter_process_group(p)',source)
        self.assertIn("adb('shell','am','force-stop',APP,timeout=20)",source)
        self.assertIn("record_flutter_failure(out,scenario,attempt,phase,logfile,-1)",source)
        self.assertIn('RT02_FLUTTER_TIMEOUT',source)
        self.assertIn('actual=installed_state(1 if scenario==\'standalone\' else 2',source)
        self.assertIn('approval_path=classify_android_approval(scenario,tap_count,actual)',source)
        self.assertNotIn('continue-on-error',source)

    def test_proof_precedes_any_dangerous_retry(self):
        s=inspect.getsource(H.one_scenario)
        self.assertLess(s.index("installed_state(1,False,out/'fixtures')"),
                        s.index('OX_R02_RT02_SPLIT_PRE_DART_RETRY'))
        self.assertLess(s.index('actual=installed_state('),s.index('approval_path=classify_android_approval('))
        self.assertIn('empty_or_expected_package()',s)
        self.assertIn('attempt==1 and not dart_started and tap_count==0',s)

if __name__=='__main__':unittest.main()
