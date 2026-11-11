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

class ReceiptAndPackageProof(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(prefix='ox-rt02-proof-');self.out=Path(self.t.name)
        self.sha='a'*40;self.run='1234'
        self.valid={'schema':1,'status':'PASS_TWO_ANDROID_SYSTEM_SESSIONS','source_sha':self.sha,
                    'run_id':self.run,'hosted_emulator_only':True,
                    'physical_device_qualified':False,'full_r02_matrix_qualified':False,
                    'release_qualified':False,'publication_allowed':False,
                    'installer_backend':'production StockInstaller',
                    'scenarios':[{'scenario':'standalone','version_code':1,'installed_path_count':1,
                        'config_x86_64_present':False,'android_confirmations':1},
                        {'scenario':'split','version_code':2,'installed_path_count':2,
                        'config_x86_64_present':True,'android_confirmations':1}]}
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
    def test_wrong_version_refused(self):
        self.valid['scenarios'][1]['version_code']=1;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_installed_missing_base_refused(self):
        with patch.object(H,'adb',return_value='package:/data/app/fixture/split_config.x86_64.apk'):
            with self.assertRaises(H.Refused):H.installed_state(2,True,self.out)
    def test_fixture_names_are_isolated(self):
        self.assertEqual(F.PKG,H.FIXTURE)
        self.assertEqual(set(F.NAMES),{'base_v1.apk','base_v2.apk','config.x86_64.apk'})


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
