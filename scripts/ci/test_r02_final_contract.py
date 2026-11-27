"""R02 final source mutation tests; no Android writes or runtime claims."""
from __future__ import annotations
import importlib.util,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
S=importlib.util.spec_from_file_location('r02_final_contract',ROOT/'scripts/ci/r02_final_contract.py')
assert S and S.loader
C=importlib.util.module_from_spec(S);S.loader.exec_module(C)
class R02FinalSourceMutations(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix='ox-r02-final-contract-')
        self.addCleanup(t.cleanup);self.root=Path(t.name)
        for name in C.PATHS:
            dst=self.root/name;dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,dst)
    def alter(self,path,old,new):
        file=self.root/path;s=file.read_text()
        self.assertEqual(s.count(old),1,'anchor drift '+path)
        file.write_text(s.replace(old,new,1))
        self.assertTrue(C.inspect(self.root),'mutation escaped '+path)
    def test_00_baseline(self):self.assertEqual(C.inspect(self.root),[])
    def test_01_no_copy_bypass(self):self.alter(C.BRIDGE,'"copy" ->', '"unsafeCopy" ->')
    def test_02_no_cancel_bypass(self):self.alter(C.BRIDGE,'"cancel" ->', '"skipCancel" ->')
    def test_03_no_false_verification(self):self.alter(C.BRIDGE,'getOrDefault(false)','getOrDefault(true)')
    def test_04_no_sha_bypass(self):self.alter(C.SERVICE,'sha256FileOffIsolate(path)','sha256FileOffIsolate("")')
    def test_05_no_unbounded_copy(self):self.alter(C.BRIDGE,'1024L * 1024L * 1024L','Long.MAX_VALUE')
    def test_06_no_unverified_archive(self):self.alter(C.SERVICE,'resolveInstallBundlePlan(', 'unsafeFirstApk(')
    def test_07_no_obb_sdk_bypass(self):self.alter(C.SERVICE,'verifyP05SdkEnvelope(', 'ignoreP05SdkEnvelope(')
    def test_08_no_privilege_bypass(self):self.alter(C.SERVICE,'provider.installApkDir(', 'privilegedInstall(')
    def test_09_no_approval_bypass(self):self.alter(C.SERVICE,'barrierDismissible: false', 'barrierDismissible: true')
    def test_10_no_signer_check(self):self.alter(C.BRIDGE,'val observed = context.packageManager.getPackageInfo(target, flags)','val observed = context.packageManager.getPackageInfo(target, 0)')
    def test_11_no_confidence_forgery(self):self.alter(C.POLICY,'installerReportedSuccess && byteEvidenceQualified','true || installerReportedSuccess')
    def test_12_no_missing_UI(self):self.alter(C.PAGE,'Install local APK / archive','Import JSON')
    def test_13_no_missing_native(self):self.alter(C.PLUGIN,'R02LocalArchiveBridge(binding.applicationContext, binding.binaryMessenger)','noBridge()')
    def test_14_no_missing_flutter(self):self.alter(C.FLUTTER,'flutter test --no-pub test/r02_local_archive_policy_test.dart','echo skipped')
    def test_15_no_missing_source(self):self.alter(C.R00,'python3 -B scripts/ci/r02_final_contract.py --check','echo skipped')
    def test_16_no_source_signer_check(self):self.alter(C.BRIDGE,'R09ApkSignatures.current(file, Build.VERSION.SDK_INT)', 'emptyList()')
    def test_18_no_mixed_signer_acceptance(self):self.alter(C.BRIDGE,'expectedSigners == signers','true')
    def test_19_no_unverified_certificate_claim(self):self.alter(C.SIGNATURES,'require(result.isVerified)','require(true)')
    def test_20_no_signature_dependency_drift(self):self.alter(C.PLUGIN_BUILD,'apksig:9.3.1','apksig:+')
    def test_21_no_post_observation_signer_drift(self):self.alter(C.BRIDGE,'afterSigners != signers','false')
    def test_17_contract_cli_check_is_executable(self):
        # Exercise the same command used by both the launcher and R00 CI.
        result=subprocess.run(
            [sys.executable,'-B',str(ROOT/'scripts/ci/r02_final_contract.py'),'--check'],
            cwd=ROOT,text=True,capture_output=True,timeout=30,check=False)
        self.assertEqual(result.returncode,0,
                         'r02_final_contract --check refused\n'+result.stdout+result.stderr)
        self.assertIn('OX_R02_FINAL_SOURCE_CONTRACT_PASS',result.stdout)
if __name__=='__main__':unittest.main()
