"""RT02 source & mutation gate: accepts no substitute for real Android evidence."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]

def load(name:str,path:str):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

C=load('r02_rt02_contract','scripts/ci/r02_rt02_contract.py')
H=load('r02_rt02_hosted','scripts/ci/r02_rt02_hosted.py')
F=load('r02_rt02_fixture','scripts/ci/r02_rt02_fixture.py')

class SourceMutations(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(prefix='ox-rt02-mut-')
        self.root=Path(self.t.name)
        for rel in C.PATHS:
            src=ROOT/rel; dst=self.root/rel
            dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
    def tearDown(self):self.t.cleanup()
    def mutation(self,rel,old,new):
        p=self.root/rel
        text=p.read_text();self.assertIn(old,text,'stale contract anchor: '+old)
        p.write_text(text.replace(old,new,1))
        errors=C.inspect(self.root)
        self.assertTrue(errors,'source mutation escaped audit: '+rel)
    def test_valid(self):self.assertEqual(C.inspect(self.root),[])
    def test_unreviewed_workflow(self):self.mutation(C.R00,"'obtainx-r02-rt02.yml'", "'hidden.yml'")
    def test_default_deny(self):self.mutation(C.R00,'unexpected = names - EXPECTED_WORKFLOWS','unexpected = set()')
    def test_no_write_permission(self):self.mutation(C.WORKFLOW,'contents: read','contents: write')
    def test_emulator_api36_required(self):self.mutation(C.WORKFLOW,'api-level: 36','api-level: 35')
    def test_kvm_required(self):self.mutation(C.WORKFLOW,'test -c /dev/kvm','echo skip-kvm')
    def test_runner_sha_pinned(self):self.mutation(C.WORKFLOW,'@a421e43855164a8197daf9d8d40fe71c6996bb0d','@main')
    def test_source_checkout(self):self.mutation(C.WORKFLOW,'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"','true')
    def test_real_flutter_test(self):self.mutation(C.HOST,"'flutter','test','integration_test/r02_real_installer_test.dart'", "'echo','run fake test'")
    def test_no_mock_installer(self):self.mutation(C.DART, 'StockInstaller(SettingsProvider()).installApk(', 'fakeInstaller(')
    def test_no_skip_confirm(self):self.mutation(C.HOST,'tap_count==1', 'tap_count>=0')
    def test_no_skip_actual_installed_hash(self):self.mutation(C.HOST,"digest[0]==expected[name]",'True')
    def test_no_skip_installed_version(self):self.mutation(C.HOST,"str(expected_version) in matches",'True')
    def test_both_scenarios(self):self.mutation(C.HOST,"for scenario in ('standalone','split')", "for scenario in ('standalone',)")
    def test_do_not_claim_full_r02(self):self.mutation(C.HOST,"'full_r02_matrix_qualified':False", "'full_r02_matrix_qualified':True")
    def test_do_not_claim_release(self):self.mutation(C.HOST,"'release_qualified':False", "'release_qualified':True")
    def test_signer_must_delete_temp_key(self):self.mutation(C.FIXTURE,'key.unlink(missing_ok=True)','pass  # omitted')
    def test_real_fixture_signing(self):self.mutation(C.FIXTURE,"str(signer), 'sign'", "'echo', 'sign'")
    def test_dart_sha(self):self.mutation(C.DART,"sha256.convert(data).toString() != expected",'false')
    def test_dart_const_version_required(self):
        # Flutter 3.47.6 flutter analyze treats prefer_const_declarations as a
        # failing diagnostic. Do not let this exact known regression return.
        self.mutation(C.DART,
            "const version = scenario == 'standalone' ? 1 : 2;",
            "final version = scenario == 'standalone' ? 1 : 2;")
    def test_dart_plan(self):self.mutation(C.DART,'resolveInstallBundlePlan(','fakePlan(')
    def test_missing_progress_artifact_rejected(self):
        self.mutation(C.WORKFLOW,'obtainx-rt02/progress.json','obtainx-rt02/lost.json')
    def test_timeout_not_silenced(self):
        self.mutation(C.HOST,'RT02_FLUTTER_TIMEOUT','IGNORED_TIMEOUT')
    def test_installer_stage_not_silenced(self):
        self.mutation(C.HOST,'phase=flutter_phase(logfile)',"phase='IGNORED'")
    def test_dart_instrumentation_not_silenced(self):
        self.mutation(C.DART,'OX_R02_RT02_DART_STAGE=INSTALL_CALL','IGNORED_STAGE')
    def test_r00_test_must_be_updated(self):self.mutation(C.R00_TEST,'test_reviewed_rt02_required_and_release_is_still_prohibited','test_fake')
    def test_ci_source_gate(self):self.mutation(C.SOURCE_GATE,'run: python3 scripts/ci/r02_rt02_contract.py --check','run: true')
    def test_missing_dart_dep(self):self.mutation(C.PUBSPEC,'integration_test:', 'ignored_integration_test:')

class HF06FlutterPreDartRecovery(unittest.TestCase):
    def test_hf06_flutter_categories_are_allowlisted(self):
        with tempfile.TemporaryDirectory(prefix='ox-hf06-diagnostic-') as td:
            log=Path(td)/'flutter.log'
            log.write_text('Installing APK...\nError: INSTALL_FAILED_TEST_ONLY\n'
                           'secret_token_01234567890=should-never-be-emitted')
            category,started,digest=H.classify_flutter_failure(log)
            self.assertEqual(category,'ANDROID_APK_INSTALL_REJECTED')
            self.assertFalse(started)
            self.assertRegex(digest,r'^[0-9a-f]{64}$')

    def test_hf06_flutter_logs_are_not_exposed(self):
        with tempfile.TemporaryDirectory(prefix='ox-hf06-redacted-') as td:
            out=Path(td)
            log=out/'flutter.log'
            log.write_text('Error installing APK: failure\nprivate_token=aFakeSecret\n')
            H.record_flutter_progress(out,'standalone','TEST_APK_INSTALL',22,True,0)
            category,started=H.record_flutter_failure(out,'standalone',1,'TEST_APK_INSTALL',log,1)
            self.assertEqual(category,'FLUTTER_INSTALL_BRIDGE_FAILED')
            data=(out/'progress.json').read_text()
            self.assertNotIn('private_token',data)
            self.assertNotIn('aFakeSecret',data)
            self.assertIn('flutter_error_category',data)
            self.assertFalse(started)

    def test_hf06_no_uiautomator_before_installer(self):
        import inspect
        source=inspect.getsource(H.one_scenario)
        self.assertIn("phase in ('STOCK_INSTALLER_CALL','STOCK_INSTALLER_RETURNED')",source)
        self.assertNotIn('if installed_app and tap_count<2:',source)
        self.assertLess(source.index('phase in'),source.index('if _tap_confirmed_install_dialog()'))

    def test_hf06_pre_dart_recovery_requires_fixture_absent(self):
        import inspect
        source=inspect.getsource(H.one_scenario)
        self.assertIn('attempt==1 and not dart_started and tap_count==0',source)
        self.assertIn('empty_or_expected_package()',source)
        self.assertIn("installed_state(1,False,out/'fixtures')",source)
        self.assertIn("if scenario=='split':",source)
        self.assertIn("phase in ('FLUTTER_STARTING','GRADLE_BUILD','TEST_APK_INSTALL')",source)

    def test_hf06_failure_does_not_mark_installer_pass(self):
        import inspect
        source=inspect.getsource(H.one_scenario)
        self.assertLess(source.index('if not test_success:'), source.index('actual=installed_state('))
        self.assertLess(source.index('actual=installed_state('),source.index('approval_path=classify_android_approval('))

class ReceiptAndPackageProof(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(prefix='ox-rt02-proof-');self.out=Path(self.t.name)
        self.sha='a'*40;self.run='1234'
        self.valid={'schema':2,'status':'PASS_TWO_ANDROID_SYSTEM_SESSIONS','source_sha':self.sha,
                    'run_id':self.run,'hosted_emulator_only':True,
                    'physical_device_qualified':False,'full_r02_matrix_qualified':False,
                    'release_qualified':False,'publication_allowed':False,
                    'installer_backend':'production StockInstaller',
                    'flutter_launches':1,
                    'host_acknowledgement_order':['standalone','split'],
                    'dart_event_order':[f'{case}:{stage}' for case in ('standalone','split')
                                        for stage in ('START','INSTALL_CALL','INSTALL_RETURNED','ACKED')],
                    'session_log_sha256':'e'*64,
                    'scenarios':[{'scenario':'standalone','version_code':1,'installed_path_count':1,
                        'config_x86_64_present':False,'android_confirmations':1,
                        'approval_path':'explicit_dialog'},
                        {'scenario':'split','version_code':2,'installed_path_count':2,
                        'config_x86_64_present':True,'android_confirmations':1,
                        'approval_path':'explicit_dialog'}]}
        self.write()
    def tearDown(self):self.t.cleanup()
    def write(self):(self.out/'rt02-receipt.json').write_text(json.dumps(self.valid))
    def verify(self):
        with patch.object(H,'identity_check',return_value=(self.sha,self.run)):
            H.verify(self.out)
    def test_valid_receipt(self):self.verify()
    def test_wrong_source_refused(self):
        self.valid['source_sha']='b'*40;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_status_not_run_refused(self):
        self.valid['status']='NOT_RUN';self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_missing_split_proof_refused(self):
        self.valid['scenarios'].pop();self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_false_release_refused(self):
        self.valid['release_qualified']=True;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_false_full_matrix_refused(self):
        self.valid['full_r02_matrix_qualified']=True;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_wrong_install_count_refused(self):
        self.valid['scenarios'][1]['installed_path_count']=1;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_no_approval_refused(self):
        self.valid['scenarios'][0]['android_confirmations']=0;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_split_zero_dialog_valid_only_when_exact_platform_proof_recorded(self):
        self.valid['scenarios'][1]['android_confirmations']=0
        self.valid['scenarios'][1]['approval_path']='platform_committed_no_dialog'
        self.write()
        self.verify()

    def test_split_zero_dialog_with_false_approval_path_refused(self):
        self.valid['scenarios'][1]['android_confirmations']=0
        self.write()
        with self.assertRaises(H.Refused):self.verify()

    def test_split_no_dialog_missing_base_refused(self):
        self.valid['scenarios'][1]['android_confirmations']=0
        self.valid['scenarios'][1]['approval_path']='platform_committed_no_dialog'
        self.valid['scenarios'][1]['installed_path_count']=1
        self.write()
        with self.assertRaises(H.Refused):self.verify()

    def test_split_no_dialog_wrong_version_refused(self):
        self.valid['scenarios'][1]['android_confirmations']=0
        self.valid['scenarios'][1]['approval_path']='platform_committed_no_dialog'
        self.valid['scenarios'][1]['version_code']=1
        self.write()
        with self.assertRaises(H.Refused):self.verify()

    def test_split_fake_extra_approval_refused(self):
        self.valid['scenarios'][1]['android_confirmations']=2
        self.write()
        with self.assertRaises(H.Refused):self.verify()

    def test_split_wrong_approval_path_refused(self):
        self.valid['scenarios'][1]['approval_path']='platform_committed_no_dialog'
        self.write()
        with self.assertRaises(H.Refused):self.verify()

    def test_wrong_version_refused(self):
        self.valid['scenarios'][1]['version_code']=1;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_installed_missing_base_refused(self):
        with patch.object(H,'adb',return_value='package:/data/app/fixture/split_config.x86_64.apk'):
            with self.assertRaises(H.Refused):H.installed_state(2,True,self.out)
    def test_fixture_names_are_isolated(self):
        self.assertEqual(F.PKG,H.FIXTURE)
        self.assertEqual(set(F.NAMES),{'base_v1.apk','base_v2.apk','config.x86_64.apk'})


class RT02AndroidApprovalClassification(unittest.TestCase):
    def good_state(self,scenario):
        if scenario=='standalone':
            return {'version_code':1,'installed_path_count':1,'config_x86_64_present':False}
        return {'version_code':2,'installed_path_count':2,'config_x86_64_present':True}

    def test_standalone_first_install_approval_required(self):
        self.assertEqual(H.classify_android_approval('standalone',1,self.good_state('standalone')),
                         'explicit_dialog')
        with self.assertRaises(H.Refused):
            H.classify_android_approval('standalone',0,self.good_state('standalone'))

    def test_split_exact_platform_committed_without_dialog(self):
        self.assertEqual(H.classify_android_approval('split',0,self.good_state('split')),
                         'platform_committed_no_dialog')
        self.assertEqual(H.classify_android_approval('split',1,self.good_state('split')),
                         'explicit_dialog')

    def test_split_no_dialog_requires_verified_split_and_version(self):
        for wrong in ({'version_code':1,'installed_path_count':2,'config_x86_64_present':True},
                      {'version_code':2,'installed_path_count':1,'config_x86_64_present':True},
                      {'version_code':2,'installed_path_count':2,'config_x86_64_present':False},
                      {}):
            with self.assertRaises(H.Refused):
                H.classify_android_approval('split',0,wrong)

    def test_no_double_or_negative_approval(self):
        for count in (-1,2,False,True):
            with self.assertRaises(H.Refused):
                H.classify_android_approval('split',count,self.good_state('split'))

    def test_no_dialog_classification_source_cannot_bypass_installed_state(self):
        with tempfile.TemporaryDirectory(prefix='ox-rt02-hf05-mut-') as td:
            root=Path(td)
            for rel in C.PATHS:
                src=ROOT/rel;dst=root/rel;dst.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(src,dst)
            p=root/C.HOST
            source=p.read_text()
            anchor="actual=installed_state(1 if scenario=='standalone' else 2,"
            self.assertIn(anchor,source)
            p.write_text(source.replace(anchor,"actual=installed_state(1 if scenario=='split' else 2,",1))
            self.assertTrue(C.inspect(root))


class RT02FixtureManifestRegression(unittest.TestCase):
    def test_config_split_targets_base_without_invalid_attribute(self):
        manifest=F.fixture_manifest(2, True)
        self.assertIn('split="config.x86_64"',manifest)
        self.assertIn('android:versionCode="2"',manifest)
        self.assertNotIn('configForSplit',manifest)
        self.assertNotIn('android:isFeatureSplit',manifest)

    def test_standalone_manifest_has_no_split_identity(self):
        for version in (1,2):
            manifest=F.fixture_manifest(version, False)
            self.assertNotIn('split="', manifest)
            self.assertNotIn('configForSplit', manifest)
            self.assertIn(f'android:versionCode="{version}"', manifest)
        with self.assertRaises(RuntimeError):
            F.fixture_manifest(1, True)
        with self.assertRaises(RuntimeError):
            F.fixture_manifest(3, False)

    def test_namespaced_config_for_split_is_refused(self):
        import inspect
        # Mutation must be injected into generator source, not documentation.
        with tempfile.TemporaryDirectory(prefix='ox-rt02-fixture-mut-') as td:
            root=Path(td)
            for rel in C.PATHS:
                dst=root/rel;dst.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/rel,dst)
            f=root/C.FIXTURE
            old="'split=\"config.x86_64\" ' if split else ''"
            new="'split=\"config.x86_64\" android:configForSplit=\"base\" ' if split else ''"
            self.assertIn(old,f.read_text())
            f.write_text(f.read_text().replace(old,new,1))
            self.assertTrue(any('invalid configForSplit' in e for e in C.inspect(root)))

    def test_fixture_preflight_is_mandatory(self):
        with tempfile.TemporaryDirectory(prefix='ox-rt02-fixture-ci-mut-') as td:
            root=Path(td)
            for rel in C.PATHS:
                dst=root/rel;dst.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/rel,dst)
            f=root/C.WORKFLOW
            anchor='- name: Compile and validate disposable APK fixtures before emulator boot'
            self.assertIn(anchor,f.read_text())
            f.write_text(f.read_text().replace(anchor,'- name: Skip fixture preflight',1))
            self.assertTrue(any('pre-emulator hard gate' in e for e in C.inspect(root)))


if __name__=='__main__':unittest.main()
