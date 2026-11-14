"""P03 independent offline signed-byte receipt and false-qualification negatives."""
from __future__ import annotations
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

SOURCE='a'*40
RUN_ID='101010'
HERE=Path(__file__).resolve().parent

def sha(data:bytes):return hashlib.sha256(data).hexdigest()

class P03OfflineReceipt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base=types.ModuleType('r02_rt02_hosted')
        base.identity_check=lambda:(SOURCE,RUN_ID)
        base.host_check=lambda:(SOURCE,RUN_ID)
        base.Refused=type('BaseRefused',(RuntimeError,),{})
        rt02c=types.ModuleType('r02_rt02c_hosted')
        rt02c.Refused=type('Rt02cRefused',(RuntimeError,),{})
        target=types.ModuleType('r02f_p04b_p03_target')
        target.PACKAGE='dev.bikram.obtainx.p04b.target'
        target.ACTIVITY=target.PACKAGE+'.DeclineActivity'
        target.APK='p04b-p03-delayed-decline.apk'
        spec=importlib.util.spec_from_file_location('p03_offline_verifier',
            HERE/'r02f_p04b_p03_hosted.py')
        assert spec and spec.loader
        with patch.dict(sys.modules,{
            'r02_rt02_hosted':base,
            'r02_rt02c_hosted':rt02c,
            'r02f_p04b_p03_target':target,
        }):
            cls.host=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.host)

    def setUp(self):
        td=tempfile.TemporaryDirectory(prefix='ox-p04b-p03-receipt-')
        self.addCleanup(td.cleanup)
        self.root=Path(td.name)
        fx=self.root/'fixtures';fx.mkdir()
        f3=fx/'p04b_p03';f3.mkdir()
        v1=b'fictional signed baseline v1'*200
        v2=b'fictional signed v2'*230
        target=b'signed noninstalling delayed target'*180
        for p,data in ((fx/'base_v1.apk',v1),(fx/'base_v2.apk',v2),
                       (f3/'p04b-p03-delayed-decline.apk',target)):
            p.write_bytes(data)
        (fx/'fixture_inventory.json').write_text(json.dumps({'source_sha':SOURCE,'files':{
            'base_v1.apk':{'sha256':sha(v1)},'base_v2.apk':{'sha256':sha(v2)}}}))
        (f3/'p04b_target_inventory.json').write_text(json.dumps({
            'source_sha':SOURCE,'package':'dev.bikram.obtainx.p04b.target',
            'activity':'dev.bikram.obtainx.p04b.target.DeclineActivity',
            'sha256':sha(target),'signed_disposable_target':True,
            'only_reads_content_uri':True,'can_install_apks':False}))
        log=b'confidential flutter transcript'*6
        (self.root/'r02f-p04b-p03-private.log').write_bytes(log)
        baseline={'version_code':1,'installed_path_count':1,
                  'base_sha256':sha(v1),'installed_original_intact':True}
        self.receipt={'schema':1,'status':self.host.STATUS,'source_sha':SOURCE,
            'run_id':RUN_ID,'signed_target_sha256':sha(target),
            'received_v2_sha256':sha(v2),'v2_sha256':sha(v2),
            'before':dict(baseline),'after':dict(baseline),
            'spoof_custom_broadcasts':1,'late_custom_broadcasts':1,
            'parallel_handoffs_refused':1,
            'mismatched_expected_package_unverified':True,'signed_v1_unchanged':True,
            'private_flutter_log_sha256':sha(log),
            'untrusted_broadcast_not_install_proof':True,
            'positive_install_qualified_by_p03':False,'physical_device_qualified':False,
            'shizuku_qualified':False,'dhizuku_qualified':False,
            'release_qualified':False,'raw_logs_uploaded':False}
        self.write()

    def write(self):
        (self.root/self.host.RECEIPT).write_text(json.dumps(self.receipt))

    def refused(self):
        self.write()
        with self.assertRaises((self.host.Refused,TypeError,KeyError,ValueError,OSError)):
            self.host.verify(self.root)

    def test_00_synthetic_valid(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.host.verify(self.root),0)
    def test_01_wrong_sha(self):self.receipt['source_sha']='b'*40;self.refused()
    def test_02_wrong_run(self):self.receipt['run_id']='not-the-run';self.refused()
    def test_03_false_success(self):self.receipt['positive_install_qualified_by_p03']=True;self.refused()
    def test_04_fake_v2_version(self):self.receipt['after']['version_code']=2;self.refused()
    def test_05_v1_changed(self):self.receipt['after']['base_sha256']='0'*64;self.refused()
    def test_06_wrong_target(self):self.receipt['signed_target_sha256']='1'*64;self.refused()
    def test_07_wrong_received_v2(self):self.receipt['received_v2_sha256']='f'*64;self.refused()
    def test_08_missing_parallel_refusal(self):self.receipt['parallel_handoffs_refused']=0;self.refused()
    def test_09_forged_bool_counter(self):self.receipt['spoof_custom_broadcasts']=True;self.refused()
    def test_10_extra_counter(self):self.receipt['spoof_custom_broadcasts']=2;self.refused()
    def test_11_no_late(self):self.receipt['late_custom_broadcasts']=0;self.refused()
    def test_12_false_positive_bridge(self):self.receipt['mismatched_expected_package_unverified']=False;self.refused()
    def test_13_dropped_untrusted_rule(self):self.receipt['untrusted_broadcast_not_install_proof']=False;self.refused()
    def test_14_false_shizuku(self):self.receipt['shizuku_qualified']=True;self.refused()
    def test_15_false_release(self):self.receipt['release_qualified']=True;self.refused()
    def test_16_raw_logs(self):self.receipt['raw_logs_uploaded']=True;self.refused()
    def test_17_log_mutation(self):
        (self.root/'r02f-p04b-p03-private.log').write_bytes(b'forged log');self.refused()
    def test_18_apk_mutation(self):
        (self.root/'fixtures'/'base_v2.apk').write_bytes(b'forged v2');self.refused()
    def test_19_target_mutation(self):
        (self.root/'fixtures'/'p04b_p03'/'p04b-p03-delayed-decline.apk').write_bytes(b'forged');self.refused()
    def test_20_extra_field(self):self.receipt['runtime_perfect']=True;self.refused()
    def test_21_symlink(self):
        p=self.root/self.host.RECEIPT;p.unlink();p.symlink_to(self.root/'r02f-p04b-p03-private.log')
        with self.assertRaises(self.host.Refused):self.host.verify(self.root)
    def test_22_wrong_inventory_source(self):
        p=self.root/'fixtures'/'p04b_p03'/'p04b_target_inventory.json'
        d=json.loads(p.read_text());d['source_sha']='z'*40;p.write_text(json.dumps(d));self.refused()
    def test_23_missing_inventory(self):
        (self.root/'fixtures'/'fixture_inventory.json').unlink();self.refused()

if __name__=='__main__':unittest.main()
