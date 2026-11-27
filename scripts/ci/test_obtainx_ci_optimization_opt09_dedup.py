"""Actual source policy and full release-admission code, controlled API fixtures.
No synthetic fixture constitutes hosted evidence or signing authorization.
"""
from __future__ import annotations
import copy
import unittest
from pathlib import Path
from unittest.mock import patch
import obtainx_ci_policy as policy
import r12_release_gate as gate
import r07_workflow_contract as workflows

HEAD = 'a' * 40
TREE = 'b' * 40
PR_HEAD = 'c' * 40
FIRST = 'd' * 40
REPO = {'id': policy.REPO_ID}
BRANCH = 'feature/final-audit-04'
IDENT = {'source_sha': HEAD, 'source_tree': TREE}


class Fixture:
    def __init__(self, reuse=False):
        self.calls = []
        self.ref = {'ref': 'refs/heads/main', 'object': {'type': 'commit', 'sha': HEAD}}
        self.commit = {'sha': HEAD, 'tree': {'sha': TREE}, 'verification': {'verified': True},
                       'parents': [{'sha': FIRST}, {'sha': PR_HEAD}]}
        self.original = {'sha': PR_HEAD, 'tree': {'sha': TREE}}
        self.pr = {'number': 34, 'state': 'closed', 'merged_at': '2026-11-27T18:50:32Z',
                   'merge_commit_sha': HEAD, 'head': {'sha': PR_HEAD, 'repo': REPO, 'ref': BRANCH},
                   'base': {'ref': 'main', 'repo': REPO}, 'labels': []}
        self.prs = [self.pr]
        self.env = {'name': 'obtainx-release-candidate', 'can_admins_bypass': False,
                    'protection_rules': [{'type': 'required_reviewers', 'prevent_self_review': True,
                                          'reviewers': [{'type': 'User', 'reviewer': {'id': 2}}]}],
                    'deployment_branch_policy': {'protected_branches': True, 'custom_branch_policies': False}}
        self.policies = {'total_count': 1, 'branch_policies': [{'name': 'main', 'type': 'branch'}]}
        self.lists = {}
        self.runs = {}
        self.jobs = {}
        for i, (lane, (workflow, job, steps)) in enumerate(policy.FULL_PROOFS.items(), 1):
            for source, branch, event, offset in [(HEAD, 'main', 'push' if lane == 'source' else 'workflow_dispatch', 0),
                                                   (PR_HEAD, BRANCH, 'pull_request', 100)]:
                rid = i + offset
                row = {'id': rid, 'workflow_id': workflow, 'head_sha': source, 'head_branch': branch,
                       'event': event, 'status': 'completed', 'conclusion': 'success', 'repository': REPO,
                       'head_repository': REPO, 'run_attempt': 1}
                self.runs[rid] = copy.deepcopy(row)
                j = {'id': rid + 1000, 'name': job, 'head_sha': source, 'status': 'completed',
                     'conclusion': 'success', 'run_id': rid, 'run_attempt': 1,
                     'steps': [{'name': s, 'status': 'completed', 'conclusion': 'success'} for s in steps]}
                self.jobs[rid] = {'total_count': 1, 'jobs': [j]}
                rows = [] if reuse and source == HEAD and lane != 'source' else [row]
                self.lists[(workflow, source)] = {'total_count': len(rows), 'workflow_runs': rows}

    def api(self, path):
        self.calls.append(path)
        if path == '/git/ref/heads/main': return copy.deepcopy(self.ref)
        if path == '/git/commits/' + HEAD: return copy.deepcopy(self.commit)
        if path == '/git/commits/' + PR_HEAD: return copy.deepcopy(self.original)
        if path == '/commits/' + HEAD + '/pulls?per_page=50': return copy.deepcopy(self.prs)
        if path == '/environments/obtainx-release-candidate': return copy.deepcopy(self.env)
        if path.endswith('/deployment-branch-policies?per_page=100'): return copy.deepcopy(self.policies)
        if '/workflows/' in path:
            workflow = int(path.split('/')[3]); source = path.split('head_sha=')[1].split('&')[0]
            return copy.deepcopy(self.lists[(workflow, source)])
        if '/attempts/' in path: return copy.deepcopy(self.jobs[int(path.split('/')[3])])
        if path.startswith('/actions/runs/'): return copy.deepcopy(self.runs[int(path.split('/')[3])])
        raise AssertionError(path)

    def mutate(self, name):
        if name == 'failed':
            rows = self.lists[(policy.FULL_PROOFS['flutter'][0], HEAD)]
            bad = dict(rows['workflow_runs'][0], id=999, conclusion='failure')
            rows['workflow_runs'].append(bad); rows['total_count'] = 2
        elif name == 'stale':
            self.ref['object']['sha'] = FIRST
        elif name == 'skipped':
            self.jobs[2]['jobs'][0]['steps'][0]['conclusion'] = 'skipped'
        else: raise AssertionError(name)


class Dedup(unittest.TestCase):
    def test_normal_draft_same_full_plan_as_ready(self):
        with patch.object(policy, 'git', return_value=HEAD), patch.object(policy, 'discover_baseline', side_effect=AssertionError('ordinary delivery must not query a scoped baseline')):
            draft = policy.plan(HEAD, 'pull_request', {'pull_request': {'draft': True, 'labels': []}})
            ready = policy.plan(HEAD, 'pull_request', {'pull_request': {'draft': False, 'labels': []}})
        self.assertEqual(draft, ready)
        self.assertTrue(draft['full_acceptance_possible'] and all(draft['lanes'].values()))
        for draft in (True, False):
            self.assertEqual(policy.requested_mode('pull_request', {'pull_request': {'draft': draft, 'labels': [{'name':'ci:development-only'}]}}), 'scoped')

    def test_all_six_never_trigger_on_ready_or_draft(self):
        for path in workflows.WORKFLOWS:
            text = (policy.ROOT / '.github/workflows' / path).read_text()
            doc = workflows.parse_workflow(text, path)
            self.assertEqual(set(doc['on']['pull_request']['types']), {'opened', 'reopened', 'synchronize', 'labeled', 'unlabeled'})
            self.assertIn('workflow_dispatch', doc['on'])
            for extra in ('ready_for_review', 'converted_to_draft'):
                with self.subTest(path=path, extra=extra), self.assertRaises(workflows.ContractError):
                    workflows.parse_workflow(text.replace('labeled, unlabeled]', 'labeled, unlabeled, '+extra+']'), path)
        self.assertEqual(workflows.verify(), 6)

    def test_exact_main_does_not_require_merge_lookup(self):
        f = Fixture(); receipt = gate.hosted_ci(HEAD, TREE, f.api)
        self.assertEqual(gate.validate_ci_receipt(receipt, IDENT), gate.CI_EXACT)
        self.assertNotIn('merge_origin', receipt)
        self.assertFalse(any('/pulls?' in x for x in f.calls))
        self.assertTrue(all(p['source_sha'] == HEAD for p in receipt['proofs'].values()))

    def test_exact_tree_reuse_five_real_lanes_plus_fresh_main_source(self):
        f = Fixture(reuse=True); receipt = gate.hosted_ci(HEAD, TREE, f.api)
        self.assertEqual(gate.validate_ci_receipt(receipt, IDENT), gate.CI_REUSED)
        self.assertEqual(receipt['proofs']['source']['source_sha'], HEAD)
        self.assertEqual(receipt['merge_origin']['source_sha'], PR_HEAD)
        self.assertEqual(receipt['merged_pr_source_proof']['source_sha'], PR_HEAD)
        self.assertEqual(sum(p['evidence_mode']=='REUSED_EXACT_MERGED_TREE' for p in receipt['proofs'].values()), 5)
        self.assertEqual(receipt, gate.hosted_ci(HEAD, TREE, f.api))

    def test_merge_refusals(self):
        for mutation in ('changed-tree', 'not-verified', 'squash', 'ambiguous-pr', 'open-pr', 'wrong-repo', 'wrong-base', 'dev-only', 'missing-pr-source', 'wrong-pr-head', 'failed-main', 'pending-pr', 'failed-pr', 'skipped-pr', 'wrong-attempt', 'wrong-job-run', 'partial-page'):
            f = Fixture(reuse=True)
            if mutation == 'changed-tree': f.original['tree']['sha'] = FIRST
            if mutation == 'not-verified': f.commit['verification']['verified'] = False
            if mutation == 'squash': f.commit['parents'].pop()
            if mutation == 'ambiguous-pr': f.prs.append(dict(f.pr, number=35))
            if mutation == 'open-pr': f.pr['state']='open'
            if mutation == 'wrong-repo': f.pr['head']['repo']={'id':2}
            if mutation == 'wrong-base': f.pr['base']['ref']='other'
            if mutation == 'dev-only': f.pr['labels']=[{'name':'ci:development-only'}]
            if mutation == 'missing-pr-source': f.lists[(policy.FULL_PROOFS['source'][0], PR_HEAD)]={'total_count':0,'workflow_runs':[]}
            if mutation == 'wrong-pr-head': f.pr['head']['sha']=FIRST
            if mutation == 'failed-main': f.lists[(policy.FULL_PROOFS['flutter'][0], HEAD)]={'total_count':1,'workflow_runs':[dict(f.runs[2],conclusion='failure')]}
            if mutation in ('pending-pr','failed-pr'):
                r=f.lists[(policy.FULL_PROOFS['flutter'][0], PR_HEAD)]['workflow_runs'][0]
                r.update(status='in_progress' if mutation=='pending-pr' else 'completed',conclusion=None if mutation=='pending-pr' else 'failure')
            if mutation == 'skipped-pr': f.jobs[102]['jobs'][0]['steps'][0]['conclusion']='skipped'
            if mutation == 'wrong-attempt': f.runs[102]['run_attempt']=2
            if mutation == 'wrong-job-run': f.jobs[102]['jobs'][0]['run_id']=999
            if mutation == 'partial-page': f.lists[(policy.FULL_PROOFS['flutter'][0],PR_HEAD)]['total_count']=51
            with self.subTest(mutation=mutation), self.assertRaises(gate.Refused):
                gate.hosted_ci(HEAD,TREE,f.api)

    def test_newer_matching_failure_never_reuses_older_success(self):
        f = Fixture(reuse=True)
        rows = f.lists[(policy.FULL_PROOFS['rt02b'][0], PR_HEAD)]
        rows['workflow_runs'].append(dict(rows['workflow_runs'][0], id=999, conclusion='cancelled'))
        rows['total_count']=2
        with self.assertRaises(gate.Refused): gate.hosted_ci(HEAD,TREE,f.api)

    def test_tampered_receipts_refused(self):
        receipt=gate.hosted_ci(HEAD,TREE,Fixture(reuse=True).api)
        for mutation in ('tree','source-mode','proof-source','missing-lane','missing-pr-proof','wrong-mode'):
            bad=copy.deepcopy(receipt)
            if mutation=='tree':bad['source_tree']=FIRST
            if mutation=='source-mode':bad['proofs']['source']['evidence_mode']='REUSED_EXACT_MERGED_TREE'
            if mutation=='proof-source':bad['proofs']['rt02']['source_sha']=HEAD
            if mutation=='missing-lane':bad['proofs'].pop('rt02c')
            if mutation=='missing-pr-proof':bad.pop('merged_pr_source_proof')
            if mutation=='wrong-mode':bad['mode']=gate.CI_EXACT
            with self.subTest(mutation=mutation),self.assertRaises(gate.Refused):gate.validate_ci_receipt(bad,IDENT)

    def test_environment_must_have_real_review_no_bypass_and_protected_main(self):
        f=Fixture();self.assertTrue(gate.verify_signing_environment(f.api))
        f.env['deployment_branch_policy']={'protected_branches':False,'custom_branch_policies':True}
        self.assertTrue(gate.verify_signing_environment(f.api))
        f.policies['branch_policies'][0]['name']='*'
        with self.assertRaises(gate.Refused):gate.verify_signing_environment(f.api)
        for mutation in ('bypass','missing-bypass','self-review','no-reviewers','unprotected','wrong-name'):
            f=Fixture()
            if mutation=='bypass':f.env['can_admins_bypass']=True
            if mutation=='missing-bypass':f.env.pop('can_admins_bypass')
            if mutation=='self-review':f.env['protection_rules'][0]['prevent_self_review']=False
            if mutation=='no-reviewers':f.env['protection_rules'][0]['reviewers']=[]
            if mutation=='unprotected':f.env['deployment_branch_policy']=None
            if mutation=='wrong-name':f.env['name']='other'
            with self.subTest(mutation=mutation),self.assertRaises(gate.Refused):gate.verify_signing_environment(f.api)

if __name__ == '__main__':
    unittest.main()
