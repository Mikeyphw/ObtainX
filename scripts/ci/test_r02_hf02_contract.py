"""Fail-closed mutation tests for the R02 HF02 source and hosted CI gates."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('r02_hf02_contract', Path(__file__).with_name('r02_hf02_contract.py'))
assert SPEC is not None and SPEC.loader is not None
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)
PATHS = (
    'lib/providers/apps_provider_install.dart',
    'lib/services/install_bundle_plan.dart',
    '.github/workflows/obtainx-r00-flutter.yml',
    '.github/workflows/obtainx-r00-contracts.yml',
    'scripts/ci/r01_hf02_contract.py',
    'scripts/ci/test_r01_hf02_contract.py',
    'docs/R02_HF02_ANALYZER_RECOVERY.md',
)


class R02HF02Contracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ox-r02-hf02-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for path in PATHS:
            dest = self.root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, dest)

    def mutate(self, rel: str, old: str, new: str) -> None:
        path = self.root / rel
        content = path.read_text(encoding='utf-8')
        self.assertEqual(content.count(old), 1, 'stale mutation anchor: ' + rel)
        path.write_text(content.replace(old, new, 1), encoding='utf-8')
        self.assertTrue(CONTRACT.inspect(self.root), 'security mutation undetected: ' + rel)

    def test_valid_source_contract_passes(self):
        self.assertEqual(CONTRACT.inspect(self.root), [])

    def test_nullable_guard_reintroduction_rejected(self):
        self.mutate('lib/providers/apps_provider_install.dart',
                    'if (apps[resolvedAppId]?.installedInfo == null) {',
                    'if (parsedArchivePath != null && apps[resolvedAppId]?.installedInfo == null) {')

    def test_icon_scan_must_remain_gated(self):
        self.mutate('lib/providers/apps_provider_install.dart',
                    'if (apps[resolvedAppId]?.installedInfo == null) {', 'if (true) {')

    def test_invalid_bundle_abi_must_be_refused(self):
        self.mutate('lib/services/install_bundle_plan.dart',
                    "throw const FormatException('No compatible ABI configuration split');",
                    'return InstallBundlePlan(packageName: packageName, versionCode: versionCode, baseApkPath: base.path, configApkPaths: [], format: format);')

    def test_stale_collection_if_rejected(self):
        self.mutate('lib/services/install_bundle_plan.dart',
                    '[...nonAbi, ?abiMember, ...selectedLocales, ?densityMember]',
                    '[...nonAbi, if (abiMember != null) abiMember, ...selectedLocales, ?densityMember]')

    def test_golden_triage_on_any_failure_rejected(self):
        self.mutate('.github/workflows/obtainx-r00-flutter.yml',
                    "if: ${{ failure() && steps.full_flutter_tests.outcome == 'failure' }}",
                    'if: ${{ failure() }}')

    def test_golden_triage_after_analyzer_failure_rejected(self):
        self.mutate('.github/workflows/obtainx-r00-flutter.yml',
                    "steps.full_flutter_tests.outcome == 'failure'",
                    "steps.analyzer.outcome == 'failure'")

    def test_full_suite_id_removed_rejected(self):
        self.mutate('.github/workflows/obtainx-r00-flutter.yml',
                    'id: full_flutter_tests', 'id: renamed')

    def test_analyzer_gate_removed_rejected(self):
        self.mutate('.github/workflows/obtainx-r00-flutter.yml',
                    'flutter analyze lib test', 'echo analyzer skipped')

    def test_new_contract_ci_gate_removed_rejected(self):
        self.mutate('.github/workflows/obtainx-r00-contracts.yml',
                    'python3 scripts/ci/r02_hf02_contract.py --check', 'echo disabled')

    def test_legacy_contract_drift_rejected(self):
        self.mutate('scripts/ci/r01_hf02_contract.py',
                    "steps.full_flutter_tests.outcome == 'failure'", "steps.analyzer.outcome == 'failure'")

    def test_legacy_negative_fixture_removal_rejected(self):
        self.mutate('scripts/ci/test_r01_hf02_contract.py',
                    'test_full_suite_step_id_removal_refused', 'test_removed')


if __name__ == '__main__':
    unittest.main()
