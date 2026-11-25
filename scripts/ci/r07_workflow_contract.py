#!/usr/bin/env python3
"""Parse required workflow YAML and enforce the exact R05/R06/R07 steps.

This is a structural precommit gate, not GitHub's execution/CI qualification.
PyYAML is an existing Devtool runtime dependency. Use YAML 1.2-like boolean
resolution for GitHub's `on` key; reject duplicate keys at every depth.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = {
    'obtainx-r00-contracts.yml': (413437262, 'ObtainX R00 / Source and Contract Integrity'),
    'obtainx-r00-flutter.yml': (413437265, 'ObtainX R00 / Hosted Flutter Qualification'),
    'obtainx-r02-api36.yml': (413666807, 'ObtainX R02 / API 36 Hosted Emulator Bootstrap'),
    'obtainx-r02-rt02.yml': (413864665, 'ObtainX R02 / RT02 Real System Installer API36'),
    'obtainx-r02-rt02b.yml': (414136383, 'ObtainX R02 / RT02B Negative Installer API36'),
    'obtainx-r02-rt02c.yml': (414158361, 'ObtainX R02 / RT02C Archive-to-Installer API36'),
}
REQUIRED_STEPS = {
    'obtainx-r00-contracts.yml': {
        'Enforce R06 details, package-evidence and stacked source contracts': 'python3 -B scripts/ci/r06_contract.py --check',
        'R07 Activity Center source and negative contracts': 'python3 -B scripts/ci/r07_contract.py --check',
        'Validate required workflow structure': 'python3 -B scripts/ci/r07_workflow_contract.py --check',
    },
    'obtainx-r00-flutter.yml': {
        'R05 persisted journal and restart regression': 'flutter test --no-pub test/r05_operation_journal_test.dart',
        'R07 Activity Center journal/action and restart tests': 'flutter test --no-pub test/r07_activity_center_test.dart',
    },
}
RISK_PATHS = {'lib/services/r07_*', 'lib/widgets/r07_*', 'test/r07_*', 'scripts/ci/r07_*'}

class ContractError(ValueError):
    pass

class UniqueLoader(yaml.SafeLoader):
    pass

UniqueLoader.yaml_implicit_resolvers = {
    key: [entry for entry in value if entry[0] != 'tag:yaml.org,2002:bool']
    for key, value in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
UniqueLoader.add_implicit_resolver('tag:yaml.org,2002:bool', re.compile(r'^(?:true|false|True|False|TRUE|FALSE)$'), list('tTfF'))

def mapping(loader, node):
    loader.flatten_mapping(node)
    out = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, (str, int, float, bool, type(None))):
            raise ContractError('non-scalar YAML mapping key')
        if key in out:
            raise ContractError(f'duplicate YAML key {key!r} at line {key_node.start_mark.line + 1}')
        out[key] = loader.construct_object(value_node, deep=True)
    return out

UniqueLoader.add_constructor('tag:yaml.org,2002:map', mapping)

def require(ok, message):
    if not ok:
        raise ContractError(message)

def parse_workflow(text, filename, *, require_repair_gate=True):
    require(filename in WORKFLOWS, 'unknown required workflow')
    require(isinstance(text, str) and 0 < len(text) <= 512 * 1024, 'workflow size/type invalid')
    try:
        doc = yaml.load(text, Loader=UniqueLoader)
    except yaml.YAMLError as exc:
        raise ContractError(f'{filename}: invalid YAML: {exc}') from exc
    require(isinstance(doc, dict), f'{filename}: workflow must be a mapping')
    require(doc.get('name') == WORKFLOWS[filename][1], f'{filename}: workflow name changed')
    triggers = doc.get('on')
    require(isinstance(triggers, dict) and 'pull_request' in triggers, f'{filename}: pull_request trigger missing')
    pr = triggers['pull_request']
    require(pr is None or isinstance(pr, dict), f'{filename}: invalid pull_request trigger')
    if isinstance(pr, dict):
        if 'types' in pr:
            require(isinstance(pr['types'], list) and {'opened','reopened','synchronize'} <= set(pr['types']), f'{filename}: required PR event types missing')
        for key in ('branches','branches-ignore','paths','paths-ignore'):
            if key in pr:
                require(isinstance(pr[key], list) and all(isinstance(x,str) for x in pr[key]), f'{filename}: invalid {key} filter')
    require(isinstance(pr, dict) and not ({'paths','paths-ignore','branches','branches-ignore'} & set(pr)), f'{filename}: unconditional PR event routing required')
    require({'opened','reopened','synchronize','labeled','unlabeled','ready_for_review','converted_to_draft'} <= set(pr.get('types',[])), f'{filename}: incomplete mode-change events')
    jobs = doc.get('jobs')
    require(isinstance(jobs, dict) and bool(jobs), f'{filename}: jobs missing')
    actual = {}
    for job_id, job in jobs.items():
        require(isinstance(job_id, str) and isinstance(job, dict), f'{filename}: malformed job')
        if 'uses' in job:
            require(isinstance(job['uses'], str) and 'steps' not in job, f'{filename}/{job_id}: reusable job invalid')
            continue
        require('runs-on' in job, f'{filename}/{job_id}: runs-on missing')
        steps = job.get('steps')
        require(isinstance(steps, list) and bool(steps), f'{filename}/{job_id}: steps missing')
        for i, step in enumerate(steps):
            require(isinstance(step, dict), f'{filename}/{job_id}/{i}: step must be a mapping')
            commands = [key for key in ('run','uses') if key in step]
            require(len(commands) == 1 and isinstance(step[commands[0]], str) and bool(step[commands[0]].strip()), f'{filename}/{job_id}/{i}: step must have exactly one nonempty run or uses')
            label = step.get('name')
            if isinstance(label, str):
                actual.setdefault(label, []).append((job_id, step))
    for label, command in REQUIRED_STEPS.get(filename, {}).items():
        if label == 'Validate required workflow structure' and not require_repair_gate:
            continue
        matches = actual.get(label, [])
        require(len(matches) == 1 and matches[0][1].get('run') == command and 'if' not in matches[0][1] and matches[0][1].get('continue-on-error', False) is False, f'{filename}: missing, duplicated, conditional or displaced required step {label}')
    return doc

SOURCE_EXPR = '${{ github.event.pull_request.head.sha || github.sha }}'
SOURCE_GUARD = 'test "$(git rev-parse HEAD)" = "$OX_EXPECTED_SHA"'


def verify_exact_source(doc, filename):
    """All mandatory jobs must use one exact PR-head identity end-to-end."""
    require(doc.get('env', {}).get('OX_EXPECTED_SHA') == SOURCE_EXPR,
            f'{filename}: workflow exact-source environment missing')
    for job_id, job in doc['jobs'].items():
        label = f'{filename}/{job_id}'
        require(job.get('env', {}).get('OX_EXPECTED_SHA', SOURCE_EXPR) == SOURCE_EXPR,
                f'{label}: job source identity override')
        steps = job.get('steps', [])
        checkout = [i for i, step in enumerate(steps)
                    if step.get('uses', '').startswith('actions/checkout@')]
        require(checkout == [0], f'{label}: exactly one first checkout required')
        require(steps[0].get('with', {}).get('ref') == SOURCE_EXPR,
                f'{label}: checkout not pinned to exact source')
        require(steps[0].get('with', {}).get('persist-credentials') is False,
                f'{label}: checkout credential persistence forbidden')
        guard_lines = steps[1].get('run', '').splitlines() if len(steps)>1 else []
        guard_lines = [line.strip() for line in guard_lines if line.strip()]
        require(SOURCE_GUARD in guard_lines and
                (guard_lines == [SOURCE_GUARD] or
                 guard_lines[:2] == ['set -euo pipefail', SOURCE_GUARD]) and
                'if' not in steps[1] and not steps[1].get('continue-on-error', False),
                f'{label}: unconditional exact-source guard must follow checkout')
        for step in steps:
            require(step.get('env', {}).get('OX_EXPECTED_SHA', SOURCE_EXPR) == SOURCE_EXPR,
                    f'{label}: step source identity override')
            action = step.get('uses', '')
            key = ('key' if action.startswith(('actions/cache/save@', 'actions/cache/restore@'))
                   else 'name' if action.startswith('actions/upload-artifact@') else None)
            if key is not None:
                value = step.get('with', {}).get(key, '')
                require(isinstance(value, str) and SOURCE_EXPR in value,
                        f'{label}: cache/artifact not exact-source bound')


def verify_incremental_route(doc, filename):
    jobs=doc['jobs']; source=filename=='obtainx-r00-contracts.yml'
    scope=jobs['source-contracts'] if source else jobs.get('scope',{})
    steps=[x for x in scope.get('steps',[]) if x.get('id')=='scope']
    require(len(steps)==1 and not steps[0].get('if') and not steps[0].get('continue-on-error'),filename+': scope planning must be unconditional')
    require('python3 -B scripts/ci/obtainx_ci_policy.py plan --head "$OX_EXPECTED_SHA" --github-output "$GITHUB_OUTPUT"' in steps[0].get('run','').splitlines()[-1],filename+': exact scope command missing')
    require(steps[0].get('env',{}).get('OX_SCOPE_TOKEN')=='${{ github.token }}',filename+': read-only proof token missing')
    require(doc.get('permissions')=={'contents':'read','actions':'read'},filename+': scope proof permissions drift')
    marker='OPT07 plan SHA256 ${{ steps.scope.outputs.plan_digest }}'
    proof=[x for x in scope['steps'] if x.get('name')==marker]
    require(len(proof)==1 and scope['steps'].index(proof[0])==scope['steps'].index(steps[0])+1 and not proof[0].get('if') and not proof[0].get('continue-on-error') and proof[0].get('env')=={'OX_PLAN_DIGEST':'${{ steps.scope.outputs.plan_digest }}'} and proof[0].get('run')=='test "${#OX_PLAN_DIGEST}" -eq 64 && [[ "$OX_PLAN_DIGEST" =~ ^[a-f0-9]{64}$ ]]',filename+': exact plan digest proof missing')
    if source:
        guard=[x for x in scope['steps'] if x.get('name')=='Development-only cannot qualify (same runner)']
        require(len(guard)==1 and guard[0] is scope['steps'][-1] and guard[0].get('if')=="steps.scope.outputs.mode == 'scoped'" and guard[0].get('run','').strip().endswith('exit 1') and not guard[0].get('continue-on-error'),filename+': scoped mode could falsely qualify full CI')
    else:
        require(scope.get('name')=='Exact-SHA scope classifier' and 'if' not in scope,filename+': planner job conditional')
        for k in ('mode','full_flutter','targeted_flutter','api36','rt02','rt02b','rt02c','plan'):
            require(scope.get('outputs',{}).get(k)=='${{ steps.scope.outputs.'+k+' }}',filename+': scope output drift '+k)
        runtime={'obtainx-r02-api36.yml':('emulator-api36','api36'),'obtainx-r02-rt02.yml':('rt02-real-install','rt02'),'obtainx-r02-rt02b.yml':('rt02b-negative-install','rt02b'),'obtainx-r02-rt02c.yml':('rt02c-archive-install','rt02c')}
        pairs=[runtime[filename]] if filename in runtime else [('targeted-flutter','targeted_flutter'),('flutter-and-android-debug','full_flutter')]
        for name,key in pairs:
            job=jobs.get(name,{})
            require(job.get('needs')=='scope' and job.get('if')=="needs.scope.outputs."+key+" == 'true'",filename+': incorrect job gate '+name)
        if filename=='obtainx-r00-flutter.yml':
            scoped=[x for x in jobs['targeted-flutter']['steps'] if x.get('name')=='Run only impacted Flutter checks']
            require(len(scoped)==1 and scoped[0].get('env',{}).get('OX_SCOPE_PLAN')=='${{ needs.scope.outputs.plan }}' and 'python3 -B scripts/ci/obtainx_ci_policy.py run-flutter --head "$OX_EXPECTED_SHA"' in scoped[0].get('run',''),filename+': targeted execution not plan-bound')


def verify(root=ROOT, *, overrides=None, require_repair_gate=True):
    root = Path(root)
    overrides = overrides or {}
    policy = json.loads((root/'config/delivery-required-ci.json').read_text(encoding='utf-8'))
    actual = [(r['workflow_id'],r['name']) for r in policy['required_workflows']]
    require(policy['repository']=='Mikeyphw/ObtainX' and policy['base_branch']=='main' and policy['event']=='pull_request' and len(actual)==6 and set(actual)==set(WORKFLOWS.values()), 'required workflow policy drift')
    for name in WORKFLOWS:
        rel = '.github/workflows/'+name
        text = overrides[rel] if rel in overrides else (root/rel).read_text(encoding='utf-8')
        if isinstance(text, bytes): text=text.decode('utf-8')
        doc = parse_workflow(text, name, require_repair_gate=require_repair_gate)
        verify_exact_source(doc, name)
        verify_incremental_route(doc, name)
    return len(WORKFLOWS)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true',required=True)
    parser.add_argument('--root',type=Path,default=ROOT)
    args = parser.parse_args()
    try:
        count = verify(args.root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f'OX_R07_WORKFLOW_REFUSED {exc}\n')
    print(f'OX_R07_REQUIRED_WORKFLOW_STRUCTURE_PASS={count}; HOSTED_CI_NOT_ATTESTED',flush=True)
