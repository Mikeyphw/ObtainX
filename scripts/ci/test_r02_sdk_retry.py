"""Adversarial offline-only tests for bounded hosted SDK provision."""
from __future__ import annotations
from pathlib import Path
import importlib.util, subprocess, tempfile, unittest
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

if __name__=='__main__':unittest.main()
