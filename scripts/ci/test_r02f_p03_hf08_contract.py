"""HF08 CI sequencing contracts: live Android audit first, offline receipt later."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]

def load_contract():
    spec = importlib.util.spec_from_file_location(
        'r02f_p03_hf08_contract_under_test',
        ROOT/'scripts/ci/r02f_p03_contract.py')
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class P03LiveAuditOrdering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract=load_contract()
        cls.workflow=(ROOT/'.github/workflows/obtainx-r02-rt02c.yml').read_text()
        cls.hosted=(ROOT/'scripts/ci/r02f_p03_hosted.py').read_text()

    def check(self, wf=None, hosted=None):
        self.contract.ensure_live_audit_is_before_shutdown(
            wf if wf is not None else self.workflow,
            hosted if hosted is not None else self.hosted)

    def test_live_runner_and_offline_gate_valid(self):self.check()

    def test_remove_live_audit_refused(self):
        self.assertEqual(self.workflow.count('scripts/ci/r02f_p03_hosted.py audit --out'),1)
        with self.assertRaises(ValueError):
            self.check(self.workflow.replace('scripts/ci/r02f_p03_hosted.py audit --out',
                                             'echo skipped-live-audit --out',1))

    def test_offline_gate_replaced_by_adb_refused(self):
        with self.assertRaises(ValueError):
            self.check(hosted=self.hosted.replace('source, runid = base.identity_check()',
                                                  'source, runid = base.host_check()',1))

    def test_live_device_requery_removed_refused(self):
        self.assertEqual(self.hosted.count("fresh = rt02c.baseline_v1(out/'fixtures')"),1)
        with self.assertRaises(ValueError):
            self.check(hosted=self.hosted.replace("fresh = rt02c.baseline_v1(out/'fixtures')",
                                                  "fresh = obj['baseline_before']",1))

    def test_remove_published_audit_receipt_refused(self):
        needle='            ${{ runner.temp }}/obtainx-rt02c/r02f-p03-android-audit.json\n'
        self.assertEqual(self.workflow.count(needle),1)
        with self.assertRaises(ValueError):self.check(self.workflow.replace(needle,'',1))

    def test_remove_offline_verifier_refused(self):
        needle='python3 -B scripts/ci/r02f_p03_hosted.py verify --out'
        self.assertEqual(self.workflow.count(needle),1)
        with self.assertRaises(ValueError):self.check(self.workflow.replace(needle,'echo no-verify --out',1))

    def test_original_rt02c_p02_r02g_order_and_sha_check_untouched(self):
        runner=self.workflow.split("script: bash -c '",1)[1].split("'\n",1)[0]
        order=['scripts/ci/r02_rt02c_hosted.py run --out',
               'scripts/ci/r02f_p02_session_abandon.py run --out',
               'scripts/ci/r02g_incompatible_sdk_hosted.py run --out',
               'scripts/ci/r02f_p03_hosted.py run --out',
               'scripts/ci/r02f_p03_hosted.py audit --out']
        positions=[runner.index(k) for k in order]
        self.assertEqual(positions,sorted(positions))
        self.assertEqual(self.workflow.count('test "$(git rev-parse HEAD)" = "$GITHUB_SHA"'),1)

if __name__=='__main__':unittest.main()
