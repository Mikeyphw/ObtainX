"""Supplemental source guard, not a substitute for strict Dart analysis."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
INSTALL = "lib/providers/apps_provider_install.dart"
LIFECYCLE = "lib/providers/apps_provider_lifecycle.dart"
ARCHIVE = "lib/services/artifact_file_work.dart"
MUTATIONS = (
    (INSTALL, "import 'dart:io';", "import 'dart:io';\nimport 'dart:typed_data';"),
    (INSTALL, "raw['signers'] is! List) {\n        return null;\n      }", "raw['signers'] is! List) return null;"),
    (LIFECYCLE, "commitGuard: commitGuard)) {\n                  return;\n                }", "commitGuard: commitGuard)) return;"),
    (ARCHIVE, "ownership.closeSync();", "ownership?.closeSync();"),
    (ARCHIVE, "_StrictBzipInput(super.source, int offset, int count)\n      : super.fromFileStream(position: offset, length: count, bufferSize: 65536);", "_StrictBzipInput(archive.InputFileStream source, int offset, int count)\n      : super.fromFileStream(source, position: offset, length: count, bufferSize: 65536);"),
)

def findings(source):
    result = []
    for index, (path, repaired, previous) in enumerate(MUTATIONS):
        content = source[path]
        if repaired not in content or (index != 3 and previous in content and previous != repaired):
            result.append(index)
    return result

class Gap02Hf01Contract(unittest.TestCase):
    def setUp(self):
        self.source = {name: (ROOT / name).read_text() for name in (INSTALL, LIFECYCLE, ARCHIVE)}

    def test_current_production_source(self):
        self.assertEqual(findings(self.source), [])
        self.assertIn("catch (_) {\n    ownership?.closeSync();", self.source[ARCHIVE])
        self.assertIn("import 'package:flutter/services.dart';", self.source[INSTALL])

    def test_each_historical_mutation_is_rejected(self):
        for index, (path, repaired, previous) in enumerate(MUTATIONS):
            with self.subTest(index=index):
                changed = self.source.copy()
                self.assertEqual(changed[path].count(repaired), 1)
                changed[path] = changed[path].replace(repaired, previous, 1)
                self.assertEqual(findings(changed), [index])
