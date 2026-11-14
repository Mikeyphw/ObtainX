"""P04 backend source-level mutation tests; no root, device owner or ADB."""
from __future__ import annotations
import importlib.util,shutil,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('p04_backend_contract',ROOT/'scripts/ci/r02f_p04_backend_contract.py')
assert SPEC and SPEC.loader
C=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(C)
class ContractMutations(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix='ox-p04-backend-');self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        for name in C.PATHS:
            f=self.root/name;f.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/name,f)
    def mutate(self,name,old,new):
        f=self.root/name;s=f.read_text();self.assertIn(old,s)
        f.write_text(s.replace(old,new,1))
        self.assertTrue(C.inspect(self.root), 'unsafe mutation escaped '+name)
    def test_00_valid(self):self.assertEqual(C.inspect(self.root),[])
    def test_01_no_auth_flag_removal(self):
        self.mutate(C.MODEL,'userInitiated && hostedApi36 && signedDisposableFixture',
                           'true')
    def test_02_no_success_forgery(self):
        self.mutate(C.MODEL,'bool get canClaimInstallSuccess => false;',
                           'bool get canClaimInstallSuccess => true;')
    def test_03_no_release_forgery(self):
        self.mutate(C.MODEL,'bool get releaseQualified => false;',
                           'bool get releaseQualified => true;')
    def test_04_no_wrong_backend_escalation(self):
        self.mutate(C.MODEL,'P04BackendState.wrongBackendPermission',
                           'P04BackendState.authorizedUnqualified')
    def test_05_no_prompt_without_user(self):
        self.mutate(C.PLUGIN,'if (!userInitiated)','if (false)')
    def test_06_no_missing_sdk_probe(self):
        self.mutate(C.HOST,'base.host_check()', 'base.identity_check()')
    def test_07_no_fake_install_claim(self):
        self.mutate(C.HOST,"'backend_install_qualified':False", "'backend_install_qualified':True")
    def test_08_no_missing_original_positive(self):
        self.mutate(C.CI,'python3 -B scripts/ci/r02f_p04b_p03_hosted.py run --out',
                          'python3 -B scripts/ci/simulated.py run --out')
    def test_09_no_prereq_scope_release(self):
        self.mutate(C.DOC,'NOT_QUALIFIED','QUALIFIED')
    def test_10_no_original_backend_scope(self):
        self.mutate(C.MATRIX,'**NOT_AVAILABLE / NOT_QUALIFIED**', '**PASS**')
    def test_11_no_worker_test_skip(self):
        self.mutate(C.DART,'OX_P04_DHIZUKU_REAL_ABSENCE_PASS','DISABLED')
    def test_12_no_missing_native_receipt(self):
        self.mutate(C.CI,'r02f-p04-backend-availability.json','disabled.json')
    def test_13_no_qualifying_physical(self):
        self.mutate(C.MODEL,'bool get physicalDeviceQualified => false;',
                          'bool get physicalDeviceQualified => true;')
if __name__=='__main__':unittest.main()
