"""RT02F P02 negative tests: do not silently weaken real session-abandon proof."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('r02f_p02_contract',ROOT/'scripts/ci/r02f_p02_contract.py')
assert SPEC and SPEC.loader
C=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)

class RT02FP02Contracts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ox-rt02f-p02-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for rel in C.PATHS:
            target=self.root/rel
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/rel,target)

    def mutation(self,path,old,new):
        target=self.root/path
        contents=target.read_text('utf8')
        self.assertIn(old,contents,'stale mutation fixture '+path+' '+old)
        target.write_text(contents.replace(old,new,1),'utf8')
        self.assertTrue(C.inspect(self.root),'unsafe mutation escaped '+path)

    def test_contract_accepts_exact_source(self):
        self.assertEqual(C.inspect(self.root),[])

    def test_actual_cli(self):
        p=subprocess.run([sys.executable,'-B',str(ROOT/C.HOST),'--help'],
            cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            check=False,text=True,timeout=30)
        # Host script imports platform helpers, not SDK; --help is read-only.
        self.assertEqual(p.returncode,0,p.stderr)
        p=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/ci/r02f_p02_contract.py'),'--check'],
            cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            check=False,text=True,timeout=30)
        self.assertEqual(p.returncode,0,p.stdout+'\n'+p.stderr)

    def test_cancel_session_parsing_negative(self):
        # Evaluate the pure regex without importing production Android helpers.
        import re
        host=(self.root/C.HOST).read_text('utf8')
        self.assertIn('SID = re.compile(',host)
        expression=r'^Success: created install session \[([1-9][0-9]{0,9})\]$'
        self.assertIsNotNone(re.fullmatch(expression,'Success: created install session [123]'))
        for bad in ('Failure: created install session [123]',
                    'Success: created install session [0]',
                    'Success: created install session [-1]',
                    'Success: created install session [123] garbage',
                    'Success: created install session [123]; other'):
            self.assertIsNone(re.fullmatch(expression,bad))

    def test_source_mutation_rejected(self):
        self.mutation(C.HOST,"package_session('ABANDON_'+kind.upper(),",
                      "package_session('COMMIT_'+kind.upper(),")

    def test_cmd_package_not_legacy_pm(self):
        self.mutation(C.HOST,"'shell','cmd','package',operation,*args",
                      "'shell','pm',operation,*args")

    def test_failure_phase_required(self):
        self.mutation(C.HOST,"print('OX_RT02F_P02_ANDROID_PHASE='+phase,flush=True)",
                      "print('DIAGNOSTICS_SILENCED='+phase,flush=True)")

    def test_contract_refuses_missing_emulator_script(self):
        self.mutation(C.WORKFLOW,'python3 -B scripts/ci/r02f_p02_session_abandon.py run --out',
                      'echo P02_SILENTLY_SKIPPED')

    def test_refuse_missing_independent_verify(self):
        self.mutation(C.WORKFLOW,'python3 -B scripts/ci/r02f_p02_session_abandon.py verify --out',
                      'echo P02_NOT_VERIFIED')

    def test_refuse_second_emulator(self):
        self.mutation(C.WORKFLOW,'script: bash -c',
                      'uses: ReactiveCircus/android-emulator-runner@a421e43855164a8197daf9d8d40fe71c6996bb0d\n          script: bash -c')

    def test_refuse_unbounded_session_bytes(self):
        self.mutation(C.HOST,'0<total<16*1024*1024','total>=0')

    def test_refuse_disabling_installed_byte_comparison(self):
        self.mutation(C.HOST,'after==before','True')

    def test_refuse_forged_cancelled_receipt(self):
        self.mutation(C.HOST,"'install_commit_called':False", "'install_commit_called':True")

    def test_refuse_missing_cleanup(self):
        self.mutation(C.HOST,'if session is not None and not abandoned:',
                      'if False:')

    def test_fresh_baseline_install_cannot_be_skipped(self):
        self.mutation(C.HOST,"'install','-t',str(v1),timeout=90",
                      "'install','-t',str(fixtures/'fake.apk'),timeout=90")

    def test_cleanup_cannot_be_skipped(self):
        self.mutation(C.HOST,"'shell','pm','uninstall',base.FIXTURE,timeout=60",
                      "'shell','echo','skip-uninstall',timeout=60")

    def test_installed_state_proof_cannot_be_removed(self):
        self.mutation(C.HOST,
                      '        before=rt02c.baseline_v1(fixtures)\n        results=[]',
                      "        before={'installed_original_intact':True}\n        results=[]")

    def test_adb_stdout_must_not_replace_installed_state(self):
        self.mutation(C.HOST,
                      "adb_phase('STAGE_FRESH_V1_BASELINE','install','-t',str(v1),timeout=90)",
                      "install=adb_phase('STAGE_FRESH_V1_BASELINE','install','-t',str(v1),timeout=90)\n        need(install.splitlines()[-1]=='Success','stdout')")


    def test_refuse_missing_clean_rt02c_handoff(self):
        self.mutation(C.HOST,'base.empty_or_expected_package()', 'True')

    def test_refuse_unbound_v1_signer(self):
        self.mutation(C.HOST,"inv.get('signed_with_ephemeral_ci_key') is True",
                      "inv.get('signed_with_ephemeral_ci_key') is False")

    def test_refuse_skipped_p02_retrigger(self):
        self.mutation(C.WORKFLOW,"      - 'scripts/ci/r02f_p02_*'",
                      "      - 'docs/**'")

    def test_refuse_missing_preceding_rt02c(self):
        self.mutation(C.WORKFLOW,'python3 -B scripts/ci/r02_rt02c_hosted.py run --out',
                      'echo SKIP_7_REAL_CASES')

    def test_refuse_wrong_source_gate(self):
        self.mutation(C.SOURCE,'python3 -B scripts/ci/r02f_p02_contract.py --check',
                      'echo P02_NOT_CHECKED')

if __name__=='__main__':unittest.main()
