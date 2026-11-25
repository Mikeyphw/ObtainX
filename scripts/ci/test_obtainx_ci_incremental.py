"""OPT07 scope, exact prior evidence, fail-closed and production route tests."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import obtainx_ci_policy as p
import r07_workflow_contract as workflows

H='a'*40; B='b'*40

class Impact(unittest.TestCase):
    def test_ui_only(self):
        v=p.impact(['lib/pages/apps.dart'],H,B)
        self.assertEqual(v['mode'],'scoped');self.assertTrue(v['targeted_flutter'])
        self.assertFalse(v['full_flutter']);self.assertFalse(any(v['lanes'].values()));self.assertIn('test/r09_discovery_test.dart',v['tests']);self.assertFalse(v['full_acceptance_possible'])
    def test_docs(self):
        v=p.impact(['docs/ROADMAP.md'],H,B);self.assertFalse(v['targeted_flutter']);self.assertFalse(any(v['lanes'].values()))
    def test_archive_source(self):
        v=p.impact(['lib/services/r04_actions_archive_integrity.dart'],H,B);self.assertTrue(v['lanes']['rt02c']);self.assertFalse(v['lanes']['rt02b']);self.assertIn('test/r04_archive_integrity_test.dart',v['tests'])
    def test_shared_installer(self):
        v=p.impact(['lib/providers/apps_provider_install.dart'],H,B);self.assertTrue(all(v['lanes'].values()));self.assertTrue(v['targeted_flutter'])
    def test_unknown_full(self):
        for path in ('android/app/build.gradle','pubspec.lock','lib/providers/source_provider.dart','.github/workflows/unknown.yml'):
            v=p.impact([path],H,B);self.assertTrue(v['full_flutter']);self.assertTrue(all(v['lanes'].values()));self.assertFalse(v['full_acceptance_possible'])
    def test_test_only(self):
        v=p.impact(['test/r09_discovery_test.dart'],H,B);self.assertEqual(v['tests'],['test/r09_discovery_test.dart'])
    def test_union_without_duplicates(self):
        v=p.impact(['lib/pages/apps.dart','lib/components/bulk_update_sheet.dart','test/r09_discovery_test.dart'],H,B);self.assertEqual(len(v['tests']),len(set(v['tests'])))
    def test_missing_mapped_test_falls_back(self):
        with tempfile.TemporaryDirectory() as d:
            v=p.impact(['lib/pages/apps.dart'],H,B,Path(d));self.assertTrue(v['full_flutter']);self.assertTrue(all(v['lanes'].values()))
    def test_invalid_path_refused(self):
        with self.assertRaises(ValueError):p.impact(['../secret'],H,B)
    def test_modes(self):
        for draft,labels,expected in [(True,[],'scoped'),(False,[],'full'),(True,['ci:full-qualification'],'full'),(False,['ci:development-only'],'scoped'),(True,['ci:development-only','ci:full-qualification'],'scoped')]:
            self.assertEqual(p.requested_mode('pull_request',{'pull_request':{'draft':draft,'labels':[{'name':x} for x in labels]}}),expected)
        self.assertEqual(p.requested_mode('workflow_dispatch',{}),'full')
    def test_one_invocation_targeted_tests(self):
        value=p.impact(['lib/pages/apps.dart'],H,B)
        with patch.object(p.subprocess,'run') as run:
            p.run_targeted(value,H)
            self.assertEqual(run.call_count,2);self.assertEqual(run.call_args_list[0].args[0],['flutter','analyze','lib','test','integration_test']);self.assertEqual(set(run.call_args_list[1].args[0][3:]),set(value['tests']))
    def test_stale_plan_refused(self):
        v=p.impact(['lib/pages/apps.dart'],H,B)
        with patch.object(p.subprocess,'run') as run,self.assertRaises(ValueError):p.run_targeted(v,B)
        run.assert_not_called()

class Baseline(unittest.TestCase):
    def setUp(self):
        self.pin={'schema':1,'repository':p.REPO,'source_sha':B,'runs':{lane:i for i,lane in enumerate(p.FULL_PROOFS,1)}}
        self.rows={};self.jobs={}
        for lane,(wf,job,steps) in p.FULL_PROOFS.items():
            run=self.pin['runs'][lane];self.rows[run]={'id':run,'workflow_id':wf,'head_sha':B,'event':'pull_request','status':'completed','conclusion':'success','repository':{'id':p.REPO_ID},'head_repository':{'id':p.REPO_ID},'run_attempt':1}
            self.jobs[run]={'total_count':1,'jobs':[{'name':job,'conclusion':'success','steps':[{'name':step,'conclusion':'success'} for step in steps]}]}
    def api(self,path):
        run=int(path.split('/')[3]);return self.jobs[run] if '/jobs?' in path else self.rows[run]
    def test_full_baseline_verified(self):self.assertTrue(p.verify_baseline(self.pin,self.api))
    def test_green_scope_not_full(self):
        self.jobs[2]['jobs'][0]['conclusion']='skipped';self.assertFalse(p.verify_baseline(self.pin,self.api))
    def test_skipped_runtime_step(self):
        self.jobs[6]['jobs'][0]['steps'][0]['conclusion']='skipped';self.assertFalse(p.verify_baseline(self.pin,self.api))
    def test_stale_head_refused(self):
        self.rows[1]['head_sha']=H;self.assertFalse(p.verify_baseline(self.pin,self.api))
    def test_wrong_repo_refused(self):
        self.rows[3]['head_repository']['id']=1;self.assertFalse(p.verify_baseline(self.pin,self.api))
    def test_wrong_workflow_refused(self):
        self.rows[6]['workflow_id']=123;self.assertFalse(p.verify_baseline(self.pin,self.api))
    def test_missing_job_page_refused(self):
        self.jobs[6]['total_count']=2;self.assertFalse(p.verify_baseline(self.pin,self.api))
    def test_wrong_event_refused(self):
        self.rows[1]['event']='workflow_dispatch';self.assertFalse(p.verify_baseline(self.pin,self.api))
    def test_failed_run_refused(self):
        self.rows[1]['conclusion']='failure';self.assertFalse(p.verify_baseline(self.pin,self.api))
    def test_discover_exact_new_full_ancestor(self):
        self.pin['source_sha']='c'*40
        def api(path):
            if 'status=success' in path:return {'workflow_runs':[self.rows[1]]}
            if 'workflows/' in path:
                wf=int(path.split('/')[3]);return {'workflow_runs':[r for r in self.rows.values() if r['workflow_id']==wf]}
            return self.api(path)
        with patch.object(p,'git',return_value=H+'\n'+B+'\n'):
            v=p.discover_baseline(H,self.pin,api=api)
        self.assertEqual(v['source_sha'],B);self.assertEqual(v['runs']['rt02c'],6)
    def test_unverified_baseline_fallback_no_full_claim(self):
        with patch.object(p,'git',return_value=H),patch.object(p,'policy_migration',return_value=False),patch.object(p,'discover_baseline',side_effect=ValueError('unverified')):
            v=p.plan(H,'pull_request',{'pull_request':{'draft':True,'head':{'sha':H,'repo':{'id':p.REPO_ID}},'base':{'sha':B,'repo':{'id':p.REPO_ID},'ref':'main'}}})
        self.assertTrue(all(v['lanes'].values()));self.assertEqual(v['mode'],'scoped');self.assertFalse(v['full_acceptance_possible'])
    def test_policy_migration_full_independent_of_api(self):
        with patch.object(p,'git',return_value=H),patch.object(p,'policy_migration',return_value=True),patch.object(p,'discover_baseline',side_effect=AssertionError('must not query')):
            v=p.plan(H,'pull_request',{'pull_request':{'draft':True,'head':{'sha':H,'repo':{'id':p.REPO_ID}},'base':{'sha':B,'repo':{'id':p.REPO_ID},'ref':'main'}}})
        self.assertEqual(v['mode'],'full');self.assertTrue(all(v['lanes'].values()))

class WorkflowMutations(unittest.TestCase):
    def test_all_six(self):self.assertEqual(workflows.verify(),6)
    def test_lane_condition_or_output_mutation_refused(self):
        rel='.github/workflows/obtainx-r02-rt02c.yml';text=(p.ROOT/rel).read_text()
        for old,new in [("needs.scope.outputs.rt02c == 'true'","needs.scope.outputs.rt02c == 'false'"),('${{ steps.scope.outputs.rt02c }}','${{ steps.scope.outputs.api36 }}'),('OX_SCOPE_TOKEN: ${{ github.token }}','OX_SCOPE_TOKEN: null')]:
            self.assertIn(old,text)
            with self.assertRaises(workflows.ContractError):workflows.verify(overrides={rel:text.replace(old,new,1)})
    def test_scope_cannot_green_full(self):
        rel='.github/workflows/obtainx-r00-contracts.yml';text=(p.ROOT/rel).read_text()
        with self.assertRaises(workflows.ContractError):workflows.verify(overrides={rel:text.replace("steps.scope.outputs.mode == 'scoped'","steps.scope.outputs.mode == 'full'")})

if __name__=='__main__':unittest.main()
