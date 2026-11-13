"""P04A negative source mutations; source tests do not certify Android runtime."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'r02f_p04_contract', ROOT/'scripts/ci/r02f_p04_contract.py')
assert SPEC and SPEC.loader
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)

class P04SourceMutations(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ox-r02f-p04-source-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in C.PATHS:
            dst = self.root/name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/name, dst)

    def mutate(self, path: str, old: str, new: str):
        target = self.root/path
        original = target.read_text('utf-8')
        self.assertEqual(original.count(old), 1, 'test anchor missing/nonunique: '+path)
        target.write_text(original.replace(old,new,1), 'utf-8')
        self.assertTrue(C.inspect(self.root), 'unsafe mutation escaped '+path)

    def test_00_valid_source(self):
        self.assertEqual(C.inspect(self.root), [])

    def test_01_cannot_skip_pending_receipt(self):
        self.mutate(C.PROVIDER, '    pending != null &&\n    pending.belongsTo(app)', '    true &&\n    pending.belongsTo(app)')

    def test_02_cannot_skip_listing_provenance(self):
        self.mutate(C.PROVIDER, 'pending.belongsTo(app)', 'true')

    def test_03_cannot_skip_observed_version(self):
        self.mutate(C.PROVIDER, 'pending.matchesPackage(installedInfo)', 'true')

    def test_04_cannot_skip_package_identity(self):
        self.mutate(C.PROVIDER, 'installedInfo.packageName == app.id', 'true')

    def test_05_cannot_redirect_observed_broadcast_to_success(self):
        # The production classifier has TWO return handedOff() branches.
        # Mutate the broadcast-observed branch by its unique enclosing context.
        self.mutate(C.CLASSIFY,
          'if (bridgeChangeObserved) {\n    return InstallResult.handedOff();',
          'if (bridgeChangeObserved) {\n    return InstallResult.success();')

    def test_05b_cannot_redirect_unobserved_timeout_to_success(self):
        # The fallback must remain a handoff too, not cancelled or confirmed.
        self.mutate(C.CLASSIFY,
          '  }\n  return InstallResult.handedOff();\n}',
          '  }\n  return InstallResult.success();\n}')

    def test_06_cannot_bypass_confirmation_guard(self):
        self.mutate(C.PROVIDER,
          'if (p04PendingMatchesInstalledPackage(entry.app, pending, installedInfo)) {',
          'if (true) {')

    def test_07_cannot_drop_multi_listing_lookup(self):
        self.mutate(C.PROVIDER, 'final listingKeys = apps.values', 'final listingKeys = apps.entries')

    def test_08_cannot_drop_android_package_scope(self):
        self.mutate(C.PROVIDER, 'installedInfo.packageName != packageName',
                    'false')

    def test_09_cannot_drop_install_observation_fallback(self):
        self.mutate(C.PROVIDER,
          'getCorrectedInstallStatusAppIfPossible(\n          entry.app, installedInfo,\n        )',
          'null')

    def test_10_cannot_omit_source_workflow_guard(self):
        self.mutate(C.SOURCE_CI,
          'run: python3 -B scripts/ci/r02f_p04_contract.py --check',
          'run: echo skipped')

    def test_11_cannot_claim_external_backend_qualified(self):
        self.mutate(C.DOC, '**NOT_QUALIFIED** for real external',
                    '**PASS** for real external')

    def test_12_cannot_delete_stale_v1_test(self):
        self.mutate(C.DART_TEST,
          'stale v1 package broadcast cannot confirm the requested v2',
          'stale version accepted')

    def test_13_cannot_delete_target_package_test(self):
        self.mutate(C.DART_TEST,
          'same version number from another package cannot confirm',
          'different package accepted')

if __name__ == '__main__':
    unittest.main()
