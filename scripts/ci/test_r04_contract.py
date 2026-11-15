#!/usr/bin/env python3
"""Fail-closed R04 mutation tests: remove one safety gate and require refusal."""
from __future__ import annotations
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('r04_contract',ROOT/'scripts/ci/r04_contract.py')
MODULE=importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
PATHS=[
 'lib/services/r04_github_actions.dart',
 'lib/app_sources/github.dart',
 'test/r04_github_actions_test.dart',
 '.github/workflows/obtainx-r00-flutter.yml',
 '.github/workflows/obtainx-r00-contracts.yml',
 'scripts/ci/obtainx_ci_policy.py',
 'docs/R04_ACTIONS_CHANNEL.md',
 '.github/workflows/obtainx-r02-api36.yml',
 '.github/workflows/obtainx-r02-rt02.yml',
 '.github/workflows/obtainx-r02-rt02b.yml',
 '.github/workflows/obtainx-r02-rt02c.yml',
]

class R04MutationContract(unittest.TestCase):
    def _mutation(self,path,before,after):
        with tempfile.TemporaryDirectory(prefix='ox-r04-mut-') as temp:
            root=Path(temp)
            for rel in PATHS:
                target=root/rel
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes((ROOT/rel).read_bytes())
            file=root/path
            source=file.read_text()
            self.assertEqual(source.count(before),1,before)
            file.write_text(source.replace(before,after,1))
            self.assertNotEqual(MODULE.verify(root),0)

    def test_remove_strong_origin(self):
        self._mutation(PATHS[0],"repoApi.host != 'api.github.com'",'false')
    def test_remove_success_only(self):
        self._mutation(PATHS[0],"r['conclusion'] == 'success'",'true')
    def test_remove_run_attempt(self):
        self._mutation(PATHS[0],"_positiveInt(r['run_attempt'])",'1')
    def test_reintroduce_manual_run_id_shadowing(self):
        self._mutation(PATHS[0],
            "final selectedRunId = _positiveInt(selected['id'])!;",
            "final runId = _positiveInt(selected['id'])!;")
    def test_remove_branch_guard(self):
        self._mutation(PATHS[0],"r['head_branch'] == chosenBranch",'true')
    def test_remove_expiry_check(self):
        self._mutation(PATHS[0],"!expires.isAfter(current)",'false')
    def test_remove_oversize_check(self):
        self._mutation(PATHS[0],'size > maxArchiveBytes','false')
    def test_remove_ambiguous_artifact_refusal(self):
        self._mutation(PATHS[0],"if (matches.length > 1)","if (false)")
    def test_remove_pagination_fail_closed(self):
        self._mutation(PATHS[0],"page == maximumPages",'false')
    def test_remove_actions_source_route(self):
        self._mutation(PATHS[1],"return await _fetchR04ActionsDetails(","return await _disabledR04ActionsDetails(")
    def test_remove_exact_sha_enforcement(self):
        self._mutation(PATHS[0],"_sha(r['head_sha'])", "null")
    def test_remove_dart_mock_http(self):
        self._mutation(PATHS[3],
          'flutter test --no-pub test/r04_github_actions_test.dart',
          'echo R04 skipped')
    def test_remove_r04_source_contract_ci(self):
        self._mutation(PATHS[4],
          'python3 -B scripts/ci/r04_contract.py --check','echo skip')
    def test_remove_android_workflow_r04_gate(self):
        self._mutation(PATHS[10], "- 'test/r04_*'", "- 'docs/r04_*'")
    def test_remove_r04_risk_glob(self):
        self._mutation(PATHS[5],"'lib/services/r04_*'", "'docs/r04_*'")

if __name__=='__main__':unittest.main(verbosity=2)
