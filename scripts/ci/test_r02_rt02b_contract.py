"""RT02B rejection source + mutation + adversarial receipt regressions."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]

def load(name:str,rel:str):
    spec=importlib.util.spec_from_file_location(name, ROOT/rel)
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

C=load('rt02b_contract','scripts/ci/r02_rt02b_contract.py')
F=load('rt02b_fixture','scripts/ci/r02_rt02b_fixture.py')
H=load('rt02b_hosted','scripts/ci/r02_rt02b_hosted.py')

class SourceMutationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ox-rt02b-contract-')
        self.root=Path(self.tmp.name)
        for rel in C.PATHS:
            p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/rel,p)
    def tearDown(self):self.tmp.cleanup()
    def mutate(self,rel:str,old:str,new:str):
        p=self.root/rel;s=p.read_text()
        self.assertIn(old,s)
        p.write_text(s.replace(old,new,1))
        errors=C.inspect(self.root)
        self.assertTrue(errors,rel+' mutation escaped source audit')
    def test_valid_source(self):self.assertEqual(C.inspect(self.root),[])
    def test_no_downgrade_case_rejected(self):
        self.mutate(C.HOST,"CASES=('signature_mismatch','downgrade')","CASES=('signature_mismatch',)")
    def test_missing_wrong_certificate_rejected(self):
        self.mutate(C.FIXTURE,'orig_cert!=wrong_cert','True')
    def test_source_bound_ci(self):
        self.mutate(C.WORKFLOW,'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"','true')
    def test_require_emulator_api36(self):
        self.mutate(C.WORKFLOW,'api-level: 36','api-level: 35')
    def test_require_exact_pinned_emulator_runner(self):
        self.mutate(C.WORKFLOW,'@a421e43855164a8197daf9d8d40fe71c6996bb0d','@main')
    def test_require_ephemeral_kvm(self):
        self.mutate(C.WORKFLOW,'test -c /dev/kvm','echo skip-kvm')
    def test_writes_forbidden(self):
        self.mutate(C.WORKFLOW,'contents: read','contents: write')
    def test_no_forged_stock_installer(self):
        self.mutate(C.DART,'StockInstaller(SettingsProvider()).installApk(','FakeInstaller(')
    def test_wrong_sha_not_silenced(self):
        self.mutate(C.DART,'sha256.convert(bytes).toString()!=fixtureDigest','false')
    def test_android_result_must_error(self):
        self.mutate(C.DART,'expect(result.isError,isTrue','expect(result.isSuccess,isTrue')
    def test_missing_negative_apk_fixture(self):
        self.mutate(C.WORKFLOW,'python3 -B scripts/ci/r02_rt02b_fixture.py --out','echo skip-rt02b-fixture --out')
    def test_missing_baseline_fixture(self):
        self.mutate(C.WORKFLOW,'python3 -B scripts/ci/r02_rt02_fixture.py --out','echo skip-base-fixture --out')
    def test_signing_key_cleanup(self):
        self.mutate(C.FIXTURE,'key.unlink(missing_ok=True)','pass')
    def test_runtime_bytes_changed_without_refusal(self):
        self.mutate(C.HOST,'digest[0]==expected','True')
    def test_runtime_version_changed_without_refusal(self):
        self.mutate(C.HOST,"need('2' in versions and '3' not in versions and '1' not in versions","need(True or '2' in versions and '3' not in versions and '1' not in versions")
    def test_device_ui_not_sampled_before_installer_call(self):
        self.mutate(C.HOST,"if installed and phase=='STOCK_INSTALLER_CALL' and taps[pending]==0:",
                    "if installed and taps[pending]==0:")
    def test_new_workflow_allowlist_required(self):
        self.mutate(C.R00,"'obtainx-r02-rt02b.yml'","'other.yml'")
    def test_source_contract_step_required(self):
        self.mutate(C.INHERITED,'python3 scripts/ci/r02_rt02b_contract.py --check','python3 -c "print(1)"')
    def test_no_runtime_claim_in_docs(self):
        self.mutate(C.DOC,'NOT full R02','fully qualified R02')
    def test_no_release(self):
        self.mutate(C.HOST,"'release_qualified':False","'release_qualified':True")
    def test_both_cases_must_be_attempted(self):
        self.mutate(C.HOST,"for step in ('START','INSTALL_CALL','REJECTED','ACKED')",
                    "for step in ('START','INSTALL_CALL','REJECTED')")
    def test_single_flutter_process_required(self):
        self.mutate(C.HOST,'subprocess.Popen(args', 'subprocess.run(args')
    def test_host_ack_barrier_required(self):
        self.mutate(C.HOST,'state.acks[pending].set()', 'pass  # skip ack')
    def test_exact_independent_android_proof_required(self):
        self.mutate(C.HOST,'proof=baseline_unchanged(fixtures)',
                    "proof={'installed_original_intact':True}")
    def test_ordered_dart_events_required(self):
        self.mutate(C.HOST,'events==EVENTS[:len(events)]','True')
    def test_dart_ack_required(self):
        self.mutate(C.DART,'await awaitHostAck(testCase)','await Future<void>.delayed(Duration.zero)')
    def test_both_compile_time_sha_required(self):
        self.mutate(C.DART,'OX_R02B_DOWNGRADE_SHA256', 'OX_R02B_SINGLE_SHA256')

class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ox-rt02b-proof-')
        self.out=Path(self.tmp.name)
        self.source='a'*40;self.run='1001'
        def case(name,taps=0):
            return {'case':name,'stock_installer_error_observed':True,
                    'installed_original_intact':True,'version_code':2,
                    'installed_path_count':1,'base_sha256':'c'*64,
                    'flutter_log_sha256':'d'*64,'android_confirmation_count':taps}
        self.record={'schema':2,'status':'PASS_TWO_REAL_ANDROID_REJECTIONS',
            'source_sha':self.source,'run_id':self.run,'hosted_emulator_only':True,
            'physical_device_qualified':False,'full_r02_matrix_qualified':False,
            'release_qualified':False,'publication_allowed':False,
            'backend':'production StockInstaller',
            'flutter_launches':1, 'host_acknowledgement_order':list(H.CASES),
            'session_log_sha256':'d'*64,
            'android_negative_cases':[case('signature_mismatch'),case('downgrade',1)]}
        self.write()
    def tearDown(self):self.tmp.cleanup()
    def write(self):(self.out/H.RECEIPT).write_text(json.dumps(self.record))
    def verify(self):
        with patch.object(H.base,'identity_check',return_value=(self.source,self.run)):
            return H.verify(self.out)
    def test_valid_receipt(self):self.assertEqual(self.verify(),0)
    def test_runtime_receipt_missing_case_refused(self):
        self.record['android_negative_cases'].pop();self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_wrong_source_refused(self):
        self.record['source_sha']='b'*40;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_failed_status_refused(self):
        self.record['status']='FAILED';self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_wrong_case_order_refused(self):
        self.record['android_negative_cases'].reverse();self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_platform_error_missing_refused(self):
        self.record['android_negative_cases'][0]['stock_installer_error_observed']=False;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_wrong_version_refused(self):
        self.record['android_negative_cases'][1]['version_code']=1;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_changed_apk_sha_refused(self):
        self.record['android_negative_cases'][1]['base_sha256']='b'*64;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_fake_dialog_count_refused(self):
        self.record['android_negative_cases'][1]['android_confirmation_count']=2;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_full_matrix_false(self):
        self.record['full_r02_matrix_qualified']=True;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_release_false(self):
        self.record['release_qualified']=True;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_wrong_installed_path_count(self):
        self.record['android_negative_cases'][0]['installed_path_count']=2;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_more_than_one_flutter_launch_refused(self):
        self.record['flutter_launches']=2;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_reordered_host_ack_refused(self):
        self.record['host_acknowledgement_order'].reverse();self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_missing_host_ack_refused(self):
        self.record['host_acknowledgement_order'].pop();self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_wrong_session_log_hash_refused(self):
        self.record['android_negative_cases'][1]['flutter_log_sha256']='e'*64;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_missing_session_hash_refused(self):
        self.record.pop('session_log_sha256');self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_bad_receipt_schema_refused(self):
        self.record['schema']=1;self.write()
        with self.assertRaises(H.Refused):self.verify()

class FixtureSafety(unittest.TestCase):
    def test_baseline_and_wrong_certificate_names_distinct(self):
        self.assertEqual(F.WRONG,'wrong_signer_v3.apk')
        self.assertEqual(F.BASE,'base_v2.apk')
        self.assertNotEqual(F.WRONG,F.BASE)
    def test_case_identity(self):
        self.assertEqual(H.CASES,('signature_mismatch','downgrade'))
    def test_source_declares_no_real_device(self):
        self.assertIn("'physical_device_qualified':False",(ROOT/C.HOST).read_text())

if __name__=='__main__':unittest.main()
