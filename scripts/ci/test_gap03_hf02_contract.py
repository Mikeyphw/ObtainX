"""Supplemental non-replay/ownership guards; not a Dart runtime substitute."""
from pathlib import Path
import hashlib
import json
import unittest

ROOT = Path(__file__).resolve().parents[2]
GUARDS = {
    'lib/services/r07_journal_guard.dart': (
        'final _leases = <String, Completer<void>>{};',
        'await _leases[key]!.future.timeout(remaining)',
        'const {5, 6}.contains(code & 0xff)',
        'if (entered || !cleanupSucceeded || !_isContention(error)) { rethrow; }',
        'await Future<void>.delayed(remaining < pause ? remaining : pause)',
        'entered = true;\n            return await operation(txn);',
        'cleanupSucceeded = false;',
        '_leases.remove(key);\n    lease.complete();',
        "PRAGMA busy_timeout=0",
        'exclusive: true, acquisitionTimeout: acquisitionTimeout',
    ),
    'lib/services/r07_operation_timeline.dart': (
        'Future<T> Function(Transaction) action',
        'return withR07SqliteTransaction(path, () async {',
        '}, action, exclusive: true);',
        'if (entered) { rethrow; }',
        "where: 'id = ? AND revision = ?'",
        'acquisitionTimeout: const Duration(milliseconds: 100)',
    ),
    'lib/services/r03_download_history.dart': ('on R07JournalBusy', 'acquisitionTimeout: const Duration(milliseconds: 100)', '_eligible(latest, preview.cutoff'),
    'lib/services/r05_operation_journal.dart': ("withR07JournalGuard(root, 'install-journal', operation)", 'preview.channel != current.channel'),
    'lib/providers/apps_provider_updates.dart': ('unawaited(completer.future.then<void>', 'completer.completeError(error, stack)', 'await Future.wait(List.generate(workerCount, (_) => runWorker()))'),
    'test/r07_operation_timeline_test.dart': ('parallel first-open and bulk workers', 'independent SQLite writer retries acquisition', 'independent writer timeout', 'callback errors roll back and never replay', 'local per-identity guard times out'),
    'test/multi_source_app_actions_test.dart': ('bulk refresh persists the result for each requested listing', "row.stage == 'checked' && row.finished", 'a durable journal refusal reaches the caller without duplicate async errors'),
    'test/r03_download_history_test.dart': ('expect(outcomes.toSet(), {260, -1});', 'on R07JournalBusy'),
    'test/r05_operation_journal_test.dart': ('expect(outcomes.toSet(), {1, -1});', 'on R07JournalBusy'),
    '.github/workflows/obtainx-r00-flutter.yml': ('flutter analyze lib test integration_test', 'test/r07_operation_timeline_test.dart test/r03_download_history_test.dart test/multi_source_app_actions_test.dart'),
}


def violations(sources):
    return [(path, marker) for path, markers in GUARDS.items()
            for marker in markers if marker not in sources[path]]


class Gap03Hf02Contract(unittest.TestCase):
    def setUp(self):
        self.sources = {path: (ROOT / path).read_text() for path in GUARDS}

    def test_current_concurrency_guards(self):
        self.assertEqual(violations(self.sources), [])
        self.assertNotIn('on DatabaseException {', self.sources['lib/services/r07_operation_timeline.dart'])
        self.assertNotIn('on DatabaseException {', self.sources['lib/services/r03_download_history.dart'])
        self.assertNotIn('db.transaction(', self.sources['lib/services/r07_operation_timeline.dart'])

    def test_each_concurrency_guard_mutation_is_detected(self):
        for path, markers in GUARDS.items():
            for marker in markers:
                with self.subTest(path=path, marker=marker):
                    changed = self.sources.copy()
                    changed[path] = changed[path].replace(marker, 'REMOVED_HF02_GUARD')
                    self.assertIn((path, marker), violations(changed))

    def test_roadmap_and_strict_required_workflows(self):
        baseline = json.loads((ROOT / 'docs/R00_BASELINE.json').read_bytes())
        self.assertEqual(baseline['roadmap_sha256'], hashlib.sha256((ROOT / 'docs/ROADMAP.md').read_bytes()).hexdigest())
        self.assertFalse(baseline['release_authorized'])
        policy = json.loads((ROOT / 'config/delivery-required-ci.json').read_bytes())
        self.assertEqual(len(policy['required_workflows']), 6)
