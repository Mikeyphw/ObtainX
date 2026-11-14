"""P04B source mutations; these tests never claim Android runtime acceptance."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
S=importlib.util.spec_from_file_location('r02f_p04b_contract',ROOT/'scripts/ci/r02f_p04b_contract.py')
assert S and S.loader
C=importlib.util.module_from_spec(S);S.loader.exec_module(C)

class P04BMutations(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix='ox-p04b-negative-');self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        for path in C.PATHS:
            target=self.root/path;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/path,target)
    def mutate(self,path,old,new):
        f=self.root/path;s=f.read_text()
        self.assertEqual(s.count(old),1,'not a unique P04B negative anchor')
        f.write_text(s.replace(old,new,1))
        self.assertTrue(C.inspect(self.root),'unsafe P04B mutation not rejected')
    def test_00_valid(self):self.assertEqual(C.inspect(self.root),[])
    def test_01_no_host_only_install_bypass(self):
        self.mutate(C.DART,'installApkViaThirdParty(', 'installApkViaUnverifiedTestShim(')
    def test_02_no_false_dart_success(self):
        self.mutate(C.DART,'expect(result.isSuccess, isFalse)','expect(result.isSuccess, isTrue)')
    def test_03_cannot_ignore_returned_bridge(self):
        self.mutate(C.DART,'expect(bridge, isFalse','expect(bridge, isTrue')
    def test_04_no_wrong_target_component(self):
        self.mutate(C.DART,'targetActivity: _targetActivity','targetActivity: null')
    def test_05_no_ignored_receiver_receipt(self):
        self.mutate(C.HOST,'observed=target_receipt()','observed={"status":"received_and_declined","sha256":"0"*64}')
    def test_06_no_missing_device_baseline(self):
        self.mutate(C.HOST,'after=rt02c.baseline_v1(fx)','after=before')
    def test_07_no_missing_signed_target_pin(self):
        self.mutate(C.HOST,'sha(fx/target.APK)==tv.get(\'sha256\')','True')
    def test_08_no_runtime_contract_drop(self):
        self.mutate(C.WORKFLOW,'python3 -B scripts/ci/r02f_p04b_hosted.py run --out','echo skip_p04b_runtime')
    def test_09_no_verify_contract_drop(self):
        self.mutate(C.WORKFLOW,'python3 -B scripts/ci/r02f_p04b_hosted.py verify --out','echo skip_p04b_verify')
    def test_10_no_private_log_upload(self):
        self.mutate(C.HOST,"'raw_logs_uploaded':False","'raw_logs_uploaded':True")
    def test_11_no_false_external_positive(self):
        self.mutate(C.HOST,"'external_positive_install_qualified':False","'external_positive_install_qualified':True")
    def test_12_no_installer_install_privileges(self):
        self.mutate(C.TARGET,'can_install_apks\':False','can_install_apks\':True')
    def test_13_no_root_in_receiver(self):
        self.mutate(C.TARGET,'getSharedPreferences("p04b", MODE_PRIVATE)',
                    'Runtime.getRuntime().exec("su"); getSharedPreferences("p04b", MODE_PRIVATE)')
    def test_14_no_missing_ci_signing_guard(self):
        self.mutate(C.TARGET,'GITHUB_ACTIONS','GITHUB_DISABLED')
    def test_15_no_instant_focus_transition(self):
        self.mutate(C.TARGET, '}, 1500L);', '}, 0L);')
    def test_16_no_unknown_false_qualification_doc(self):
        self.mutate(C.DOC,'**NOT_QUALIFIED** for positive','**PASSED** for positive')
if __name__=='__main__':unittest.main()
