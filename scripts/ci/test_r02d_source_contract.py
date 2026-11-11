"""RT02D local mutation tests: refuse weakening new compatibility/OBB guards."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('r02d_source_contract',
                                          ROOT/'scripts/ci/r02d_source_contract.py')
assert SPEC and SPEC.loader
MOD=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

class RT02DSourceMutations(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='obtainx-rt02d-')
        self.root=Path(self.tmp.name)
        for item in MOD.PATHS:
            to=self.root/item
            to.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/item,to)
    def tearDown(self):self.tmp.cleanup()
    def mutate(self,rel,before,after):
        p=self.root/rel
        text=p.read_text('utf8')
        self.assertIn(before,text)
        p.write_text(text.replace(before,after,1),'utf8')
        self.assertNotEqual(MOD.inspect(self.root),[],rel+' mutation escaped')
    def test_r02d_cli_check_flag_is_supported_and_read_only(self):
        run=subprocess.run(
            [sys.executable,'-B',str(ROOT/'scripts/ci/r02d_source_contract.py'),'--check'],
            cwd=ROOT,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,text=True,timeout=60,check=False)
        self.assertEqual(run.returncode,0,run.stdout+'\n'+run.stderr)
        self.assertIn('OX_RT02D_SOURCE_CONTRACT_PASS',run.stdout)

    def test_valid_source(self):self.assertEqual(MOD.inspect(self.root),[])
    def test_no_locale_gate_bypass(self):
        self.mutate(MOD.PLANNER,'Ambiguous language splits require locale evidence','accept languages blindly')
    def test_no_density_gate_bypass(self):
        self.mutate(MOD.PLANNER,'Ambiguous density splits require display evidence','accept all densities')
    def test_no_wrong_locale_select(self):
        self.mutate(MOD.PLANNER,'No compatible language configuration split','ignore locale mismatch')
    def test_no_duplicate_density(self):
        self.mutate(MOD.PLANNER,'Multiple APK splits for the same density','ignore density collision')
    def test_no_obb_boundary_bypass(self):
        self.mutate(MOD.PLANNER,"path.startsWith('$root/')",'true')
    def test_no_staging_traversal_bypass(self):
        self.mutate(MOD.PLANNER,"path.split('/').contains('..')",'false')
    def test_no_obb_host_fallback(self):
        self.mutate(MOD.PROVIDER,'OBB payload cannot be installed by this backend on Android 11+', 'continue without OBB')
    def test_android11_preinstall_sdk_gate_cannot_be_disabled(self):
        self.mutate(MOD.PROVIDER,
            'if (sdk >= 30) {\n          throw const FormatException(',
            'if (sdk >= 999) {\n          throw const FormatException(')
    def test_android11_runtime_sdk_gate_cannot_be_disabled(self):
        self.mutate(MOD.PROVIDER,
            'if (sdkInt >= _androidApiLevelR) {\n      throw const FormatException(',
            'if (sdkInt >= 999) {\n      throw const FormatException(')
    def test_no_noncontainer_obb_guard_bypass(self):
        self.mutate(MOD.PROVIDER,'obbFiles.isNotEmpty && !installer.wantsContainerHandoff','false')
    def test_no_r02d_flutter_skip(self):
        self.mutate(MOD.FLUTTER,'flutter test --no-pub test/r02d_device_compatibility_test.dart','echo skipped')
    def test_no_r02d_source_gate_skip(self):
        self.mutate(MOD.CONTRACTS,'python3 scripts/ci/r02d_source_contract.py --check','echo skipped')
    def test_no_dart_fixtures_removed(self):
        self.mutate(MOD.TEST,'refuses ambiguous density','ignores ambiguous density')

if __name__=='__main__':unittest.main()
