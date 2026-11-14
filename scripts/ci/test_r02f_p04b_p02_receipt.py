"""Execute exact P02 post-emulator verifier with 15 synthetic refusal mutations.

Synthetic receipts NEVER qualify Android. Captures any PASS console output.
"""
from __future__ import annotations
import contextlib,hashlib,importlib.util,io,json,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
SOURCE='a'*40
RUN_ID='123456'
def sha(raw):return hashlib.sha256(raw).hexdigest()
class ReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base=types.ModuleType('r02_rt02_hosted')
        base.identity_check=lambda:(SOURCE,RUN_ID)
        base.host_check=lambda:(SOURCE,RUN_ID)
        base.Refused=type('BaseRefused',(RuntimeError,),{})
        target=types.ModuleType('r02f_p04b_p02_target')
        target.PACKAGE='dev.bikram.obtainx.p04b.positive'
        target.ACTIVITY=target.PACKAGE+'.PositiveInstallActivity'
        target.APK='p04b-positive-target.apk'
        spec=importlib.util.spec_from_file_location('p02_real_verifier',HERE/'r02f_p04b_p02_hosted.py')
        assert spec and spec.loader
        with patch.dict(sys.modules,{'r02_rt02_hosted':base,'r02f_p04b_p02_target':target}):
            cls.runtime=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.runtime)
    def setUp(self):
        td=tempfile.TemporaryDirectory(prefix='ox-p04b-p02-receipt-');self.addCleanup(td.cleanup)
        self.root=Path(td.name);fx=self.root/'fixtures';fx.mkdir()
        v1=b'disposable signed v1'*100;v2=b'disposable signed v2'*110;target=b'positive installer signed apk'*80
        for name,data in [('base_v1.apk',v1),('base_v2.apk',v2),('p04b-positive-target.apk',target)]:
            (fx/name).write_bytes(data)
        (fx/'fixture_inventory.json').write_text(json.dumps({'source_sha':SOURCE,'files':{
            'base_v1.apk':{'sha256':sha(v1)},'base_v2.apk':{'sha256':sha(v2)}}}))
        (fx/'p04b_positive_inventory.json').write_text(json.dumps({'schema':1,'source_sha':SOURCE,
             'sha256':sha(target),'requires_system_user_approval':True,
             'only_disposable_fixture_install':True}))
        log=b'private Flutter test transcript';(self.root/'r02f-p04b-p02-private.log').write_bytes(log)
        self.data={'schema':1,'status':self.runtime.STATUS,'source_sha':SOURCE,'run_id':RUN_ID,
                   'target_component':self.runtime.target.ACTIVITY,'target_sha256':sha(target),
                   'v2_sha256':sha(v2),'target_received_sha256':sha(v2),
                   'before':{'version_code':1,'base_sha256':sha(v1),'split_count':0},
                   'after':{'version_code':2,'base_sha256':sha(v2),'split_count':0},
                   'system_approval_taps':1,'flutter_log_sha256':sha(log),
                   'external_mode':'production_native_intent','android_install_status_verified':True,
                   'signed_bytes_verified':True,'dart_handoff_not_success':True,
                   'physical_device_qualified':False,'shizuku_qualified':False,
                   'dhizuku_qualified':False,'release_qualified':False,'raw_logs_uploaded':False}
        self.write()
    def write(self): (self.root/self.runtime.RECEIPT).write_text(json.dumps(self.data))
    def reject(self):
        self.write()
        with self.assertRaises((self.runtime.Refused,ValueError,TypeError,KeyError)):
            self.runtime.verify(self.root)
    def test_00_baseline(self):
        with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(self.runtime.verify(self.root),0)
    def test_01_source(self):self.data['source_sha']='b'*40;self.reject()
    def test_02_runid(self):self.data['run_id']='999';self.reject()
    def test_03_approval(self):self.data['system_approval_taps']=0;self.reject()
    def test_04_dart_false_success(self):self.data['dart_handoff_not_success']=False;self.reject()
    def test_05_android_status(self):self.data['android_install_status_verified']=False;self.reject()
    def test_06_wrong_version(self):self.data['after']['version_code']=1;self.reject()
    def test_07_wrong_apk_hash(self):self.data['after']['base_sha256']='0'*64;self.reject()
    def test_08_received_mismatch(self):self.data['target_received_sha256']='0'*64;self.reject()
    def test_09_no_bound_log(self):
        (self.root/'r02f-p04b-p02-private.log').write_bytes(b'forged log');self.reject()
    def test_10_changed_target(self):
        (self.root/'fixtures'/'p04b-positive-target.apk').write_bytes(b'forged target');self.reject()
    def test_11_changed_v2(self):
        (self.root/'fixtures'/'base_v2.apk').write_bytes(b'forged v2');self.reject()
    def test_12_changed_v1(self):
        (self.root/'fixtures'/'base_v1.apk').write_bytes(b'forged v1');self.reject()
    def test_13_wrong_inventory_source(self):
        p=self.root/'fixtures'/'p04b_positive_inventory.json';d=json.loads(p.read_text());d['source_sha']='b'*40;p.write_text(json.dumps(d));self.reject()
    def test_14_false_privilege_scope(self):self.data['shizuku_qualified']=True;self.reject()
    def test_15_extra_receipt_field(self):self.data['approval_user']='secret';self.reject()
    def test_16_fake_mode(self):self.data['external_mode']='shell_pm_install';self.reject()
    def test_17_symlink(self):
        p=self.root/self.runtime.RECEIPT;p.unlink();p.symlink_to(self.root/'r02f-p04b-p02-private.log')
        with self.assertRaises(self.runtime.Refused):self.runtime.verify(self.root)
if __name__=='__main__':unittest.main()
