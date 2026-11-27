#!/usr/bin/env python3
"""Read-only exact-head prerequisites for full PR Android qualification.

Reuse existing successful steps on this exact commit/tree, never a green badge
from another commit, a skipped test, or an earlier superseded attempt. This is
only admission to Android work, not Android/release acceptance. The four real
emulator jobs and their independent evidence gates remain mandatory.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Resolve only the tracked sibling even under Python safe-path execution.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from obtainx_ci_policy import FULL_PROOFS, REPO_ID, SHA, git, read_api

FLUTTER_STEPS = (
    'Analyze current source and tests',
    'R03 deterministic mock HTTP resume and persistence tests',
    'R08 source reliability named regressions',
    'F-Droid and source provider digest regressions',
    'R09 byte-backed artifact metadata review',
    'R10 accessibility and package lookup regressions',
    'Execute full Flutter test suite',
)
MAX_POLLS = 24
POLL_SECONDS = 30


def latest_run(api, workflow, head):
    path = f'/actions/workflows/{workflow}/runs?head_sha={head}&event=pull_request&per_page=50'
    rows = api(path).get('workflow_runs')
    if not isinstance(rows, list):
        raise ValueError('invalid workflow inventory')
    matches = [row for row in rows if row.get('workflow_id') == workflow
               and row.get('head_sha') == head and row.get('event') == 'pull_request'
               and row.get('repository', {}).get('id') == REPO_ID
               and row.get('head_repository', {}).get('id') == REPO_ID
               and type(row.get('id')) is int and row['id'] > 0
               and type(row.get('run_attempt')) is int and row['run_attempt'] > 0]
    if not matches:
        return None
    row = max(matches, key=lambda r: (r['id'], r['run_attempt']))
    # Re-read the exact run so the attempt and result do not depend on a
    # potentially stale list response. Refuse a run identity change.
    current = api(f'/actions/runs/{row["id"]}')
    for key in ('id', 'workflow_id', 'head_sha', 'event', 'repository', 'head_repository'):
        if key in ('repository', 'head_repository'):
            if current.get(key, {}).get('id') != REPO_ID:
                raise ValueError('run repository changed')
        elif current.get(key) != row[key]:
            raise ValueError('run identity changed')
    attempt = current.get('run_attempt')
    if type(attempt) is not int or attempt < row['run_attempt']:
        raise ValueError('run attempt regressed')
    return current


def observe(api, lane, head):
    workflow, job_name, source_steps = FULL_PROOFS[lane]
    decisive = FLUTTER_STEPS if lane == 'flutter' else source_steps
    row = latest_run(api, workflow, head)
    if row is None:
        return 'PENDING', None
    state, conclusion = row.get('status'), row.get('conclusion')
    if state == 'completed' and conclusion != 'success':
        raise ValueError(f'{lane} prerequisite failed: {conclusion}')
    if state not in ('queued', 'in_progress', 'requested', 'waiting', 'pending', 'completed'):
        raise ValueError('unknown prerequisite state')
    if lane == 'source' and state != 'completed':
        return 'PENDING', None
    jobs = api(f'/actions/runs/{row["id"]}/attempts/{row["run_attempt"]}/jobs?per_page=100')
    inventory = jobs.get('jobs')
    if not isinstance(inventory, list) or jobs.get('total_count') != len(inventory):
        raise ValueError('incomplete prerequisite job inventory')
    matches = [job for job in inventory if job.get('name') == job_name]
    if len(matches) != 1:
        if not matches and state != 'completed':
            return 'PENDING', None
        raise ValueError('missing or duplicate decisive job')
    job = matches[0]
    if (type(job.get('id')) is not int or job['id'] <= 0 or
            job.get('run_id') != row['id'] or job.get('run_attempt') != row['run_attempt']
            or job.get('head_sha') != head):
        raise ValueError('decisive job identity mismatch')
    if job.get('status') == 'completed' and job.get('conclusion') != 'success':
        raise ValueError(f'{lane} decisive job failed')
    steps = job.get('steps') or []
    for name in decisive:
        candidates = [step for step in steps if step.get('name') == name]
        if len(candidates) > 1:
            raise ValueError('ambiguous prerequisite step')
        if not candidates or candidates[0].get('status') != 'completed':
            if state == 'completed':
                raise ValueError('completed run lacks decisive step')
            return 'PENDING', None
        if candidates[0].get('conclusion') != 'success':
            raise ValueError(f'{lane} decisive step failed or skipped')
    if lane == 'source' and job.get('conclusion') != 'success':
        raise ValueError('source contract job not successful')
    # A rerun or a newly queued replacement can supersede a prior observation.
    # Re-read the newest identity once before accepting the proof.
    verified = latest_run(api, workflow, head)
    if verified is None or (verified['id'], verified['run_attempt']) != (row['id'], row['run_attempt']):
        return 'PENDING', None
    if verified.get('status') == 'completed' and verified.get('conclusion') != 'success':
        raise ValueError('prerequisite failed during observation')
    return 'PASS', {'workflow_id': workflow, 'run_id': row['id'],
                    'attempt': row['run_attempt'], 'job_id': job.get('id'),
                    'head': head, 'steps': list(decisive)}


def wait(head, tree, *, api=read_api, sleep=time.sleep, polls=MAX_POLLS):
    if not SHA.fullmatch(head) or not SHA.fullmatch(tree) or not 1 <= polls <= MAX_POLLS:
        raise ValueError('invalid prerequisite identity or poll bound')
    for index in range(polls):
        # Observe both on every pass: a failure that becomes visible while the
        # other lane is pending must refuse rather than launch Android work.
        source, source_proof = observe(api, 'source', head)
        flutter, flutter_proof = observe(api, 'flutter', head)
        print(f'OX_OPT08_PREREQUISITE poll={index + 1} source={source} flutter={flutter}', flush=True)
        if source == flutter == 'PASS':
            return {'schema': 'obtainx.ci-prerequisites.v1', 'head': head, 'tree': tree,
                    'source': source_proof, 'flutter': flutter_proof,
                    'android_qualified': False, 'release_qualified': False}
        if index + 1 < polls:
            sleep(POLL_SECONDS)
    raise TimeoutError('exact-head prerequisites did not pass within the bounded window')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--head', required=True)
    args = parser.parse_args()
    if git('rev-parse', 'HEAD').strip() != args.head:
        raise ValueError('prerequisite checkout mismatch')
    tree = git('rev-parse', 'HEAD^{tree}').strip()
    evidence = wait(args.head, tree)
    print('OX_OPT08_PREREQUISITE_PASS ' + json.dumps(evidence, sort_keys=True), flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, AttributeError) as exc:
        # Fixed categories only; API exceptions may contain private details.
        print('OX_OPT08_PREREQUISITE_REFUSED ' + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
