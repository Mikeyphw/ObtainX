"""Adversarial scope tests: skipped heavy jobs never equal runtime qualification."""
from __future__ import annotations
import tempfile
import subprocess
import unittest
from pathlib import Path
from obtainx_ci_policy import classify, paths_between, RISK_GLOBS

class CISelection(unittest.TestCase):
    def test_docs_only_uses_source(self):
        x=classify(['docs/README.md']); self.assertFalse(x['full_flutter']); self.assertFalse(x['targeted_flutter']); self.assertTrue(x['source_contracts'])
    def test_regular_flutter_is_targeted(self):
        x=classify(['lib/components/app_detail_widgets.dart']); self.assertTrue(x['targeted_flutter']); self.assertFalse(x['full_flutter'])
    def test_test_only_is_targeted(self):
        x=classify(['test/example_test.dart']); self.assertTrue(x['targeted_flutter'])
    def test_installer_source_requires_full(self):
        for path in ('lib/installers/external_installer.dart','lib/services/install_bundle_plan.dart',
                     'lib/providers/apps_provider_install.dart','lib/services/verified_obb_delivery.dart'):
            self.assertTrue(classify([path])['full_flutter'],path)
    def test_adversarial_source_and_workflows_require_full(self):
        for path in ('.github/workflows/obtainx-r02-rt02c.yml','scripts/ci/r02_rt02c_hosted.py',
                     'scripts/ci/obtainx_ci_policy.py','android/app/build.gradle',
                     'pubspec.lock','docs/SECURITY_RELEASE_POLICY.md'):
            self.assertTrue(classify([path])['full_flutter'],path)
    def test_unknown_github_configuration_fails_closed(self):
        self.assertTrue(classify(['.github/codeowners'])['full_flutter'])
    def test_manual_forces_full(self):
        self.assertTrue(classify(['docs/README.md'],force=True)['full_flutter'])
    def test_empty_inventory_refused(self):
        with self.assertRaises(ValueError):classify([])
    def test_unsafe_inventory_refused(self):
        for path in ('/etc/passwd','dir/../foo','hi\\there'):
            with self.assertRaises(ValueError):classify([path])
    def test_risk_globs_present(self):
        self.assertIn('lib/installers/**',RISK_GLOBS)
        self.assertIn('.github/workflows/**',RISK_GLOBS)
    def test_exact_sha_git_boundary(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            def git(*args):
                return subprocess.check_output(['git',*args],cwd=root,text=True).strip()
            git('init','-q','-b','main');git('config','user.name','CI Fixture');git('config','user.email','ci@example.invalid')
            (root/'README').write_text('base\n');git('add','README');git('commit','-qm','base')
            base=git('rev-parse','HEAD')
            (root/'test').mkdir();(root/'test/example_test.dart').write_text('test\n')
            git('add','test');git('commit','-qm','test')
            head=git('rev-parse','HEAD')
            self.assertEqual(paths_between(base,head,root=root),['test/example_test.dart'])
            with self.assertRaises((ValueError,RuntimeError)):paths_between(head,base,root=root)
            with self.assertRaises(ValueError):paths_between('a'*7,head,root=root)

if __name__=='__main__':unittest.main()
