"""CI6 mutation tests: no path-trigger gaps or false qualification allowed."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT/'scripts/ci/obtainx_ci6_contract.py'
SPEC = importlib.util.spec_from_file_location('obtainx_ci6_src',CONTRACT)
assert SPEC and SPEC.loader
C=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)

class CI6NegativeMutations(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ox-ci6-contract-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for rel in [C.POLICY,C.SCOPE,C.CONTRACTS,*[x[1] for x in C.REQUIRED]]:
            target=self.root/rel
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/rel,target)

    def mutate(self,name,old,new):
        p=self.root/name
        original=p.read_text()
        self.assertIn(old,original,name)
        p.write_text(original.replace(old,new,1))
        errors=C.inspect(self.root)
        self.assertTrue(errors,'mutation escaped: '+name+' '+old)
        p.write_text(original)
        self.assertEqual(C.inspect(self.root),[])

    def test_00_clean(self):
        self.assertEqual(C.inspect(self.root),[])

    def test_01_exact_six_names_from_policy(self):
        p=json.loads((self.root/C.POLICY).read_text())
        self.assertEqual(len(p['workflows']),6)
        self.assertEqual([(x['name'],x['path']) for x in p['workflows']],list(C.REQUIRED))
        self.mutate(C.POLICY,'"require_all_exact_head_success": true',
                    '"require_all_exact_head_success": false')

    def test_02_missing_not_qualified(self):
        self.mutate(C.POLICY,'"missing_is_not_qualified": true',
                    '"missing_is_not_qualified": false')

    def test_03_false_release_claim(self):
        self.mutate(C.POLICY,'"release_qualified": false',
                    '"release_qualified": true')

    def test_04_android_pr_filter_drop_each(self):
        for path,lane in zip(C.ANDROID,('api36','rt02','rt02b','rt02c')):
            self.mutate(path,"    if: needs.scope.outputs."+lane+" == 'true'", "    if: false")
            self.mutate(path,'  pull_request:\n','  pull_request:\n    paths: [docs/**]\n')

    def test_05_no_manual_trigger_each(self):
        for _,path in C.REQUIRED:
            self.mutate(path,'  workflow_dispatch:', '  not_a_trigger:')

    def test_06_names_must_match_exact_manifest(self):
        for name,path in C.REQUIRED:
            self.mutate(path,'name: '+name,'name: unqualified artifact')

    def test_07_scope_router_never_treats_p04b_as_source_only(self):
        self.mutate(C.SCOPE,"    'scripts/ci/r02f_p04b_*',",
                    "    'scripts/ci/r02f_unused_*',")
        spec=importlib.util.spec_from_file_location('ox_ci6_router',ROOT/C.SCOPE)
        assert spec and spec.loader
        policy=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(policy)
        for path in ('scripts/ci/r02f_p04b_p02_target.py',
                     'scripts/ci/r02f_p04b_p02_hosted.py',
                     'scripts/ci/r02f_p04b_p03_negative.py',
                     'scripts/ci/r02f_p02_contract.py',
                     'scripts/ci/r02g_incompatible_sdk_hosted.py'):
            outcome=policy.classify([path])
            self.assertTrue(outcome['full_flutter'],path)
            self.assertEqual(outcome['reason'],'high-risk')

    def test_08_source_integrity_gate_cannot_disappear(self):
        self.mutate(C.CONTRACTS,'python3 -B scripts/ci/obtainx_ci6_contract.py --check',
                    'echo CI6 gate disabled')

    def test_09_policy_symlink_refused(self):
        p=self.root/C.POLICY
        backup=p.with_name('policy_data.json')
        p.rename(backup)
        p.symlink_to(backup.name)
        self.assertTrue(C.inspect(self.root))

if __name__=='__main__': unittest.main()
