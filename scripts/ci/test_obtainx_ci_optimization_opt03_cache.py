"""Bounded cache material validation and mutation regressions for OPT03."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('obtainx_ci_optimization_opt03_apk_cache',
                                          ROOT/'scripts/ci/obtainx_ci_optimization_opt03_apk_cache.py')
M=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)

class CacheIntegrity(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix='ox-opt03-')
        self.addCleanup(tmp.cleanup)
        p=Path(tmp.name)
        self.apk=p/M.APK_NAME
        self.receipt=p/M.RECEIPT_NAME
        self.source='a'*40
        with zipfile.ZipFile(self.apk,'w',compression=zipfile.ZIP_STORED) as z:
            z.writestr('AndroidManifest.xml',b'xml'*16)
            z.writestr('classes.dex',b'0'*(M.MIN_BYTES+100))
        M.seal(self.apk,self.receipt,self.source)
    def test_valid_exact_source_receipt(self):
        M.verify(self.apk,self.receipt,self.source)
    def test_wrong_sha_is_rejected(self):
        with self.assertRaises(M.Refused):M.verify(self.apk,self.receipt,'b'*40)
    def test_wrong_profile_is_rejected(self):
        d=json.loads(self.receipt.read_text())
        d['profile']='other'
        self.receipt.write_text(json.dumps(d))
        with self.assertRaises(M.Refused):M.verify(self.apk,self.receipt,self.source)
    def test_wrong_package_claim_is_rejected(self):
        d=json.loads(self.receipt.read_text())
        d['package_name']='com.unrelated.app'
        self.receipt.write_text(json.dumps(d))
        with self.assertRaises(M.Refused):M.verify(self.apk,self.receipt,self.source)
    def test_checksum_tampering_is_rejected(self):
        d=json.loads(self.receipt.read_text());d['sha256']='b'*64
        self.receipt.write_text(json.dumps(d))
        with self.assertRaises(M.Refused):M.verify(self.apk,self.receipt,self.source)
    def test_bytes_tampering_is_rejected(self):
        with self.apk.open('ab') as fh:fh.write(b'forged bytes')
        with self.assertRaises(M.Refused):M.verify(self.apk,self.receipt,self.source)
    def test_symlinked_cache_apk_is_rejected(self):
        original=self.apk.with_suffix('.original')
        self.apk.rename(original)
        self.apk.symlink_to(original)
        with self.assertRaises(M.Refused):M.verify(self.apk,self.receipt,self.source)
    def test_unreadable_zip_is_rejected(self):
        self.apk.write_bytes(b'X'*M.MIN_BYTES)
        with self.assertRaises(M.Refused):M.verify(self.apk,self.receipt,self.source)
    def test_missing_android_manifest_is_rejected(self):
        with zipfile.ZipFile(self.apk,'w') as z:z.writestr('classes.dex',b'0'*M.MIN_BYTES)
        with self.assertRaises(M.Refused):M.verify(self.apk,self.receipt,self.source)
    def test_extra_receipt_field_is_rejected(self):
        d=json.loads(self.receipt.read_text());d['release_qualified']=True
        self.receipt.write_text(json.dumps(d))
        with self.assertRaises(M.Refused):M.verify(self.apk,self.receipt,self.source)
    def test_missing_receipt_is_rejected(self):
        self.receipt.unlink()
        with self.assertRaises(M.Refused):M.verify(self.apk,self.receipt,self.source)
    def test_checked_out_source_must_equal_event_sha(self):
        proc=subprocess.CompletedProcess(['git'],0,b'b'*40+b'\n',b'')
        with patch.dict(M.os.environ,{'GITHUB_SHA':self.source,'GITHUB_ACTIONS':'true',
                                      'RUNNER_OS':'Linux','RUNNER_ARCH':'X64'}),\
             patch.object(M.subprocess,'run',return_value=proc):
            with self.assertRaises(M.Refused):M.source_identity()
    def test_source_identity_requires_hosted_x64(self):
        with patch.dict(M.os.environ,{'GITHUB_SHA':self.source,'GITHUB_ACTIONS':'false',
                                      'RUNNER_OS':'Linux','RUNNER_ARCH':'X64'}):
            with self.assertRaises(M.Refused):M.source_identity()
    def test_android_inspection_missing_sdk_refuses(self):
        with patch.dict(M.os.environ,{'ANDROID_HOME':'/non-existent-opt03-sdk'}):
            with self.assertRaises(M.Refused):M.verify_android_tools(self.apk)
    def test_sig_and_package_validation_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix='ox-apk-sdk-') as d:
            root=Path(d)
            tool=root/'build-tools'/'35.0.0'
            tool.mkdir(parents=True)
            for s in ('aapt','apksigner'):(tool/s).touch()
            r=subprocess.CompletedProcess(['tool'],1,b'',b'FAIL')
            with patch.dict(M.os.environ,{'ANDROID_HOME':str(root)}),\
                 patch.object(M.subprocess,'run',return_value=r):
                with self.assertRaises(M.Refused):M.verify_android_tools(self.apk)

if __name__=='__main__':unittest.main()
