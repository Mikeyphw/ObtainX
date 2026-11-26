"""Supplemental source mutation checks for the 12 observed analyzer diagnostics.
Strict hosted Dart analysis and actual Flutter tests remain mandatory.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
MUTATIONS = (('lib/providers/apps_provider_install.dart', "live.id != expected.packageId) {\n          throw StateError('Queued release changed before execution');\n        }", "live.id != expected.packageId) throw StateError('Queued release changed before execution');"), ('lib/providers/apps_provider_install.dart', 'if (appContext != null && appContext.mounted) {\n        notificationsProvider = appContext.read<NotificationsProvider>();', 'if (appContext != null) {\n        notificationsProvider = appContext.read<NotificationsProvider>();'), ('lib/providers/apps_provider_install.dart', "downloadedFile.timelineId ?? downloadedDir?.timelineId, 'declined');", "downloadedFile?.timelineId ?? downloadedDir?.timelineId, 'declined');"), ('lib/providers/apps_provider_install.dart', "downloadedFile?.timelineId ?? downloadedDir.timelineId, 'declined');", "downloadedFile?.timelineId ?? downloadedDir?.timelineId, 'declined');"), ('lib/services/r03_download_engine.dart', "'releaseFingerprint': ?releaseFingerprint", "if (releaseFingerprint != null) 'releaseFingerprint': releaseFingerprint!"), ('lib/services/r03_download_history.dart', 'await FileSystemEntity.type(entity.path, followLinks: false) == FileSystemEntityType.file) {\n          continue;\n        }', 'await FileSystemEntity.type(entity.path, followLinks: false) == FileSystemEntityType.file) continue;'), ('lib/services/r03_download_history.dart', '!await _eligible(current, cutoff, entity, null, null, null)) {\n            return;\n          }', '!await _eligible(current, cutoff, entity, null, null, null)) return;'), ('lib/services/r07_activity_catalog.dart', 'List<R07ActivityRecord>.unmodifiable(<R07ActivityRecord>[...active, ...finished]..sort(compare))', 'List<R07ActivityRecord>.unmodifiable([...active, ...finished]..sort(compare))'), ('lib/services/r07_operation_timeline.dart', "whereArgs: [id, previous.revision]) != 1) {\n        throw StateError('Operation revision conflict');\n      }", "whereArgs: [id, previous.revision]) != 1) throw StateError('Operation revision conflict');"), ('lib/widgets/r07_activity_center_page.dart', "if (mounted) {\n        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(\n          content: Text('The retained transfer could not resume. No new install was authorized.')));\n      }", "if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(\n        content: Text('The retained transfer could not resume. No new install was authorized.')));"), ('lib/widgets/r07_activity_center_page.dart', "if (mounted) {\n          ScaffoldMessenger.of(context).showSnackBar(SnackBar(\n            content: Text('Retention stopped after a history change or I/O error. At least $count receipts removed; review the refreshed history.')));\n        }", "if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(\n          content: Text('Retention stopped after a history change or I/O error. At least $count receipts removed; review the refreshed history.')));"), ('lib/widgets/r07_activity_center_page.dart', 'onChanged: _busy ? null : (value) {\n                      if (value != null) {\n                        setState(() {\n                          _channel = value; _historyLimit = _pageSize; _load();\n                        });\n                      }\n                    },', 'onChanged: _busy ? null : (value) { if (value != null) setState(() {\n                      _channel = value; _historyLimit = _pageSize; _load();\n                    }); },'))

def violations(sources):
    return [i for i, (path, required, _) in enumerate(MUTATIONS)
            if required not in sources[path]]

class Gap03Hf01Contract(unittest.TestCase):
    def setUp(self):
        self.sources = {p: (ROOT / p).read_text() for p, _, _ in MUTATIONS}

    def test_current_source(self):
        self.assertEqual(violations(self.sources), [])

    def test_each_regression_refused(self):
        for i, (path, required, old) in enumerate(MUTATIONS):
            with self.subTest(diagnostic=i+1, path=path):
                changed = self.sources.copy()
                self.assertEqual(changed[path].count(required), 1)
                changed[path] = changed[path].replace(required, old, 1)
                self.assertEqual(violations(changed), [i])
