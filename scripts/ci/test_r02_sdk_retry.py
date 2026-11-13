"""Adversarial offline-only tests for bounded hosted SDK provision."""
from __future__ import annotations
from pathlib import Path
import importlib.util, subprocess, tempfile, unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('r02_sdk_retry',ROOT/'scripts/ci/r02_sdk_retry.py')
assert SPEC and SPEC.loader
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)

class MockSDK(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ox-hf05-sdk-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.env={'GITHUB_ACTIONS':'true','RUNNER_OS':'Linux','RUNNER_ARCH':'X64',
                  'ANDROID_HOME':str(self.root),'RUNNER_TEMP':str(self.root)}
        self.calls=[];self.slept=[]

    def image(self,complete=True):
        for rel in ('platforms/android-36/android.jar','build-tools/35.0.0/aapt2',
                    'system-images/android-36/google_apis/x86_64/source.properties',
                    'system-images/android-36/google_apis/x86_64/system.img'):
            p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(b'X'*(2*1024*1024 if rel.endswith('system.img') and complete else 20))

    def fake(self,responses):
        def run(args,**kwargs):
            self.assertEqual(args,['sdkmanager','--install',*M.PACKAGES])
            self.assertEqual(kwargs['timeout'],480)
            self.assertIs(kwargs['check'],False)
            self.calls.append(args)
            rc,message=responses.pop(0)
            kwargs['stdout'].write(message.encode())
            if rc==0:self.image()
            return subprocess.CompletedProcess(args,rc)
        return run

    def invoke(self,responses):
        return M.attempt_install(self.fake(responses),self.slept.append,
                                 sdk_root=self.root,env=self.env)

    def test_clean_success_one_download(self):
        self.assertEqual(self.invoke([(0,'done')]),0);self.assertEqual(len(self.calls),1)
    def test_exact_corrupt_zip_retries_once(self):
        self.assertEqual(self.invoke([(1,M.CORRUPT_ZIP),(0,'done')]),0)
        self.assertEqual(len(self.calls),2);self.assertEqual(self.slept,[5])
    def test_second_corrupt_zip_refused(self):
        with self.assertRaises(M.Refused):self.invoke([(1,M.CORRUPT_ZIP),(1,M.CORRUPT_ZIP)])
        self.assertEqual(len(self.calls),2)
    def test_non_corrupt_failure_never_retried(self):
        with self.assertRaises(M.Refused):self.invoke([(1,'disk full')])
        self.assertEqual(len(self.calls),1);self.assertFalse(self.slept)
    def test_zero_exit_without_image_refused(self):
        with self.assertRaises(M.Refused):M.sdk_proof(self.root)
    def test_truncated_image_refused(self):
        self.image(False)
        with self.assertRaises(M.Refused):M.sdk_proof(self.root)
    def test_hosted_runner_required(self):
        self.env['GITHUB_ACTIONS']='false'
        with self.assertRaises(M.Refused):self.invoke([(0,'done')])
        self.assertFalse(self.calls)

class SDKWorkflowContracts(unittest.TestCase):
    def test_exact_four_workflows_use_bounded_helper(self):
        for rel in ('.github/workflows/obtainx-r02-api36.yml',
                    '.github/workflows/obtainx-r02-rt02.yml',
                    '.github/workflows/obtainx-r02-rt02b.yml',
                    '.github/workflows/obtainx-r02-rt02c.yml'):
            s=(ROOT/rel).read_text()
            self.assertEqual(s.count("python3 -B scripts/ci/r02_sdk_retry.py 'platforms;android-36' 'build-tools;35.0.0' 'system-images;android-36;google_apis;x86_64'"),1,rel)
            self.assertIn("      - 'scripts/ci/r02_sdk_retry.py'",s,rel)
            self.assertNotIn('continue-on-error: true',s,rel)
            self.assertIn('timeout-minutes: 3',s,rel)
            self.assertIn('api-level: 36',s,rel)
        policy=(ROOT/'scripts/ci/obtainx_ci_policy.py').read_text()
        self.assertIn("'scripts/ci/r02_sdk_retry.py'",policy)

class OPT06P02SelectiveSDKPreflight(MockSDK):
    """Exact-package proof and diagnostics; no Android, Gradle, or network calls."""

    def seed(self,selected=(0,1,2),properties=True):
        for index in selected:
            path,prop,key,value,size=M.COMPONENTS[index]
            payload=self.root/path
            payload.parent.mkdir(parents=True,exist_ok=True)
            payload.write_bytes(b'V' * (size + (1 if path.endswith('/system.img') else 0)))
            if properties:
                props=self.root/prop
                props.parent.mkdir(parents=True,exist_ok=True)
                content=key+'='+value+'\n'
                if index==2:
                    content+='SystemImage.Abi=x86_64\nSystemImage.TagId=google_apis\n'
                props.write_text(content)

    def run_missing(self,expected,fail=False):
        seen=[]
        def fake(args,**kwargs):
            seen.append(args)
            self.assertEqual(args,['sdkmanager','--install',*expected])
            self.assertEqual(kwargs['timeout'],480)
            self.assertIs(kwargs['check'],False)
            if fail:
                kwargs['stdout'].write(b'network failed')
                return subprocess.CompletedProcess(args,1)
            self.image()
            return subprocess.CompletedProcess(args,0)
        return fake,seen

    def test_all_preinstalled_skips_sdkmanager(self):
        self.seed()
        self.assertEqual(M.present_packages(self.root),(True,True,True))
        run,seen=self.run_missing(())
        self.assertEqual(M.attempt_install(run,sdk_root=self.root,env=self.env),0)
        self.assertFalse(seen)

    def test_partial_preinstalled_only_missing_requested(self):
        self.seed((0,1))
        self.assertEqual(M.present_packages(self.root),(True,True,False))
        run,seen=self.run_missing((M.PACKAGES[2],))
        self.assertEqual(M.attempt_install(run,sdk_root=self.root,env=self.env),0)
        self.assertEqual(len(seen),1)

    def test_ambiguous_platform_properties_require_install(self):
        self.seed((0,1,2))
        (self.root/M.COMPONENTS[0][1]).write_text('AndroidVersion.ApiLevel=35\n')
        self.assertEqual(M.present_packages(self.root),(False,True,True))
        run,seen=self.run_missing((M.PACKAGES[0],))
        self.assertEqual(M.attempt_install(run,sdk_root=self.root,env=self.env),0)
        self.assertEqual(len(seen),1)

    def test_bogus_system_image_tag_never_skipped(self):
        self.seed()
        p=self.root/M.COMPONENTS[2][1]
        p.write_text(p.read_text().replace('SystemImage.TagId=google_apis','SystemImage.TagId=default'))
        self.assertEqual(M.present_packages(self.root),(True,True,False))

    def test_wrong_system_image_abi_never_skipped(self):
        self.seed()
        p=self.root/M.COMPONENTS[2][1]
        p.write_text(p.read_text().replace('SystemImage.Abi=x86_64','SystemImage.Abi=arm64-v8a'))
        self.assertEqual(M.present_packages(self.root),(True,True,False))

    def test_partial_image_truncated_never_skipped(self):
        self.seed()
        (self.root/M.COMPONENTS[2][0]).write_bytes(b'x')
        self.assertEqual(M.present_packages(self.root),(True,True,False))

    def test_symlinked_android_jar_never_skipped(self):
        self.seed()
        target=self.root/M.COMPONENTS[0][0]
        outside=self.root/'other.jar';outside.write_bytes(b'x'*(1024*1024))
        target.unlink();target.symlink_to(outside)
        self.assertEqual(M.present_packages(self.root),(False,True,True))

    def test_duplicate_source_property_key_never_skipped(self):
        self.seed()
        p=self.root/M.COMPONENTS[1][1]
        p.write_text(p.read_text()+'Pkg.Revision=35.0.0\n')
        self.assertEqual(M.present_packages(self.root),(True,False,True))

    def test_unreadable_or_absent_metadata_falls_back_to_install(self):
        self.seed()
        (self.root/M.COMPONENTS[0][1]).unlink()
        self.assertEqual(M.present_packages(self.root),(False,True,True))

    def test_preinstalled_still_requires_final_image_proof(self):
        self.seed()
        with patch.object(M,'sdk_proof',side_effect=M.Refused('forced')):
            with self.assertRaises(M.Refused):M.attempt_install(sdk_root=self.root,env=self.env)

    def test_preinstalled_summary_has_bounded_metadata(self):
        self.seed()
        summary=self.root/'summary.md';self.env['GITHUB_STEP_SUMMARY']=str(summary)
        self.assertEqual(M.attempt_install(sdk_root=self.root,env=self.env),0)
        info=summary.read_text()
        self.assertIn('preinstalled=111',info)
        self.assertIn('sdkmanager_attempts=0',info)
        self.assertNotIn(str(self.root),info)

    def test_noncorrupt_partial_failure_no_retry_and_no_summary(self):
        self.seed((0,1))
        summary=self.root/'summary.md';self.env['GITHUB_STEP_SUMMARY']=str(summary)
        run,seen=self.run_missing((M.PACKAGES[2],),fail=True)
        with self.assertRaises(M.Refused):
            M.attempt_install(run,self.slept.append,sdk_root=self.root,env=self.env)
        self.assertEqual(len(seen),1)
        self.assertFalse(summary.exists())

    def test_empty_properties_have_no_false_positive(self):
        self.seed(properties=False)
        self.assertEqual(M.present_packages(self.root),(False,False,False))

    def test_exact_corrupt_zip_retry_partial_set_only(self):
        self.seed((0,))
        attempts=[]
        missing=(M.PACKAGES[1],M.PACKAGES[2])
        def fake(args,**kwargs):
            self.assertEqual(args,['sdkmanager','--install',*missing]);attempts.append(args)
            if len(attempts)==1:
                kwargs['stdout'].write(M.CORRUPT_ZIP.encode())
                return subprocess.CompletedProcess(args,1)
            self.image();return subprocess.CompletedProcess(args,0)
        self.assertEqual(M.attempt_install(fake,self.slept.append,sdk_root=self.root,env=self.env),0)
        self.assertEqual(len(attempts),2);self.assertEqual(self.slept,[5])

if __name__=='__main__':unittest.main()
