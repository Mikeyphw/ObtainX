"""RT02F mutation tests for external handoff and selective high-risk CI."""
from __future__ import annotations
import importlib.util
import tempfile
import unittest
from pathlib import Path
from shutil import copyfile
ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('r02f_source_contract',ROOT/'scripts/ci/r02f_source_contract.py')
assert SPEC and SPEC.loader
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)
class RT02FMutation(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(prefix='ox-r02f-');self.addCleanup(self.t.cleanup)
        self.root=Path(self.t.name)
        for p in M.PATHS:
            dst=self.root/p;dst.parent.mkdir(parents=True,exist_ok=True);copyfile(ROOT/p,dst)
    def mutate(self,p,old,new):
        f=self.root/p;s=f.read_text('utf8');self.assertIn(old,s,'stale anchor '+p)
        f.write_text(s.replace(old,new,1),'utf8')
        self.assertTrue(M.inspect(self.root),'mutation undetected '+p)
    def test_clean_passes(self):self.assertEqual(M.inspect(self.root),[])
    def test_native_change_not_success(self):
        self.mutate(M.SOURCE,'return InstallResult.handedOff();','return InstallResult.success();')
    def test_external_callback_must_use_classifier(self):
        self.mutate(M.EXTERNAL,'classifyUnverifiedThirdPartyHandoff(changed)','InstallResult.success()')
    def test_pending_indicator_guard(self):
        self.mutate(M.PROVIDER,"if (pending != null) {\n              _awaitThirdPartyInstallConfirmation(dir.appId);","if (true) {\n              _awaitThirdPartyInstallConfirmation(dir.appId);")
    def test_selected_flutter_test(self):
        self.mutate(M.FLUTTER,'flutter test --no-pub test/r02f_external_handoff_test.dart','echo test skipped')
    def test_targeted_vs_full_not_disabled(self):
        self.mutate(M.FLUTTER,'needs.scope.outputs.full_flutter','false')
    def test_scope_classifier_must_exist(self):
        self.mutate(M.POLICY,"run_git('merge-base','--is-ancestor'","run_git('rev-parse','--is-ancestor'")
    def test_source_contract_mandatory(self):
        self.mutate(M.SOURCE_CI,'python3 -B scripts/ci/r02f_source_contract.py --check','echo skip')
    def test_android_high_risk_path(self):
        self.mutate(M.HEAVY[1],"      - 'lib/installers/**'", "      - 'docs/**'")
    def test_manual_full_workflow_retained(self):
        self.mutate(M.HEAVY[2],'  workflow_dispatch:', '  # no manual gate')
if __name__=='__main__': unittest.main()
