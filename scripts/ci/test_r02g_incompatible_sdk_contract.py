"""R02G P01: offline adversarial contracts and exact receipt negatives.

No unit test certifies actual Android: hosted emulator must emit its own
source-bound receipt after the PackageManager test.
"""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))

# The bundled ZIP can run pure unit tests without pretending a real Android
# SDK/ADB is present. In the real repository these imports are actual modules.
if not (HERE/'r02_rt02_hosted.py').exists():
    B=types.ModuleType('r02_rt02_hosted')
    B.Refused=type('Refused',(RuntimeError,),{})
    B.FIXTURE='dev.bikram.obtainx.rt02.fixture';B.SERIAL='emulator-5554'
    B.host_check=lambda:('a'*40,'12345')
    B.identity_check=lambda:('a'*40,'12345')
    B.empty_or_expected_package=lambda:True
    B.command=lambda *args,**kwargs:subprocess.CompletedProcess(args,1,b'',b'')
    B.adb=lambda *args,**kwargs:''
    sys.modules.setdefault('r02_rt02_hosted',B)
    R=types.ModuleType('r02_rt02c_hosted');R.verify=lambda out:0
    sys.modules.setdefault('r02_rt02c_hosted',R)
    P=types.ModuleType('r02f_p02_session_abandon');P.verify=lambda out:0
    sys.modules.setdefault('r02f_p02_session_abandon',P)

import r02g_incompatible_sdk_contract as C
import r02g_incompatible_sdk_fixture as F
import r02g_incompatible_sdk_hosted as H

class FixtureTests(unittest.TestCase):
    def test_fixture_requires_min37(self):
        m=F.manifest()
        self.assertIn('android:minSdkVersion="37"',m)
        self.assertIn('android:targetSdkVersion="35"',m)
        self.assertIn('dev.bikram.obtainx.rt02g.future_sdk',m)
        self.assertNotIn('android:debuggable="true"',m)

    def test_fixture_signing_key_cleanup(self):
        with tempfile.TemporaryDirectory(prefix='ox-r02g-fixture-') as td:
            root=Path(td)
            (root/'fixture_inventory.json').write_text(json.dumps({
                'source_sha':'a'*40,'signed_with_ephemeral_ci_key':True,
                'never_released':True}),encoding='utf8')
            sdk=root/'sdk'
            for rel in ('build-tools/35.0.0/aapt2','build-tools/35.0.0/zipalign',
                        'build-tools/35.0.0/apksigner','build-tools/35.0.0/aapt',
                        'platforms/android-36/android.jar'):
                f=sdk/rel;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b'stub')
            def failed_key(*args,**kwargs):
                (root/'.rt02g-disposable.jks').write_bytes(b'private-synthetic-key')
                raise F.Refused('synthetic signer failure')
            with patch.dict(F.os.environ,{'GITHUB_ACTIONS':'true','RUNNER_OS':'Linux',
                                          'RUNNER_ARCH':'X64','GITHUB_SHA':'a'*40,
                                          'ANDROID_HOME':str(sdk)}),patch.object(F,'tool',side_effect=failed_key):
                with self.assertRaises(F.Refused):F.build(root)
            for name in ('.rt02g-disposable.jks','.rt02g-manifest.xml',
                         '.rt02g-unsigned.apk','.rt02g-aligned.apk',
                         F.NAME,F.INVENTORY):
                self.assertFalse((root/name).exists(),name)

    def test_nonhosted_fixture_signing_refused(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(F.os.environ,{'GITHUB_ACTIONS':'false'}):
                with self.assertRaises(F.Refused):F.build(Path(td))

class InstallOutputTests(unittest.TestCase):
    def output(self,rc,body):
        return subprocess.CompletedProcess(['adb'],rc,b'',body.encode('utf8'))

    def test_exact_platform_refusal_only(self):
        self.assertEqual(H.classify_install(self.output(1,
            'Performing Streamed Install\nFailure [INSTALL_FAILED_OLDER_SDK: Requires newer sdk version #37]')),
            H.EXPECTED)
    def test_unexpected_success_refused(self):
        with self.assertRaises(H.Refused):
            H.classify_install(self.output(0,'Success'))
    def test_missing_sdk_refusal_refused(self):
        with self.assertRaises(H.Refused):
            H.classify_install(self.output(1,'INSTALL_FAILED_UPDATE_INCOMPATIBLE'))
    def test_duplicate_error_category_refused(self):
        with self.assertRaises(H.Refused):
            H.classify_install(self.output(1,'INSTALL_FAILED_OLDER_SDK INSTALL_FAILED_OLDER_SDK'))
    def test_conflicting_android_errors_refused(self):
        with self.assertRaises(H.Refused):
            H.classify_install(self.output(1,'INSTALL_FAILED_OLDER_SDK INSTALL_FAILED_INVALID_APK'))
    def test_forged_success_text_refused(self):
        with self.assertRaises(H.Refused):
            H.classify_install(self.output(1,'INSTALL_FAILED_OLDER_SDK\nSuccess'))
    def test_unbounded_error_message_refused(self):
        with self.assertRaises(H.Refused):
            H.classify_install(self.output(1,'INSTALL_FAILED_OLDER_SDK'+('X'*65536)))

class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(prefix='ox-r02g-receipt-')
        self.addCleanup(self.t.cleanup)
        self.out=Path(self.t.name)
        self.inv={'sha256':'a'*64}
        self.expected={**H.baseline('b'*40,'123'),
            'status':'PASS_ANDROID_MINSDK37_REJECTED_ON_API36',
            'fixture_package':F.PACKAGE,'fixture_sha256':'a'*64,
            'min_sdk_version':37,'device_sdk_version':36,
            'android_rejection_code':H.EXPECTED,'adb_install_exit_nonzero':True,
            'package_absent_after':True,'prior_fixture_absent':True,
            'install_backend':'Android PackageManager adb install',
            'installer_dialog_approvals':0}
        H.receipt_file(self.out,self.expected)

    def verify(self):
        with patch.object(H.base,'identity_check',return_value=('b'*40,'123')), \
             patch.object(H,'inventory',return_value=self.inv):
            return H.verify(self.out)

    def test_valid_receipt(self):self.assertEqual(self.verify(),0)
    def test_modified_receipt_refused(self):
        for key,value in (('status','NOT_RUN'),('min_sdk_version',36),
                          ('device_sdk_version',37),('release_qualified',True),
                          ('physical_device_qualified',True),
                          ('android_rejection_code','INSTALL_FAILED_INVALID_APK'),
                          ('fixture_sha256','f'*64),('source_sha','c'*40),
                          ('adb_install_exit_nonzero',False),
                          ('package_absent_after',False),
                          ('installer_dialog_approvals',1)):
            with self.subTest(key=key):
                bad=self.expected.copy();bad[key]=value
                H.receipt_file(self.out,bad)
                with self.assertRaises(H.Refused):self.verify()

    def test_missing_receipt_field_refused(self):
        bad=self.expected.copy();del bad['prior_fixture_absent']
        H.receipt_file(self.out,bad)
        with self.assertRaises(H.Refused):self.verify()

class SourceContractTests(unittest.TestCase):
    @unittest.skipUnless((ROOT/C.WF).is_file(),'needs applied repo to inspect exact workflow')
    def test_valid_source(self):
        self.assertEqual(C.inspect(ROOT),[])

    @unittest.skipUnless((ROOT/C.WF).is_file(),'needs applied repo to inspect exact workflow')
    def test_removed_hosted_gate_refused(self):
        with tempfile.TemporaryDirectory(prefix='ox-r02g-source-') as td:
            root=Path(td)
            for rel in C.PATHS:
                src=ROOT/rel;dst=root/rel;dst.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(src,dst)
            wf=root/C.WF
            old='python3 -B scripts/ci/r02g_incompatible_sdk_hosted.py run --out'
            self.assertEqual(wf.read_text().count(old),1)
            wf.write_text(wf.read_text().replace(old,'echo fake-device',1))
            self.assertTrue(C.inspect(root),'missing hosted runtime escaped source contract')

    @unittest.skipUnless((ROOT/C.WF).is_file(),'needs applied repo to inspect exact workflow')
    def test_test_suppression_refused(self):
        with tempfile.TemporaryDirectory(prefix='ox-r02g-source-') as td:
            root=Path(td)
            for rel in C.PATHS:
                src=ROOT/rel;dst=root/rel;dst.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(src,dst)
            wf=root/C.WF
            wf.write_text(wf.read_text()+'\n      continue-on-error: true\n')
            self.assertTrue(C.inspect(root))

if __name__=='__main__':unittest.main()
