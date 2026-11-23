"""Executable P04B receipt-parser adversarial checks, NOT Android qualification."""
from __future__ import annotations
import hashlib
import contextlib
import io
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
SOURCE='a'*40
RUN_ID='12345'

def digest(b):return hashlib.sha256(b).hexdigest()

class ExternalReceiptNegatives(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Import the exact PRODUCTION post-emulator verifier, replacing only
        # hardware-only imports. No fake adb action can ever be considered PASS.
        base=types.ModuleType('r02_rt02_hosted')
        base.identity_check=lambda:(SOURCE,RUN_ID)
        base.host_check=lambda:(SOURCE,RUN_ID)
        base.Refused=type('BaseRefused',(RuntimeError,),{})
        rtc=types.ModuleType('r02_rt02c_hosted')
        rtc.Refused=type('RT02CRefused',(RuntimeError,),{})
        spec=importlib.util.spec_from_file_location('p04b_receipt_actual',HERE/'r02f_p04b_hosted.py')
        assert spec and spec.loader
        with patch.dict(sys.modules,{'r02_rt02_hosted':base,'r02_rt02c_hosted':rtc}):
            cls.runtime=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.runtime)
    def setUp(self):
        td=tempfile.TemporaryDirectory(prefix='ox-p04b-receipt-');self.addCleanup(td.cleanup)
        self.root=Path(td.name)
        fx=self.root/'fixtures';fx.mkdir()
        v2=b'disposable-signed-v2-byte-fixture'*55
        target=b'disposable-target-apk-byte-fixture'*44
        (fx/'base_v2.apk').write_bytes(v2)
        (fx/'p04b-external-decline.apk').write_bytes(target)
        inv={'schema':1,'source_sha':SOURCE,'files':{'base_v2.apk':{'sha256':digest(v2)}}}
        target_inv={'schema':1,'source_sha':SOURCE,'sha256':digest(target),
                    'signed_disposable_target':True,'only_reads_content_uri':True,
                    'can_install_apks':False}
        (fx/'fixture_inventory.json').write_text(json.dumps(inv))
        (fx/'p04b_target_inventory.json').write_text(json.dumps(target_inv))
        log=b'All tests passed!\nOX_R02F_P04B_DART_REAL_DECLINE_NO_FALSE_SUCCESS_PASS\n'
        (self.root/'r02f-p04b-private.log').write_bytes(log)
        baseline={'version_code':1,'installed_path_count':1,'base_sha256':digest(b'original-signed-v1')}
        self.data={'schema':1,'status':self.runtime.STATUS,'source_sha':SOURCE,'run_id':RUN_ID,
                   'target_component':'dev.bikram.obtainx.p04b.target.DeclineActivity',
                   'signed_target_sha256':digest(target),'received_v2_sha256':digest(v2),
                   'expected_v2_sha256':digest(v2),
                   'signed_v1_before':baseline,'signed_v1_after':baseline,
                   'flutter_log_sha256':digest(log),'native_external_activity_invoked':True,
                   'external_target_declined_without_install':True,
                   'independent_android_v1_checked':True,
                   'external_positive_install_qualified':False,
                   'physical_device_qualified':False,'shizuku_qualified':False,
                   'dhizuku_qualified':False,'release_qualified':False,'raw_logs_uploaded':False}
        self.write()
    def write(self):
        (self.root/self.runtime.RECEIPT).write_text(json.dumps(self.data))
    def reject(self):
        self.write()
        with self.assertRaises((self.runtime.Refused,ValueError,KeyError,TypeError)):
            self.runtime.verify(self.root)
    def test_00_exact_synthetic_receipt_schema(self):
        # Never emit an Android PASS marker from synthetic source-only tests.
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            self.assertEqual(self.runtime.verify(self.root),0)
        self.assertIn('INDEPENDENT_SOURCE_BOUND_RECEIPT_PASS',captured.getvalue())
    def test_01_wrong_source(self):self.data['source_sha']='b'*40;self.reject()
    def test_02_wrong_run(self):self.data['run_id']='678';self.reject()
    def test_03_false_positive_qualified(self):self.data['external_positive_install_qualified']=True;self.reject()
    def test_04_wrong_v2_digest(self):self.data['received_v2_sha256']='0'*64;self.reject()
    def test_05_wrong_installed_v1(self):
        self.data['signed_v1_after']={'version_code':2};self.reject()
    def test_06_raw_logs_qualified(self):self.data['raw_logs_uploaded']=True;self.reject()
    def test_07_log_mutated_after_receipt(self):
        (self.root/'r02f-p04b-private.log').write_bytes(b'mutated-private-log')
        self.reject()
    def test_08_extra_field(self):self.data['privileged_install']=True;self.reject()
    def test_09_no_external_android_evidence(self):
        self.data['native_external_activity_invoked']=False;self.reject()
    def test_10_wrong_target(self):self.data['target_component']='other.Component';self.reject()
    def test_11_missing_fixture_inventory(self):
        (self.root/'fixtures'/'p04b_target_inventory.json').unlink()
        self.write()
        with self.assertRaises(FileNotFoundError):self.runtime.verify(self.root)
    def test_13_wrong_fixture_inventory_source(self):
        f=self.root/'fixtures'/'fixture_inventory.json'
        x=json.loads(f.read_text());x['source_sha']='b'*40;f.write_text(json.dumps(x))
        self.reject()
    def test_14_wrong_target_inventory_source(self):
        f=self.root/'fixtures'/'p04b_target_inventory.json'
        x=json.loads(f.read_text());x['source_sha']='b'*40;f.write_text(json.dumps(x))
        self.reject()
    def test_15_target_bytes_modified(self):
        (self.root/'fixtures'/'p04b-external-decline.apk').write_bytes(b'forged target')
        self.reject()
    def test_16_v2_bytes_modified(self):
        (self.root/'fixtures'/'base_v2.apk').write_bytes(b'forged v2')
        self.reject()
    def test_17_target_scope_mutated(self):
        f=self.root/'fixtures'/'p04b_target_inventory.json'
        x=json.loads(f.read_text());x['can_install_apks']=True;f.write_text(json.dumps(x))
        self.reject()
    def test_12_symlinked_receipt(self):
        f=self.root/self.runtime.RECEIPT;f.unlink();f.symlink_to(self.root/'r02f-p04b-private.log')
        with self.assertRaises(self.runtime.Refused):self.runtime.verify(self.root)
if __name__=='__main__':unittest.main()
