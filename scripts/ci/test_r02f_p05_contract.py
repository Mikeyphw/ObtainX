"""R02F P05 source mutation refusals; no Android or personal device required."""
from __future__ import annotations
import importlib.util,shutil,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
S=importlib.util.spec_from_file_location('p05_contract',ROOT/'scripts/ci/r02f_p05_contract.py')
assert S and S.loader
C=importlib.util.module_from_spec(S);S.loader.exec_module(C)

class P05Mutations(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix='ox-p05-contract-');self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        for name in C.PATHS:
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/name,path)
    def mutate(self,path,old,new):
        p=self.root/path;s=p.read_text()
        self.assertIn(old,s,'P05 missing source mutation anchor '+path)
        p.write_text(s.replace(old,new,1))
        self.assertTrue(C.inspect(self.root),'P05 unsafe mutation escaped '+path)
        p.write_text(s)
        self.assertEqual(C.inspect(self.root),[])
    def test_00_valid(self):self.assertEqual(C.inspect(self.root),[])
    def test_01_no_sdk_guard_drop(self):
        self.mutate(C.MODEL,'sdk < 1','sdk < -10')
    def test_02_no_direct_obb_android_11(self):
        self.mutate(C.MODEL,'androidSdk < 30','androidSdk <= 36')
    def test_03_no_unknown_abi(self):
        self.mutate(C.MODEL,'supportedAbis.isEmpty','false')
    def test_04_no_sdk_envelope_skip(self):
        self.mutate(C.PROVIDER,'verifyP05SdkEnvelope(', 'ignoredP05SdkEnvelope(')
    def test_05_no_device_profile_skip(self):
        self.mutate(C.PROVIDER,'validateP05DeviceProfile(\n      sdk:', 'ignoredP05DeviceProfile(\n      sdk:')
    def test_06_no_symlink_destination_bypass(self):
        self.mutate(C.OBB,'_assertNoSymlinkAncestors(destinationFolder);', '// removed')
    def test_07_no_obb_source_sha_weaken(self):
        self.mutate(C.OBB,'sha256.bind(source.openRead()).first','source.length()')
    def test_08_no_obb_cancel_removed(self):
        self.mutate(C.OBB,'if (isCancelled?.call() ?? false)', 'if (false)')
    def test_09_no_emulator_identity(self):
        self.mutate(C.HOST,'base.host_check()','base.identity_check()')
    def test_10_no_fake_physical_qualification(self):
        self.mutate(C.HOST,"'physical_device_qualified':False","'physical_device_qualified':True")
    def test_11_no_source_contract_skip(self):
        self.mutate(C.R00,'python3 -B scripts/ci/r02f_p05_contract.py --check','echo P05 disabled')
    def test_12_no_flutter_negative_skip(self):
        self.mutate(C.FLUTTER,'flutter test --no-pub test/r02f_p05_obb_ancestor_test.dart',
                    'echo P05 OBB tests disabled')
    def test_13_no_receipt_upload_skip(self):
        self.mutate(C.RT02C,'r02f-p05-device-profile.json','disabled-p05.json')
    def test_14_no_broad_physical_probe(self):
        self.mutate(C.PHYSICAL,"'device_writes':False","'device_writes':True")
    def test_15_no_model_library_lint(self):
        self.mutate(C.MODEL,'library;\n','')
    def test_16_no_order_bypass(self):
        self.mutate(C.RT02C,'python3 -B scripts/ci/r02f_p05_hosted.py run --out',
                    'python3 -B scripts/ci/r02f_p05_stub.py run --out')
if __name__=='__main__':unittest.main()
