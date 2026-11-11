"""Mutation tests for fail-closed ObtainX CI optimization routing."""
from __future__ import annotations
from pathlib import Path
import importlib.util
import tempfile
import unittest
from shutil import copyfile

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('obtainx_ci_optimization_contract',
    ROOT/'scripts/ci/obtainx_ci_optimization_contract.py')
assert SPEC and SPEC.loader
M=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)

class CIOptimizationSafety(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ox-ci-opt01-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for rel in (*M.FILES, M.POLICY):
            dest=self.root/rel
            dest.parent.mkdir(parents=True,exist_ok=True)
            copyfile(ROOT/rel,dest)

    def mutation(self,rel,old,new):
        p=self.root/rel
        s=p.read_text(encoding='utf8')
        self.assertIn(old,s,rel+' stale mutation anchor')
        p.write_text(s.replace(old,new,1),encoding='utf8')
        self.assertTrue(M.inspect(self.root),'dangerous optimization mutation escaped '+rel)

    def test_exact_optimization_contract_accepts(self):
        self.assertEqual(M.inspect(self.root),[])

    def test_cannot_defer_without_explicit_label(self):
        self.mutation(M.HEAVY[0],M.DEFER_EXPR,'true')

    def test_cannot_bypass_full_after_label_removal(self):
        self.mutation(M.HEAVY[1],M.DEFER_EXPR,"github.event_name == 'workflow_dispatch'")

    def test_manual_dispatch_always_available(self):
        self.mutation(M.HEAVY[2],'  workflow_dispatch:','  # disabled manual gate')

    def test_label_removal_retriggers(self):
        self.mutation(M.HEAVY[3],M.EVENT_TYPES,
                      'types: [opened, reopened, synchronize, labeled]')

    def test_source_guard_must_fail_closed(self):
        self.mutation(M.SOURCE,'OX_CI_DEVELOPMENT_ONLY_NOT_QUALIFIED',
                      'OX_CI_DEVELOPMENT_SUCCESS')

    def test_source_contracts_cannot_be_skipped(self):
        self.mutation(M.SOURCE,"python3 -m unittest discover -s scripts/ci -p 'test_*.py' -v",'echo skip')

    def test_guard_must_share_source_runner(self):
        self.mutation(M.SOURCE,'Development-only cannot qualify (same runner)',
                      'Development-only guard moved outside source runner')

    def test_guard_must_stay_red(self):
        self.mutation(M.SOURCE,'          exit 1\n','          exit 0\n')

    def test_guard_requires_label(self):
        self.mutation(M.SOURCE,
            '        if: ${{ '+M.REFUSE_EXPR+' }}',
            '        if: ${{ false }}')


    def test_api36_cache_mandatory(self):
        self.mutation(M.HEAVY[0],'          cache: gradle\n',
                      '          cache: none\n')

    def test_rt02_cache_wrapper_dependency_mandatory(self):
        self.mutation(M.HEAVY[1],
                      '            android/gradle/wrapper/gradle-wrapper.properties',
                      '            arbitrary/untrusted.gradle')

    def test_rt02b_cache_jdk_pin_mandatory(self):
        self.mutation(M.HEAVY[2],
                      'actions/setup-java@cf277c60eb25467037889841efdb72551f06f6c3',
                      'actions/setup-java@main')

    def test_rt02c_existing_gradle_cache_mandatory(self):
        self.mutation(M.HEAVY[3],
                      '            android/**/*.gradle*',
                      '            some/irrelevant/path')

    def test_cache_must_be_inside_java_step(self):
        self.mutation(M.HEAVY[0],
                      '      - name: Set up Java 21',
                      '      - name: Cache moved outside Java setup')

    def test_artifact_upload_timeout_bounded(self):
        self.mutation(M.HEAVY[0],'timeout-minutes: 3\n        uses: '+M.UPLOAD,
                      'timeout-minutes: 120\n        uses: '+M.UPLOAD)

    def test_upload_not_silently_ignored(self):
        self.mutation(M.HEAVY[1],M.UPLOAD,'echo artifact skipped')

    def test_emulator_required_when_qualifying(self):
        self.mutation(M.HEAVY[2],M.EMULATOR,'echo fake-emulator')

    def test_full_flutter_mandatory_when_qualifying(self):
        self.mutation(M.FLUTTER,
          "needs.scope.outputs.full_flutter == 'true' && !contains(github.event.pull_request.labels.*.name, 'ci:development-only')",
          "needs.scope.outputs.full_flutter == 'false'")

    def test_summary_does_not_count_as_artifact(self):
        self.mutation(M.HEAVY[3],M.UPLOAD,'echo pretend-upload')

    def test_opt_python_risk_cannot_be_bypassed(self):
        self.mutation(M.POLICY,"'"+M.RISK+"'","'docs/*.md'")

    def test_opt_python_change_retriggers_android(self):
        self.mutation(M.HEAVY[0],"      - '"+M.RISK+"'","      - 'docs/**'")

if __name__ == '__main__':
    unittest.main()
