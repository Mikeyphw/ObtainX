"""R02 mutation tests: fail closed for unsafe source or obsolete CI assertions."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

MODULE=Path(__file__).with_name('r02_install_contract.py')
spec=importlib.util.spec_from_file_location('r02_install_contract', MODULE)
audit=importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(audit)
ROOT=MODULE.resolve().parents[2]

class R02InstallContracts(unittest.TestCase):
    PATHS=[
        'lib/services/install_bundle_plan.dart',
        'lib/providers/apps_provider_install.dart',
        'lib/providers/apps_provider.dart',
        'lib/app_sources/app_package_formats.dart',
        'test/r02_install_bundle_plan_test.dart',
        '.github/workflows/obtainx-r00-flutter.yml',
        '.github/workflows/obtainx-r00-contracts.yml',
        'docs/SECURITY_RELEASE_POLICY.md',
        'docs/R02_INSTALL_PLAN_AUDIT.md',
        'docs/R02_SOURCE_BASELINE.json',
    ]
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(prefix='oxr02-contract-')
        self.root=Path(self.t.name)
        for rel in self.PATHS:
            f=self.root/rel
            f.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/rel,f)
    def tearDown(self):
        self.t.cleanup()
    def mutate(self,rel,old,new):
        p=self.root/rel
        s=p.read_text()
        self.assertIn(old,s)
        p.write_text(s.replace(old,new,1))
    def refused(self):
        self.assertTrue(audit.inspect(self.root), 'mutation was not rejected')
    def test_clean_passes(self):
        self.assertEqual(audit.inspect(self.root),[])
    def test_legacy_first_apk_restored(self):
        self.mutate('lib/providers/apps_provider_install.dart','plan.baseApkPath','_preferMatchingApk(apkFiles, dir.appId)[0]')
        self.refused()
    def test_base_metadata_not_required(self):
        self.mutate('lib/services/install_bundle_plan.dart',
                    'Bundle requires exactly one unambiguous base APK','No base check needed')
        self.refused()
    def test_package_identity_check_removed(self):
        self.mutate('lib/services/install_bundle_plan.dart',
                    'expectedPackageName != packageName','false')
        self.refused()
    def test_split_version_validation_removed(self):
        self.mutate('lib/services/install_bundle_plan.dart',
                    'versionCode != versionCode','false')
        self.refused()
    def test_abi_gate_removed(self):
        self.mutate('lib/services/install_bundle_plan.dart',
                    'No compatible ABI configuration split','all ABIs accepted')
        self.refused()
    def test_min_sdk_gate_removed(self):
        self.mutate('lib/services/install_bundle_plan.dart',
                    'minSdkVersion! > deviceSdkVersion','false')
        self.refused()
    def test_container_handoff_not_validated(self):
        self.mutate('lib/providers/apps_provider_install.dart',
                    'expectedPackageName: dir.appId','expectedPackageName: null')
        self.refused()
    def test_bad_archive_inventory_cleanup_removed(self):
        self.mutate('lib/providers/apps_provider_install.dart',
                    'extracted.deleteSync(recursive: true)', '/* leak discarded archive */')
        self.refused()
    def test_bad_archive_inventory_cleanup_guard_disabled(self):
        self.mutate('lib/providers/apps_provider_install.dart',
                    'if (extracted.existsSync()) {', 'if (false) {')
        self.refused()
    def test_bad_archive_inventory_error_swallowed(self):
        self.mutate('lib/providers/apps_provider_install.dart',
                    '            extracted.deleteSync(recursive: true);\n          }\n          rethrow;',
                    '            extracted.deleteSync(recursive: true);\n          }\n          // error incorrectly ignored')
        self.refused()
    def test_unsafe_cleanup_with_decoy_token_elsewhere_refused(self):
        self.mutate('lib/providers/apps_provider_install.dart',
                    'extracted.deleteSync(recursive: true)',
                    '/* removed: extracted.deleteSync(recursive: true) */')
        self.refused()
    def test_obbs_moved_before_confirmation(self):
        self.mutate('lib/providers/apps_provider_install.dart',
                    'obbFiles.add(file)','await moveObbFile(file, dir.appId)')
        self.refused()
    def test_test_gate_deleted(self):
        self.mutate('.github/workflows/obtainx-r00-flutter.yml',
                    'flutter test --no-pub test/r02_install_bundle_plan_test.dart',
                    'echo ignored')
        self.refused()
    def test_source_ci_deleted(self):
        self.mutate('.github/workflows/obtainx-r00-contracts.yml',
                    'python3 scripts/ci/r02_install_contract.py --check',
                    'echo ignored')
        self.refused()
    def test_release_gate_bypassed(self):
        self.mutate('docs/SECURITY_RELEASE_POLICY.md',
                    'NO PUBLIC RELEASE QUALIFIED','RELEASE ALLOWED')
        self.refused()
    def test_baseline_receipt_modified(self):
        self.mutate('docs/R02_SOURCE_BASELINE.json',
                    '42859288599', '0')
        self.refused()

if __name__=='__main__':
    unittest.main()
