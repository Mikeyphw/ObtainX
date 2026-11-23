"""Offline synthetic, non-privileged Shizuku/Dhizuku evidence verifier mutations."""
from __future__ import annotations
import hashlib,importlib.util,json,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
SOURCE='b'*40;RUN='445566'
def sha(raw):return hashlib.sha256(raw).hexdigest()

class NegativeReceipts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base=types.ModuleType('r02_rt02_hosted')
        base.Refused=type('BaseRefused',(RuntimeError,),{})
        base.identity_check=lambda:(SOURCE,RUN)
        base.host_check=lambda:(SOURCE,RUN)
        spec=importlib.util.spec_from_file_location('p04_backend_runtime',HERE/'r02f_p04_backends_hosted.py')
        with patch.dict(sys.modules,{'r02_rt02_hosted':base}):
            cls.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.m)

    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix='p04-backend-proof-')
        self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.fx=self.root/'fixtures';self.fx.mkdir()
        files={'base_v1.apk':b'fixture1'*400,'base_v2.apk':b'fixture2'*400}
        for k,v in files.items():(self.fx/k).write_bytes(v)
        (self.fx/'fixture_inventory.json').write_text(json.dumps({'source_sha':SOURCE,
            'files':{k:{'sha256':sha(v)} for k,v in files.items()}}))
        self.log=self.root/'r02f-p04-backend-private.log';self.log.write_bytes(b'PRIVATE')
        self.obj={'schema':1,'status':self.m.STATUS,'source_sha':SOURCE,'run_id':RUN,
          'mode':'unavailable','backend_packages':dict(self.m.PACKAGES),
          'shizuku_unavailable':True,'dhizuku_unavailable':True,
          'selected_backend':None,'selected_backend_authorized_read_only':False,
          'signed_fixture_source_bound':True,'private_log_sha256':sha(b'PRIVATE'),
          'privileged_install_performed':False,'backend_install_qualified':False,
          'physical_device_qualified':False,'release_qualified':False,'raw_logs_uploaded':False}
        self.write()

    def write(self): (self.root/self.m.RECEIPT).write_text(json.dumps(self.obj))
    def reject(self):
        self.write()
        with self.assertRaises((self.m.Refused,ValueError,KeyError,TypeError)):
            self.m.verify(self.root)
    def test_00_valid(self):self.assertEqual(self.m.verify(self.root),0)
    def test_01_source(self):self.obj['source_sha']='a'*40;self.reject()
    def test_02_run(self):self.obj['run_id']='0';self.reject()
    def test_03_installed_claim(self):self.obj['backend_install_qualified']=True;self.reject()
    def test_04_privileged_action_claim(self):self.obj['privileged_install_performed']=True;self.reject()
    def test_05_physical(self):self.obj['physical_device_qualified']=True;self.reject()
    def test_06_release(self):self.obj['release_qualified']=True;self.reject()
    def test_07_raw_log(self):self.obj['raw_logs_uploaded']=True;self.reject()
    def test_08_absent_code(self):self.obj['shizuku_unavailable']=False;self.reject()
    def test_09_other_absence(self):self.obj['dhizuku_unavailable']=False;self.reject()
    def test_10_bad_mode(self):self.obj['mode']='authorized_read_only';self.reject()
    def test_11_false_authorized(self):self.obj['selected_backend_authorized_read_only']=True;self.reject()
    def test_12_fake_service(self):self.obj['backend_packages']['dhizuku']='com.invalid';self.reject()
    def test_13_wrong_log(self):self.log.write_bytes(b'ALTERED');self.reject()
    def test_14_fixture_drift(self):self.fx.joinpath('base_v1.apk').write_bytes(b'WRONG');self.reject()
    def test_15_extra(self):self.obj['secret']='leak';self.reject()
    def test_16_wrong_status(self):self.obj['status']='PASS_PRIVILEGED_INSTALL';self.reject()
    def test_17_symlink(self):
        p=self.root/self.m.RECEIPT;p.unlink();p.symlink_to(self.log)
        with self.assertRaises(self.m.Refused):self.m.verify(self.root)
    def test_18_missing_permission_consent(self):
        self.assertFalse(self.m.permission_probe_planned('shizuku',''))
    def test_19_wrong_mode(self):
        self.assertFalse(self.m.permission_probe_planned('external',self.m.ACK))
    def test_20_authorized_probe_is_still_not_an_install(self):
        self.obj.update(status=self.m.AUTH_STATUS,mode='authorized_read_only',
            selected_backend='dhizuku',selected_backend_authorized_read_only=True,
            shizuku_unavailable=False,dhizuku_unavailable=False)
        self.write();self.assertEqual(self.m.verify(self.root),0)
        self.obj['backend_install_qualified']=True;self.reject()
if __name__=='__main__':unittest.main()
