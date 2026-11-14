"""P04B P03 adversarial source mutations: never claim Android runtime acceptance."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('p04b_p03_contract',ROOT/'scripts/ci/r02f_p04b_p03_contract.py')
assert SPEC and SPEC.loader
C=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(C)

class P03SourceMutations(unittest.TestCase):
    def setUp(self):
        td=tempfile.TemporaryDirectory(prefix='ox-p04b-p03-mutation-')
        self.addCleanup(td.cleanup)
        self.root=Path(td.name)
        for relative in C.PATHS:
            p=self.root/relative;p.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/relative,p)
    def mutate(self,path,old,new):
        f=self.root/path
        source=f.read_text()
        self.assertEqual(source.count(old),1,'source mutation anchor drift '+path+' '+old)
        f.write_text(source.replace(old,new,1))
        issues=C.inspect(self.root)
        self.assertTrue(issues,'unsafe P03 source change escaped contract: '+path+' '+old)

    def test_00_valid(self):self.assertEqual(C.inspect(self.root),[])
    def test_01_parallel_refusal_removed(self):
        self.mutate(C.MAIN,'methodResult.error("INSTALL_IN_PROGRESS",',
                    'methodResult.success(true); // disabled\n            methodResult.error("IGNORED",')
    def test_02_parallel_check_after_cache(self):
        self.mutate(C.MAIN,'val activeExternalWatcher = installWatcher',
                    'val duplicatedWatcher = installWatcher')
    def test_03_drop_old_session_fence(self):
        self.mutate(C.MAIN,'if (session.receiver !== this) return',
                    'if (session.receiver === this) return')
    def test_04_drop_action_guard(self):
        self.mutate(C.MAIN,'broadcastIntent.action != Intent.ACTION_PACKAGE_ADDED',
                    'broadcastIntent.action == Intent.ACTION_PACKAGE_ADDED')
    def test_05_drop_scheme_guard(self):
        self.mutate(C.MAIN,'broadcastIntent.data?.scheme != "package"',
                    'broadcastIntent.data?.scheme == "package"')
    def test_06_target_delay_bypassed(self):
        self.mutate(C.TARGET,"NEW='}, 12000L);'","NEW='}, 1L);'")
    def test_07_target_signed_builder_removed(self):
        self.mutate(C.TARGET,'delegate.build(out)','return')
    def test_08_missing_native_refusal_assertion(self):
        self.mutate(C.DART,"expect(refusal,'INSTALL_IN_PROGRESS'",
                    "expect(refusal,'INSTALL_OK'")
    def test_09_forged_success_in_dart(self):
        self.mutate(C.DART,'expect(verdict.isSuccess,isFalse)',
                    'expect(verdict.isSuccess,isTrue)')
    def test_10_wrong_version_not_checked(self):
        self.mutate(C.DART,"expectedPackageName:'$_fixture.mismatched'",
                    'expectedPackageName:_fixture')
    def test_11_no_spoof_probe(self):
        self.mutate(C.DART,"await _probe('spoof')", "await _probe('ignored')")
    def test_12_no_late_probe(self):
        self.mutate(C.DART,"await _probe('late')", "await _probe('spoof')")
    def test_13_replace_android_v1_baseline(self):
        self.mutate(C.HOST,'before==after','before!=after')
    def test_14_fake_android_success_receipt(self):
        self.mutate(C.HOST,"'positive_install_qualified_by_p03':False",
                    "'positive_install_qualified_by_p03':True")
    def test_15_remove_private_log_hash(self):
        self.mutate(C.HOST,"obj['private_flutter_log_sha256']==sha(out/'r02f-p04b-p03-private.log')",
                    "obj['private_flutter_log_sha256'] is not None")
    def test_16_remove_runtime_job(self):
        self.mutate(C.WORKFLOW,'python3 -B scripts/ci/r02f_p04b_p03_hosted.py run --out',
                    'python3 -B scripts/ci/never.py run --out')
    def test_17_remove_offline_verifier(self):
        self.mutate(C.WORKFLOW,'python3 -B scripts/ci/r02f_p04b_p03_hosted.py verify --out',
                    'python3 -B scripts/ci/never.py verify --out')
    def test_18_remove_receipt_upload(self):
        self.mutate(C.WORKFLOW,'r02f-p04b-p03-adversarial.json',
                    'r02f-p04b-p03-private.log')
    def test_19_drop_r00_source_gate(self):
        self.mutate(C.SOURCE,'run: python3 -B scripts/ci/r02f_p04b_p03_contract.py --check',
                    'run: echo skipped')
    def test_20_false_qualification(self):
        self.mutate(C.DOC,'**NOT_QUALIFIED until the P03 source tests and all six exact-HEAD hosted workflows pass.**',
                    '**PASS even if CI fails.**')
    def test_21_native_unverified_receipt_removed(self):
        self.mutate(C.HOST,"'untrusted_broadcast_not_install_proof':True",
                    "'untrusted_broadcast_not_install_proof':False")
    def test_22_offline_v2_proof_removed(self):
        self.mutate(C.HOST,"inv['files']['base_v2.apk']['sha256']==sha(fx/'base_v2.apk')",
                    "inv['files']['base_v2.apk']['sha256']")

if __name__=='__main__':unittest.main()
