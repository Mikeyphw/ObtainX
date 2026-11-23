"""Source contract mutations: every weakened privilege/provenance guard refused."""
from __future__ import annotations
import importlib.util,shutil,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
S=importlib.util.spec_from_file_location('p04b_p02_source',ROOT/'scripts/ci/r02f_p04b_p02_contract.py')
assert S and S.loader
C=importlib.util.module_from_spec(S);S.loader.exec_module(C)
class P04BPositiveSourceMutations(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(prefix='ox-p04b-p02-src-');self.addCleanup(self.t.cleanup)
        self.root=Path(self.t.name)
        for path in C.PATHS:
            p=self.root/path;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/path,p)
    def mutate(self,path,old,new):
        p=self.root/path;s=p.read_text()
        self.assertEqual(s.count(old),1,'mutation anchor drift '+path+' '+old)
        p.write_text(s.replace(old,new,1))
        self.assertTrue(C.inspect(self.root),'source mutation escaped '+path)
    def test_00_valid(self):self.assertEqual(C.inspect(self.root),[])
    def test_01_no_hosted_signing(self):self.mutate(C.TARGET,"os.getenv('GITHUB_ACTIONS')=='true'","False")
    def test_02_no_android_approval(self):self.mutate(C.TARGET,'PackageInstaller.SessionParams.USER_ACTION_REQUIRED','0')
    def test_03_no_mutable_callback(self):self.mutate(C.TARGET,'PendingIntent.FLAG_MUTABLE','PendingIntent.FLAG_IMMUTABLE')
    def test_04_no_pkg_session_commit(self):self.mutate(C.TARGET,'session.commit(pending.getIntentSender())','// no commit')
    def test_05_no_session_fsync(self):self.mutate(C.TARGET,'session.fsync(output)','// no fsync')
    def test_06_no_sha_bound_dart(self):self.mutate(C.DART,'sha256.convert(bytes).toString() != _sha','false')
    def test_07_no_false_dart_success(self):self.mutate(C.DART,'expect(result.isSuccess, isFalse)','expect(result.isSuccess, isTrue)')
    def test_08_no_android_approval(self):self.mutate(C.HOST,"need(approvals==1,'system PackageInstaller approval not observed exactly once')","need(approvals>=0,'system PackageInstaller approval not observed exactly once')")
    def test_09_no_package_bytes(self):self.mutate(C.HOST,'package_observation(fx,2)','package_observation(fx,1)')
    def test_10_final_signed_success_receipt_required(self):
        self.mutate(C.HOST, "need(terminal=={\n             'sha256':inv['files']['base_v2.apk']['sha256'],\n             'status':'system_status_success'},",
                    "need(terminal=={\n             'sha256':inv['files']['base_v2.apk']['sha256'],\n             'status':'approval_pending'},")
    def test_11_no_source_bound_target(self):self.mutate(C.HOST,"obj['target_sha256']==tv['sha256']==sha(fx/target.APK)","obj['target_sha256']==tv['sha256']")
    def test_12_no_offline_log_hash(self):self.mutate(C.HOST,"obj['flutter_log_sha256']==sha(out/'r02f-p04b-p02-private.log')",'True')
    def test_13_no_ci_guard_drop(self):self.mutate(C.SOURCE,'run: python3 -B scripts/ci/r02f_p04b_p02_contract.py --check','run: echo omitted')
    def test_14_no_runtime_drop(self):self.mutate(C.RUNTIME,'python3 -B scripts/ci/r02f_p04b_p02_hosted.py run --out','python3 -B scripts/ci/other.py run --out')
    def test_15_no_false_scope(self):self.mutate(C.DOC,'**NOT_QUALIFIED**','**PASS**')
    def test_16_target_must_finish_after_session_commit(self):
        self.mutate(C.TARGET,'        finish();\n      }\n    } catch',
                    '        // left foreground\n      }\n    } catch')
    def test_17_foreground_must_wait_for_status_success(self):
        self.mutate(C.HOST, 'signed_success = (approvals==1 and',
                    'signed_success = (approvals>=0 and')
    def test_18_no_missing_bounded_progress(self):
        self.mutate(C.HOST,'OX_P04B_P02_PROGRESS','UNBOUNDED_DEBUG_LOG')
    def test_19_foreground_action_required(self):
        self.mutate(C.HOST,"base.adb('shell','am','start','-f','0x24000000','-n',",
                    "base.adb('shell','am','start','-f','0x0','-n',")
    def test_20_early_foreground_without_verified_approval_refused(self):
        self.mutate(C.HOST,'if signed_success and not foreground_restored:',
                    'if not foreground_restored:')
    def test_21_target_operation_inserted_before_finish_refused(self):
        self.mutate(C.TARGET,'        finish();\n      }\n    } catch',
                    '        status(this,"still_active");\n        finish();\n      }\n    } catch')
    def test_22_do_not_stop_at_flutter_exit(self):
        self.mutate(C.HOST, 'if flutter_done and signed_success and foreground_restored:',
                    'if flutter_done:')
    def test_23_status_only_early_failures_required(self):
        self.mutate(C.HOST, "need(out['status'] in allowed_status_only,",
                    'need(True,')
    def test_24_post_flutter_deadline_required(self):
        self.mutate(C.HOST, 'post_flutter_deadline = now + 120',
                    'post_flutter_deadline = None')
    def test_25_no_skipping_flutter_terminal_check(self):
        self.mutate(C.HOST, 'if flutter_done and post_flutter_deadline is None:',
                    'if False and post_flutter_deadline is None:')
    def test_26_device_sha_required_for_approval_success(self):
        self.mutate(C.HOST, "observed=={'status':'system_status_success','sha256':expected_v2}",
                    "observed.get('status')=='system_status_success'")

if __name__=='__main__':unittest.main()
