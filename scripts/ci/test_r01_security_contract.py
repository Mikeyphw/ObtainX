"""Mutation tests: security contract must reject bypasses and stale artifacts."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

MODULE_PATH = Path(__file__).with_name('r01_security_contract.py')
spec = importlib.util.spec_from_file_location('r01_security_contract', MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)
ROOT = MODULE_PATH.resolve().parents[2]

class R01Contracts(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(prefix='oxr01-')
        self.root = Path(self.t.name)
        copy_paths = [
            'lib/services/artifact_file_work.dart',
            'lib/providers/apps_provider_install.dart',
            '.github/workflows/obtainx-r00-flutter.yml',
            '.github/workflows/obtainx-r00-contracts.yml',
            'docs/SECURITY_RELEASE_POLICY.md',
            'docs/R01_ARCHIVE_SECURITY.md',
            'docs/R01_FIXTURE_SHA256.json',
            'test/archive_extraction_security_test.dart',
        ]
        for rel in copy_paths:
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, p)
        source = ROOT / module.FIXTURE_DIR
        target = self.root / module.FIXTURE_DIR
        shutil.copytree(source, target)
    def tearDown(self):
        self.t.cleanup()
    def mutate(self, rel, before, after):
        p = self.root / rel
        data = p.read_text()
        self.assertIn(before, data)
        p.write_text(data.replace(before, after, 1))
    def test_baseline_passes(self):
        self.assertEqual(module.inspect(self.root, git_check=False), [])
    def test_native_unbounded_zip_is_refused(self):
        self.mutate('lib/providers/apps_provider_install.dart',
                    'await extractZipOffIsolate(filePath, destinationPath);',
                    'await ZipFile.extractToDirectory(zipFile: File(filePath), destinationDir: Directory(destinationPath));')
        self.assertTrue(module.inspect(self.root, git_check=False))
    def test_archive_limit_removed_is_refused(self):
        self.mutate('lib/services/artifact_file_work.dart', 'byteCount > maxBytes - written', 'false')
        self.assertTrue(module.inspect(self.root, git_check=False))
    def test_zip_crc_verification_bypass_is_refused(self):
        self.mutate('lib/services/artifact_file_work.dart',
                    '_fileCrc32(file) != entry.crc32',
                    'false')
        self.assertTrue(module.inspect(self.root, git_check=False))
    def test_tampered_adversarial_fixture_is_refused(self):
        (self.root / module.FIXTURE_DIR / 'traversal.zip').write_bytes(b'forged fixture')
        self.assertTrue(any('fixture corrupted' in e for e in module.inspect(self.root, git_check=False)))
    def test_flutter_gate_removed_is_refused(self):
        self.mutate('.github/workflows/obtainx-r00-flutter.yml',
                    'flutter test --no-pub test/archive_extraction_security_test.dart',
                    'echo testing is optional')
        self.assertTrue(module.inspect(self.root, git_check=False))
    def test_release_workflow_restoration_refused(self):
        (self.root / '.github/workflows' / 'release.yml').write_text('name: Release\n')
        self.assertTrue(module.inspect(self.root, git_check=False))

if __name__ == '__main__':
    unittest.main()
