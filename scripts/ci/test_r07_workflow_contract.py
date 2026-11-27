"""Targeted workflow-structure regressions; no CI or Gradle invoked."""
import unittest
from pathlib import Path
from r07_workflow_contract import parse_workflow, ContractError, WORKFLOWS, REQUIRED_STEPS, verify, SOURCE_EXPR, SOURCE_GUARD

NAME='obtainx-r00-contracts.yml'
def fixture(name=NAME):
    text='name: '+WORKFLOWS[name][1]+'\non:\n  pull_request:\n    types: [opened, reopened, synchronize, labeled, unlabeled, ready_for_review, converted_to_draft]\n'
    text+='jobs:\n  job:\n    runs-on: ubuntu-24.04\n    steps:\n      - uses: actions/checkout@v4\n'
    for label, run in REQUIRED_STEPS.get(name,{}).items():
        text+=f'      - name: {label}\n        run: {run}\n'
    return text

class WorkflowStructureTest(unittest.TestCase):
    def test_all_six_workflow_shapes(self):
        for name in WORKFLOWS:
            with self.subTest(name=name):
                self.assertIn('pull_request',parse_workflow(fixture(name),name)['on'])
    def test_original_indentation_defect(self):
        good=fixture()
        bad=good.replace('        run: python3 -B scripts/ci/r06_contract.py --check\n      - name: R07 Activity Center source and negative contracts\n        run: python3 -B scripts/ci/r07_contract.py --check', '      - name: R07 Activity Center source and negative contracts\n      run: python3 -B scripts/ci/r07_contract.py --check\n      run: python3 -B scripts/ci/r06_contract.py --check')
        self.assertNotEqual(good,bad)
        with self.assertRaises(ContractError): parse_workflow(bad,NAME)
    def test_duplicate_run(self):
        bad=fixture().replace('        run: python3 -B scripts/ci/r06_contract.py --check','        run: echo bypass\n        run: python3 -B scripts/ci/r06_contract.py --check')
        with self.assertRaises(ContractError): parse_workflow(bad,NAME)
    def test_duplicate_on(self):
        with self.assertRaises(ContractError): parse_workflow(fixture()+'on: {}\n',NAME)
    def test_displaced_command(self):
        bad=fixture().replace('        run: python3 -B scripts/ci/r06_contract.py --check','        run: echo unrelated')
        with self.assertRaises(ContractError): parse_workflow(bad,NAME)
    def test_conditional_required_gate(self):
        bad=fixture().replace('        run: python3 -B scripts/ci/r07_contract.py --check','        if: false\n        run: python3 -B scripts/ci/r07_contract.py --check')
        with self.assertRaises(ContractError): parse_workflow(bad,NAME)
    def test_missing_synchronize(self):
        with self.assertRaises(ContractError): parse_workflow(fixture().replace(', synchronize',''),NAME)
    def test_missing_runtime_risk_path(self):
        name='obtainx-r02-api36.yml'
        with self.assertRaises(ContractError): parse_workflow(fixture(name).replace("  pull_request:\n", "  pull_request:\n    paths: [docs/**]\n"),name)
    def test_unconditional_job_step_shape(self):
        with self.assertRaises(ContractError): parse_workflow(fixture().replace('      - uses: actions/checkout@v4','      - name: orphan step'),NAME)
    def test_gate_error_is_not_a_pass(self):
        bad=fixture().replace('        run: python3 -B scripts/ci/r07_workflow_contract.py --check','        continue-on-error: true\n        run: python3 -B scripts/ci/r07_workflow_contract.py --check')
        with self.assertRaises(ContractError): parse_workflow(bad,NAME)
class ExactSourceBindingTest(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[2]

    def test_all_six_exact_workflow_jobs(self):
        self.assertEqual(verify(self.ROOT), 6)

    def mutation(self, name, old, new):
        rel = '.github/workflows/' + name
        text = (self.ROOT / rel).read_text()
        self.assertIn(old, text)
        with self.assertRaises(ContractError):
            verify(self.ROOT, overrides={rel: text.replace(old, new, 1)})

    def test_synthetic_merge_checkout_refused(self):
        self.mutation('obtainx-r02-rt02c.yml', 'ref: ' + SOURCE_EXPR,
                      'ref: ${{ github.sha }}')

    def test_missing_expected_source_refused(self):
        self.mutation(NAME, 'OX_EXPECTED_SHA: ' + SOURCE_EXPR,
                      'OX_EXPECTED_SHA: ${{ github.sha }}')

    def test_commented_source_guard_refused(self):
        self.mutation('obtainx-r02-rt02c.yml', SOURCE_GUARD,
                      '# ' + SOURCE_GUARD)

    def test_unpinned_full_flutter_checkout_refused(self):
        name = 'obtainx-r00-flutter.yml'
        rel = '.github/workflows/' + name
        text = (self.ROOT / rel).read_text()
        prefix, sep, job = text.partition('  flutter-and-android-debug:')
        self.assertTrue(sep)
        with self.assertRaises(ContractError):
            verify(self.ROOT, overrides={rel: prefix + sep + job.replace(
                'ref: ' + SOURCE_EXPR, 'ref: ${{ github.sha }}', 1)})

    def test_synthetic_artifact_identity_refused(self):
        self.mutation('obtainx-r02-rt02c.yml',
                      'name: obtainx-r02-rt02c-archive-' + SOURCE_EXPR,
                      'name: obtainx-r02-rt02c-archive-${{ github.sha }}')

    def test_static_artifact_identity_refused(self):
        self.mutation('obtainx-r02-rt02c.yml',
                      'name: obtainx-r02-rt02c-archive-' + SOURCE_EXPR,
                      'name: obtainx-r02-rt02c-archive')

    def test_job_level_override_refused(self):
        self.mutation('obtainx-r02-rt02c.yml', '      GRADLE_OPTS:',
                      '      OX_EXPECTED_SHA: ${{ github.sha }}\n      GRADLE_OPTS:')

if __name__=='__main__': unittest.main()
