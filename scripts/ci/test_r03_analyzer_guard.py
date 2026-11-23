#!/usr/bin/env python3
"""Known R03 Flutter analyzer regressions from PR #23 first hosted run."""
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[2]
class AnalyzerGate(unittest.TestCase):
    def test_previous_flutter_analyzer_failure_is_not_reintroduced(self):
        provider=(ROOT/'lib/providers/apps_provider.dart').read_text()
        engine=(ROOT/'lib/services/r03_download_engine.dart').read_text()
        tests=(ROOT/'test/r03_download_engine_test.dart').read_text()
        self.assertNotIn('HttpHeaders.contentDispositionHeader',provider)
        self.assertNotIn("import 'dart:typed_data';",provider)
        self.assertIn("headers.value('content-disposition')",provider)
        self.assertIn('final R03DownloadRecord initial = R03DownloadRecord(',engine)
        self.assertNotIn('StackTrace __',engine)
        self.assertNotIn('progress: (_, received, __)',tests)
        self.assertIn('const receipt = R03DownloadRecord(',tests)
        self.assertIn('final range = r03ContentRange',engine)
        self.assertIn('await _verifyBlocks(part, previous.blocks)',engine)
    def test_actual_ci_requires_analyzer_before_flutter_and_android(self):
        r00=(ROOT/'.github/workflows/obtainx-r00-flutter.yml').read_text()
        self.assertIn('run: flutter analyze lib test',r00)
        self.assertIn('run: flutter test --no-pub test/r03_download_engine_test.dart',r00)
        self.assertLess(r00.index('run: flutter analyze lib test'),
                        r00.index('run: flutter test --no-pub test/r03_download_engine_test.dart'))
if __name__=='__main__':unittest.main(verbosity=2)
