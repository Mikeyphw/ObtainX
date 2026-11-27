"""G06/G07 source integration guard. Dart/runtime acceptance remains separate."""
from pathlib import Path
import hashlib
import json
import unittest

ROOT = Path(__file__).resolve().parents[2]
GUARDS = {
    'lib/providers/apps_provider_updates.dart': (
        'timeline.enqueue([expected])', 'timeline.run(entry, expected, \'checking\'',
        'checkIntent(current), \'checking\'', 'resumeQueued: resumeQueued'),
    'lib/providers/apps_provider_install.dart': (
        "successStage: expected.kind == 'install' ? 'ready' : 'downloadReady'",
        "advance(timelineId, 'downloaded', transferId: observation.jobId)",
        "advance(timelineId, 'extracting')", 'retryParent?.id',
        'timeline.beginPreparation(R07OperationIntent', 'timelineId: intentId',
        'linkAttempt(intentId, receipt.id', 'Operation timeline binding refused before handoff',
        'clearDownloadCancellation(original.listingKey, cancellationToken)',
        'provenance.archiveSha256 != (containerDigest ?? digest)'),
    'lib/services/r07_operation_timeline.dart': (
        'withR07JournalGuard', "where: 'id = ? AND revision = ?'", 'PRIMARY KEY(operationId, revision)',
        "reason: stage == 'cancelled'", 'R07ProcessState.dead',
        "current.intent.kind != 'install'", 'historyConditions.join',
        'SUM(finished)', 'expectedStage: entry.stage'),
    'lib/services/r03_download_engine.dart': (
        'resumeRecord.explicitlyResumable', 'jsonEncode(previous.toJson()) != jsonEncode(resumeRecord.toJson())',
        '_verifyBlocks(part, previous.blocks)', "..['if-range'] = checkpoint.ifRange!",
        'range.start == acceptedBytes', 'range.total == checkpoint.totalBytes',
        'Explicit resume requires an exact validated range',
        'startedWrite || (resumeRecord == null && previous?.explicitlyResumable != true)',
        '_refuseForeignPartial(initial)'),
    'lib/services/r03_download_history.dart': (
        'record.cacheRootFingerprint != r07JournalFingerprint(cache.absolute.path)',
        'owner.releaseFingerprint == null', 'archiveName(current, bytes)',
        "[base, '$base.part', '$base-dir']", 'withR07JournalGuard(root',
        'current.entries[entry.key] != entry.value', '_eligible(latest, preview.cutoff'),
    'lib/services/r05_operation_journal.dart': (
        'item.channelFingerprint != null', 'referencedParents.contains(item.id)',
        'all.where((item) => !_terminal(item)).length >= maxOperations',
        'withR07JournalGuard(root', 'await active.rename(target.path)',
        'parent.releaseFingerprint != releaseFingerprint', 'preview.channel != current.channel'),
    'lib/services/r07_activity_catalog.dart': (
        'R03DownloadHistory.readRecord(entity, archived: archived)', 'historyLimit: historyLimit',
        'installRead.unreadableCount == 0', '!entry.archivedTransfer',
        'entry.download?.explicitlyResumable == true'),
    'lib/widgets/r07_activity_center_page.dart': (
        'channel == r11ChannelFingerprint(live)', 'resumeRecord: record',
        'retryParent: entry.install', 'cancelQueued(entry.timeline!.id)',
        'channel: channel, preview: preview', 'transfers.prune(downloadPreview)',
        'provider.checkUpdates(specificIds:', 'provider.downloadAndInstallLatestApps('),
    '.github/workflows/obtainx-r00-flutter.yml': (
        'flutter analyze lib test integration_test', 'test/r07_operation_timeline_test.dart',
        'test/r03_download_history_test.dart', 'test/r03_download_engine_test.dart'),
}


def violations(sources):
    return [(path, marker) for path, markers in GUARDS.items()
            for marker in markers if marker not in sources[path]]


class Gap03Contract(unittest.TestCase):
    def setUp(self):
        self.sources = {p: (ROOT / p).read_text() for p in GUARDS}

    def test_integrated_source_guard(self):
        self.assertEqual(violations(self.sources), [])

    def test_each_critical_guard_refuses_mutation(self):
        for path, markers in GUARDS.items():
            for marker in markers:
                with self.subTest(path=path, marker=marker):
                    changed = dict(self.sources)
                    changed[path] = changed[path].replace(marker, 'REMOVED_GAP03_GUARD')
                    self.assertIn((path, marker), violations(changed))

    def test_roadmap_identity_and_full_hosted_policy(self):
        baseline = json.loads((ROOT / 'docs/R00_BASELINE.json').read_bytes())
        self.assertEqual(baseline['roadmap_sha256'], hashlib.sha256((ROOT / 'docs/ROADMAP.md').read_bytes()).hexdigest())
        policy = json.loads((ROOT / 'config/delivery-required-ci.json').read_bytes())
        self.assertEqual(len(policy['required_workflows']), 6)
        self.assertFalse(baseline['release_authorized'])
