"""RT02C source, archive fixture, and fail-closed negative runtime receipt tests."""
from __future__ import annotations
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/ci'))

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module
C=load('r02_rt02c_contract','scripts/ci/r02_rt02c_contract.py')
F=load('r02_rt02c_fixture','scripts/ci/r02_rt02c_fixture.py')
H=load('r02_rt02c_hosted','scripts/ci/r02_rt02c_hosted.py')

class SourceMutations(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(prefix='ox-rt02c-source-')
        self.root=Path(self.t.name)
        for name in C.PATHS:
            src=ROOT/name;dst=self.root/name;dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(src,dst)
    def tearDown(self):self.t.cleanup()
    def mutation(self,rel,original,changed):
        path=self.root/rel;text=path.read_text()
        self.assertIn(original,text,'stale test anchor '+original)
        path.write_text(text.replace(original,changed,1))
        self.assertNotEqual(C.inspect(self.root),[],f'mutation escaped: {rel} {original}')
    def test_valid_source(self):self.assertEqual(C.inspect(self.root),[])
    def test_new_workflow_allowlist(self):
        self.mutation(C.R00,"'obtainx-r02-rt02c.yml'","'rogue-release.yml'")
    def test_new_workflow_mandatory(self):
        self.mutation(C.WF,'permissions:\n  contents: read','permissions:\n  contents: write')
    def test_sha_checkout_required(self):
        self.mutation(C.WF,'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"','true')
    def test_action_pin_required(self):
        self.mutation(C.WF,'@a421e43855164a8197daf9d8d40fe71c6996bb0d','@main')
    def test_no_older_sdk(self):
        self.mutation(C.WF,'api-level: 36','api-level: 34')
    def test_no_kvm_bypass(self):
        self.mutation(C.WF,'test -c /dev/kvm','echo skip')
    def test_prebuild_mandatory(self):
        self.mutation(C.WF,'python3 -B scripts/ci/r02_rt02c_fixture.py --out','echo fake-build --out')
    def test_independent_verification_mandatory(self):
        self.mutation(C.WF,'python3 -B scripts/ci/r02_rt02c_hosted.py verify --out','echo never-verify --out')
    def test_evidence_upload_mandatory(self):
        self.mutation(C.WF,'rt02c-progress.json','raw-test-logs.txt')
    def test_no_unaudited_source_gate(self):
        self.mutation(C.SOURCE_WF,'python3 scripts/ci/r02_rt02c_contract.py --check','echo pass')
    def test_no_mock_installer(self):
        self.mutation(C.DART,'StockInstaller(SettingsProvider()).installApk(','fakeInstaller(')
    def test_extract_zip_required(self):
        self.mutation(C.DART,'extractZipOffIsolate(','fakeExtractor(')
    def test_extract_tar_required(self):
        self.mutation(C.DART,'extractTarballOffIsolate(','fakeExtractor(')
    def test_archive_digest_required(self):
        self.mutation(C.DART,'sha256.convert(bytes).toString() != archiveSha','false')
    def test_single_session_control_body_must_have_explicit_length(self):
        self.mutation(C.DART, 'request.contentLength = payload.length;',
                      'request.contentLength = -1;')
    def test_single_session_control_body_must_send_verified_bytes(self):
        self.mutation(C.DART, 'request.add(payload);',
                      'request.write(jsonEncode(body));')
    def test_extracted_apk_digest_required(self):
        self.mutation(C.DART,'actual.toString() != expected','false')
    def test_resolver_required(self):
        self.mutation(C.DART,'resolveInstallBundlePlan(','fakePlanner(')
    def test_split_session_required(self):
        self.mutation(C.DART,'expect(plan.sessionPaths.length, 2)','expect(plan.sessionPaths.length, 1)')
    def test_no_missing_tar_case(self):
        self.mutation(C.FIX,"POSITIVE=('apks','apkm','xapk','zip','tar.gz')","POSITIVE=('apks','apkm','xapk','zip')")
    def test_preinstall_rejects_traversal(self):
        self.mutation(C.FIX,"members['../escape.apk']=base","pass # traversal removed")
    def test_preinstall_rejects_ambiguous(self):
        self.mutation(C.FIX,"members['payload/another-base.apk']=base","pass # ambiguity removed")
    def test_no_false_full_matrix(self):
        self.mutation(C.HOST,"'full_r02_matrix_qualified':False","'full_r02_matrix_qualified':True")
    def test_no_false_user_import(self):
        self.mutation(C.HOST,"'user_facing_import_qualified':False","'user_facing_import_qualified':True")
    def test_no_false_release(self):
        self.mutation(C.HOST,"'release_qualified':False","'release_qualified':True")
    def test_no_skip_actual_installed_bytes(self):
        self.mutation(C.SINGLE, 'self.base.installed_state(2, True, self.fixtures)', 'dict()')
    def test_no_skip_negative_proof(self):
        self.mutation(C.SINGLE, 'not self.called and self.taps == 0', 'True')
    def test_stale_r00_fixture_test(self):
        self.mutation(C.R00_TEST,"'obtainx-r02-rt02c.yml'","'obtainx-r02-old.yml'")
    def test_no_unbounded_pre_dart_retry(self):
        self.mutation(C.SINGLE, 'self.launches = 1',
                      'self.launches = 1\n        for attempt in (1, 2): break')
    def test_no_bypass_single_session_installer_proof(self):
        self.mutation(C.SINGLE, 'self.base.installed_state(2, True, self.fixtures)', 'dict()')
    def test_no_bypass_single_session_negative_baseline(self):
        self.mutation(C.SINGLE, 'self.H.baseline_v1(self.fixtures)', 'dict()')
    def test_no_session_handshake_bypass(self):
        self.mutation(C.DART, "await control('prepare', name)", "await fakePrepare(name)")
    def test_no_second_flutter_launch(self):
        self.mutation(C.SINGLE, 'self.launches = 1', 'self.launches = 2')
    def test_no_skip_live_signed_v1_staging(self):
        self.mutation(C.SINGLE,
                      "self.base.adb('install', '-t', str(self.fixtures / 'base_v1.apk')",
                      "self.base.adb('install', '-t', str(self.fixtures / 'fake_v1.apk')")
    def test_no_skip_dart_case_evidence(self):
        self.mutation(C.DART,'OX_R02C_DART_STAGE=PREINSTALL_REFUSED','SKIPPED_VALIDATION')

class ArchiveFixtures(unittest.TestCase):
    def setUp(self):
        self.base=b'disposable-ci-base-apk-bytes'*60
        self.split=b'disposable-ci-split-apk-bytes'*60
    def test_exact_seven_archive_cases(self):
        self.assertEqual(H.CASES,('apks','apkm','xapk','zip','tar.gz','traversal','ambiguous'))
        self.assertEqual(set(F.NAMES),{H.filename(x) for x in H.CASES})
    def test_all_positive_contain_same_signed_members(self):
        for kind in F.POSITIVE:
            entries=F.archive_entries(kind,self.base,self.split)
            self.assertEqual(entries['payload/base.apk'],self.base)
            self.assertEqual(entries['payload/config.x86_64.apk'],self.split)
    def test_all_zips_roundtrip(self):
        for kind in ('apks','apkm','xapk','zip'):
            raw=F.pack_zip(F.archive_entries(kind,self.base,self.split))
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                self.assertEqual(archive.read('payload/base.apk'),self.base)
                self.assertEqual(archive.read('payload/config.x86_64.apk'),self.split)
                self.assertEqual(len(archive.namelist()),len(set(archive.namelist())))
    def test_tar_roundtrip(self):
        raw=F.pack_tar(F.archive_entries('tar.gz',self.base,self.split))
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
            self.assertEqual(archive.extractfile('payload/base.apk').read(),self.base)
            self.assertEqual(archive.extractfile('payload/config.x86_64.apk').read(),self.split)
    def test_traversal_is_genuine(self):
        raw=F.pack_zip(F.archive_entries('traversal',self.base,self.split))
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            self.assertIn('../escape.apk',z.namelist())
    def test_ambiguous_base_is_genuine(self):
        raw=F.pack_zip(F.archive_entries('ambiguous',self.base,self.split))
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            self.assertEqual(z.read('payload/base.apk'),z.read('payload/another-base.apk'))
    def test_formats_have_unique_bytes(self):
        values=[]
        for case in H.CASES:
            entries=F.archive_entries(case,self.base,self.split)
            raw=F.pack_tar(entries) if case=='tar.gz' else F.pack_zip(entries)
            values.append(hashlib.sha256(raw).hexdigest())
        self.assertEqual(len(set(values)),7)
    def test_refuse_unsupported_format(self):
        with self.assertRaises(RuntimeError):F.archive_entries('jar',self.base,self.split)
        with self.assertRaises(H.Refused):H.filename('apk')

class PreDartRetry(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(prefix='ox-rt02c-retry-');self.out=Path(self.t.name)
        self.fixtures=self.out/'fixtures';self.fixtures.mkdir()
        self.case='apks';self.log=self.out/'rt02c-apks.private.log'
        self.log.write_text('Running Gradle task assembleNormalDebug')
        (self.out/'rt02c-progress.json').write_text(json.dumps({
            'case':self.case,'android_confirmations':0}))
    def tearDown(self):self.t.cleanup()
    def eligible(self,error='Flutter RT02C case failed apks phase=GRADLE_BUILD'):
        with patch.object(H,'baseline_v1',return_value={'installed_original_intact':True}):
            return H.eligible_pre_dart_retry(self.out,self.fixtures,self.case,H.Refused(error))
    def test_pre_dart_retry_can_recover_transient_flutter(self):
        self.assertTrue(self.eligible())
    def test_no_retry_after_stock_installer(self):
        self.log.write_text('OX_R02C_DART_STAGE=INSTALL_CALL')
        self.assertFalse(self.eligible())
    def test_no_retry_after_refusal(self):
        self.log.write_text('OX_R02C_DART_STAGE=PREINSTALL_REFUSED')
        self.assertFalse(self.eligible())
    def test_no_retry_after_ui_action(self):
        (self.out/'rt02c-progress.json').write_text(json.dumps({
            'case':self.case,'android_confirmations':1}))
        self.assertFalse(self.eligible())
    def test_no_retry_for_other_failure(self):
        self.assertFalse(self.eligible('Installed split mismatch'))
    def test_no_retry_if_v1_package_changed(self):
        with patch.object(H,'baseline_v1',side_effect=H.Refused('v1 changed')):
            with self.assertRaises(H.Refused):
                H.eligible_pre_dart_retry(self.out,self.fixtures,self.case,
                   H.Refused('Flutter RT02C case failed apks phase=GRADLE_BUILD'))

class RuntimeReceipts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ox-rt02c-receipt-');self.out=Path(self.tmp.name)
        self.commit='a'*40;self.run='123456'
        cases=[]
        for index,case in enumerate(H.CASES):
            digest=hashlib.sha256(case.encode()).hexdigest()
            if case in F.POSITIVE:
                cases.append({'case':case,'archive_sha256':digest,'flutter_log_sha256':digest,
                  'installed_signed_members_verified':True,'version_code':2,'installed_path_count':2,
                  'config_x86_64_present':True,'android_confirmations':0})
            else:
                cases.append({'case':case,'archive_sha256':digest,'flutter_log_sha256':digest,
                  'preinstall_refused':True,'installed_original_intact':True,'version_code':1,
                  'installed_path_count':1,'android_confirmations':0})
        for index,item in enumerate(cases):
            item['process_launch']=1
            item['boundary_index']=index
        self.data={'schema':1,'status':'PASS_FIVE_ARCHIVES_TWO_PREINSTALL_REFUSALS',
                   'flutter_launches':1,'session_log_sha256':hashlib.sha256(b'session').hexdigest(),
                   'runner_probe_count':27,'runner_probe_skipped':180,
                   'source_sha':self.commit,'run_id':self.run,'hosted_emulator_only':True,
                   'physical_device_qualified':False,'full_r02_matrix_qualified':False,
                   'user_facing_import_qualified':False,'release_qualified':False,
                   'publication_allowed':False,'backend':'production StockInstaller','cases':cases}
        self.write()
    def tearDown(self):self.tmp.cleanup()
    def write(self):(self.out/H.RECEIPT).write_text(json.dumps(self.data))
    def verify(self):
        with patch.object(H.base,'identity_check',return_value=(self.commit,self.run)):
            return H.verify(self.out)
    def test_valid_receipt(self):self.assertEqual(self.verify(),0)
    def test_opt06_missing_probe_count_refused(self):
        del self.data['runner_probe_count'];self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_opt06_missing_skipped_count_refused(self):
        del self.data['runner_probe_skipped'];self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_opt06_negative_probe_count_refused(self):
        self.data['runner_probe_count']=-1;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_opt06_boolean_probe_count_refused(self):
        self.data['runner_probe_count']=True;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_opt06_excessive_skipped_count_refused(self):
        self.data['runner_probe_skipped']=6001;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_opt06_float_skipped_count_refused(self):
        self.data['runner_probe_skipped']=0.0;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_missing_single_process_proof(self):
        self.data['flutter_launches']=2;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_repeated_boundary_index(self):
        self.data['cases'][2]['boundary_index']=1;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_missing_case(self):
        self.data['cases'].pop();self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_reordered_case(self):
        self.data['cases'][0],self.data['cases'][1]=self.data['cases'][1],self.data['cases'][0];self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_mismatched_commit(self):
        self.data['source_sha']='b'*40;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_no_missing_split(self):
        self.data['cases'][0]['installed_path_count']=1;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_no_downgrade_positive(self):
        self.data['cases'][3]['version_code']=1;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_no_unverified_positive(self):
        self.data['cases'][0]['installed_signed_members_verified']=False;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_no_negative_wrong_version(self):
        self.data['cases'][-1]['version_code']=2;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_no_negative_unrecorded_refusal(self):
        self.data['cases'][-1]['preinstall_refused']=False;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_no_negative_installer_tap(self):
        self.data['cases'][-1]['android_confirmations']=1;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_no_false_user_import_admission(self):
        self.data['user_facing_import_qualified']=True;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_no_false_release_admission(self):
        self.data['release_qualified']=True;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_no_reused_archive_digest(self):
        self.data['cases'][0]['archive_sha256']=self.data['cases'][1]['archive_sha256'];self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_no_missing_log_sha(self):
        self.data['cases'][0]['flutter_log_sha256']='wrong';self.write()
        with self.assertRaises(H.Refused):self.verify()

if __name__=='__main__':unittest.main()
