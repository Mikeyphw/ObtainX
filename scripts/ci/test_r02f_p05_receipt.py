"""P05 independent offline receipt test: only synthetic data, NEVER Android proof."""
from __future__ import annotations
import contextlib,hashlib,importlib.util,io,json,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
SRC='a'*40
RUN='43210'
def digest(raw):return hashlib.sha256(raw).hexdigest()

class P05ReceiptNegatives(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base=types.ModuleType('r02_rt02_hosted')
        base.Refused=type('BaseRefused',(RuntimeError,),{})
        base.identity_check=lambda:(SRC,RUN)
        base.host_check=lambda:(SRC,RUN)
        base.adb=lambda *args:'unused'
        spec=importlib.util.spec_from_file_location('p05_synthetic_verifier',HERE/'r02f_p05_hosted.py')
        assert spec and spec.loader
        with patch.dict(sys.modules,{'r02_rt02_hosted':base}):
            cls.r=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.r)
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix='ox-p05-receipt-');self.addCleanup(t.cleanup)
        self.root=Path(t.name);self.fx=self.root/'fixtures';self.fx.mkdir()
        self.v1=b'SIGNED-V1'*110;self.v2=b'SIGNED-V2'*115
        (self.fx/'base_v1.apk').write_bytes(self.v1)
        (self.fx/'base_v2.apk').write_bytes(self.v2)
        self.inv={'source_sha':SRC,'files':{
          'base_v1.apk':{'sha256':digest(self.v1)},
          'base_v2.apk':{'sha256':digest(self.v2)}}}
        (self.fx/'fixture_inventory.json').write_text(json.dumps(self.inv))
        self.data={'schema':1,'status':self.r.STATUS,'source_sha':SRC,
          'run_id':RUN,'android_sdk':36,'emulator':True,
          'supported_abis':['x86_64','x86'],'density_dpi':420,
          'locales':['en-US'],'signed_v1_sha256':digest(self.v1),
          'signed_v2_sha256':digest(self.v2),
          'direct_obb_api30_plus_refused':True,
          'obb_delivery_qualified':False,'arm64_physical_qualified':False,
          'physical_device_qualified':False,'release_qualified':False,
          'raw_logs_uploaded':False}
        self.write()
    def write(self): (self.root/self.r.RECEIPT).write_text(json.dumps(self.data))
    def reject(self):
        self.write()
        with self.assertRaises((self.r.Refused,ValueError,TypeError,KeyError,AttributeError)):
            self.r.verify(self.root)
    def test_00_valid(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.r.verify(self.root),0)
    def test_01_wrong_source(self):self.data['source_sha']='b'*40;self.reject()
    def test_02_wrong_run(self):self.data['run_id']='321';self.reject()
    def test_03_wrong_schema(self):self.data['schema']=2;self.reject()
    def test_04_wrong_status(self):self.data['status']='PASS_UNVERIFIED';self.reject()
    def test_05_false_obb_delivery(self):self.data['obb_delivery_qualified']=True;self.reject()
    def test_06_false_arm64_physical(self):self.data['arm64_physical_qualified']=True;self.reject()
    def test_07_false_physical(self):self.data['physical_device_qualified']=True;self.reject()
    def test_08_false_release(self):self.data['release_qualified']=True;self.reject()
    def test_09_false_log_upload(self):self.data['raw_logs_uploaded']=True;self.reject()
    def test_10_fake_obb_route(self):self.data['direct_obb_api30_plus_refused']=False;self.reject()
    def test_11_wrong_sdk(self):self.data['android_sdk']=35;self.reject()
    def test_12_no_emulator(self):self.data['emulator']=False;self.reject()
    def test_13_wrong_abi(self):self.data['supported_abis']=['arm64-v8a'];self.reject()
    def test_14_duplicate_abi(self):self.data['supported_abis']=['x86_64','x86_64'];self.reject()
    def test_15_invalid_density(self):self.data['density_dpi']=0;self.reject()
    def test_16_invalid_locale(self):self.data['locales']=['../../secret'];self.reject()
    def test_17_changed_v1(self):
        (self.fx/'base_v1.apk').write_bytes(b'WRONG'*110)
        with self.assertRaises(self.r.Refused):self.r.verify(self.root)
    def test_18_changed_v2(self):
        (self.fx/'base_v2.apk').write_bytes(b'WRONG'*110)
        with self.assertRaises(self.r.Refused):self.r.verify(self.root)
    def test_19_wrong_inventory(self):
        self.inv['source_sha']='b'*40
        (self.fx/'fixture_inventory.json').write_text(json.dumps(self.inv))
        with self.assertRaises(self.r.Refused):self.r.verify(self.root)
    def test_20_receipt_extra(self):self.data['installed']=True;self.reject()
    def test_21_receipt_symlink(self):
        p=self.root/self.r.RECEIPT;p.unlink();p.symlink_to(self.fx/'fixture_inventory.json')
        with self.assertRaises(self.r.Refused):self.r.verify(self.root)
    def test_22_fixture_symlink(self):
        p=self.fx/'base_v2.apk';p.unlink();p.symlink_to(self.fx/'base_v1.apk')
        with self.assertRaises(self.r.Refused):self.r.verify(self.root)
if __name__=='__main__':unittest.main()
