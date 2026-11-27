"""Exact-head admission controls and pause/checkpoint regression contracts."""
from pathlib import Path
import copy
import subprocess
import sys
import unittest

import obtainx_ci_optimization_opt08_prerequisites as opt
from obtainx_ci_policy import FULL_PROOFS, REPO_ID
from r07_workflow_contract import parse_workflow

ROOT = Path(__file__).resolve().parents[2]
HEAD = 'a' * 40
TREE = 'b' * 40


class Fixture:
    def __init__(self):
        self.runs = {}
        self.jobs = {}
        for lane, number in [('source', 11), ('flutter', 22)]:
            workflow, name, steps = FULL_PROOFS[lane]
            steps = opt.FLUTTER_STEPS if lane == 'flutter' else steps
            self.runs[workflow] = [dict(id=number, workflow_id=workflow, head_sha=HEAD,
                event='pull_request', repository={'id': REPO_ID},
                head_repository={'id': REPO_ID}, run_attempt=1,
                status='completed' if lane == 'source' else 'in_progress',
                conclusion='success' if lane == 'source' else None)]
            self.jobs[number] = [dict(id=100 + number, run_id=number, run_attempt=1,
                head_sha=HEAD, name=name, status='completed' if lane == 'source' else 'in_progress',
                conclusion='success' if lane == 'source' else None,
                steps=[dict(name=s, status='completed', conclusion='success') for s in steps])]

    def __call__(self, path):
        if path.startswith('/actions/workflows/'):
            return {'workflow_runs': copy.deepcopy(self.runs[int(path.split('/')[3])])}
        number = int(path.split('/')[3])
        if '/jobs?' in path:
            jobs = self.jobs[number]
            return {'jobs': copy.deepcopy(jobs), 'total_count': len(jobs)}
        return copy.deepcopy(next(row for rows in self.runs.values() for row in rows if row['id'] == number))

    def run(self, lane):
        return self.runs[FULL_PROOFS[lane][0]][0]


class Opt08Prerequisites(unittest.TestCase):
    def test_exact_success_reused_for_admission_only(self):
        result = opt.wait(HEAD, TREE, api=Fixture(), polls=1)
        self.assertEqual(result['head'], HEAD)
        self.assertEqual(result['tree'], TREE)
        self.assertEqual(result['flutter']['run_id'], 22)
        self.assertEqual(result['source']['run_id'], 11)
        self.assertFalse(result['android_qualified'])
        self.assertFalse(result['release_qualified'])

    def test_pause_failure_refuses_before_android(self):
        f = Fixture()
        f.jobs[22][0]['steps'][-1]['conclusion'] = 'failure'
        with self.assertRaises(ValueError):
            opt.wait(HEAD, TREE, api=f, polls=1)

    def test_all_flutter_decisive_steps_required_before_android(self):
        workflow = (ROOT / '.github/workflows/obtainx-r00-flutter.yml').read_text()
        self.assertIn('Execute full Flutter test suite', opt.FLUTTER_STEPS)
        self.assertIn('R09 byte-backed artifact metadata review', opt.FLUTTER_STEPS)
        self.assertIn('name: R09 byte-backed artifact metadata review\n        run: flutter test --no-pub test/r09_artifact_inspection_test.dart', workflow)
        self.assertIn('R08 source reliability named regressions', opt.FLUTTER_STEPS)
        self.assertIn('F-Droid and source provider digest regressions', opt.FLUTTER_STEPS)
        self.assertIn('name: F-Droid and source provider digest regressions\n        run: flutter test --no-pub test/source_provider_test.dart', workflow)
        for name in opt.FLUTTER_STEPS:
            with self.subTest(step=name):
                for state in ('failure', 'skipped'):
                    f = Fixture()
                    step = next(s for s in f.jobs[22][0]['steps'] if s['name'] == name)
                    step['conclusion'] = state
                    with self.assertRaises(ValueError):
                        opt.wait(HEAD, TREE, api=f, polls=1)
                f = Fixture()
                step = next(s for s in f.jobs[22][0]['steps'] if s['name'] == name)
                step.update(status='in_progress', conclusion=None)
                with self.assertRaises(TimeoutError):
                    opt.wait(HEAD, TREE, api=f, polls=1)

    def test_skipped_step_refused(self):
        f = Fixture()
        f.jobs[22][0]['steps'][-1]['conclusion'] = 'skipped'
        with self.assertRaises(ValueError):
            opt.wait(HEAD, TREE, api=f, polls=1)

    def test_pending_and_wrong_head_do_not_qualify(self):
        for key, value in [('head_sha', 'c' * 40), ('head_repository', {'id': 42}), ('workflow_id', 99)]:
            with self.subTest(key=key):
                f = Fixture(); f.run('flutter')[key] = value
                with self.assertRaises(TimeoutError):
                    opt.wait(HEAD, TREE, api=f, polls=1)
        f = Fixture(); f.jobs[22][0]['steps'][-1].update(status='in_progress', conclusion=None)
        sleeps = []
        with self.assertRaises(TimeoutError):
            opt.wait(HEAD, TREE, api=f, polls=3, sleep=sleeps.append)
        self.assertEqual(sleeps, [30, 30])

    def test_latest_failure_not_masked_by_older_success(self):
        f = Fixture(); newer = copy.deepcopy(f.run('flutter'))
        newer.update(id=23, status='completed', conclusion='failure')
        f.runs[FULL_PROOFS['flutter'][0]].append(newer)
        with self.assertRaises(ValueError):
            opt.wait(HEAD, TREE, api=f, polls=1)

    def test_wrong_job_identity_and_duplicate_step_refused(self):
        for key, value in [('head_sha', 'c' * 40), ('run_attempt', 2), ('run_id', 999), ('id', 0)]:
            with self.subTest(key=key):
                f = Fixture(); f.jobs[22][0][key] = value
                with self.assertRaises(ValueError):
                    opt.wait(HEAD, TREE, api=f, polls=1)
        f = Fixture(); f.jobs[22][0]['steps'].append(copy.deepcopy(f.jobs[22][0]['steps'][0]))
        with self.assertRaises(ValueError):
            opt.wait(HEAD, TREE, api=f, polls=1)

    def test_source_failure_and_missing_jobs_refuse(self):
        f = Fixture(); f.run('source')['conclusion'] = 'failure'
        with self.assertRaises(ValueError):
            opt.wait(HEAD, TREE, api=f, polls=1)
        f = Fixture(); f.jobs[11] = []
        with self.assertRaises(ValueError):
            opt.wait(HEAD, TREE, api=f, polls=1)

    def test_rerun_during_proof_never_accepts_old_attempt(self):
        f = Fixture(); calls = 0
        def api(path):
            nonlocal calls
            if path == '/actions/runs/22':
                calls += 1
                if calls >= 2:
                    f.run('flutter')['run_attempt'] = 2
            return f(path)
        with self.assertRaises(TimeoutError):
            opt.wait(HEAD, TREE, api=api, polls=1)

    def test_all_four_real_lanes_wait_before_runtime_and_keep_manual_route(self):
        for lane in ('api36', 'rt02', 'rt02b', 'rt02c'):
            name = f'obtainx-r02-{lane}.yml'
            content = (ROOT/'.github/workflows'/name).read_text()
            parse_workflow(content, name)
            self.assertEqual(content.count('Await exact-head source and full Flutter test prerequisites'), 1)
            self.assertIn(f"if: github.event_name == 'pull_request' && steps.scope.outputs.mode == 'full' && steps.scope.outputs.{lane} == 'true'", content)
            self.assertIn(f"needs: scope\n    if: needs.scope.outputs.{lane} == 'true'", content)
            self.assertLess(content.index('Await exact-head source'), content.index('Set up Java 21'))
            self.assertNotIn('continue-on-error: true', content)
            self.assertIn('  workflow_dispatch:', content)

    def test_safe_path_direct_cli_help(self):
        result = subprocess.run([sys.executable, '-B', '-P', str(ROOT/'scripts/ci/obtainx_ci_optimization_opt08_prerequisites.py'), '--help'],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--head', result.stdout)

    def test_checkpoint_boundary_not_transport_chunk_and_synchronized_fixture(self):
        engine = (ROOT/'lib/services/r03_download_engine.dart').read_text()
        self.assertIn('await output.writeFrom(incoming, index, end);', engine)
        self.assertNotIn('await output.writeFrom(incoming);', engine)
        self.assertIn('received += count;', engine)
        start = engine.index('await output.writeFrom(incoming, index, end);')
        self.assertLess(engine.index('await _save(journal, active);', start),
                        engine.index('onPauseAvailable?.call(active.explicitlyResumable &&', start))
        test = (ROOT/'test/r03_download_engine_test.dart').read_text()
        self.assertIn('gate.future.timeout', test)
        self.assertIn('expect(saved.validatedBytes, r03ChunkBytes);', test)
        self.assertIn('expect(await output.readAsBytes(), payload);', test)
        self.assertIn('coalesced response still exposes first durable pause boundary', test)


if __name__ == '__main__':
    unittest.main()
