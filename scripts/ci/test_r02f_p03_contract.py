"""Adversarial source mutations: never substitute source tests for Android."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('r02f_p03_contract', ROOT/'scripts/ci/r02f_p03_contract.py')
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)

class R02FP03ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clean = {path:(ROOT/path).read_text(encoding='utf-8') for path in contract.RULES}

    def test_base_contract(self):
        contract.verify_sources(self.clean)

    def deny(self, name, old, new, path):
        changed=dict(self.clean)
        self.assertIn(old, changed[path], 'mutation target missing: '+name)
        changed[path]=changed[path].replace(old,new,1)
        with self.assertRaises(ValueError, msg='mutant not rejected: '+name):
            contract.verify_sources(changed)

    def test_no_stale_owner_bypass(self):
        self.deny('identity', 'if (!identical(_gates[gate.listingKey], gate)) return false;',
                  'if (false) return false;', 'lib/services/install_precommit_gate.dart')

    def test_no_native_session_escape(self):
        self.deny('abandon', 'installer.abandonSession(op.sessionId)',
                  '// suppressed', 'android/app/src/main/kotlin/dev/imranr/obtainium/R02fP03SessionBridge.kt')

    def test_no_false_cancel_without_signed_baseline(self):
        self.deny('apk digest', 'baselineStillProven(op)', 'true',
                  'android/app/src/main/kotlin/dev/imranr/obtainium/R02fP03SessionBridge.kt')

    def test_no_missing_real_ui_tap(self):
        self.deny('tap', 'await tester.tap(realCancel)',
                  '// test only pretends tap', 'integration_test/r02f_p03_app_cancel_test.dart')

    def test_no_synthetic_test_screen(self):
        self.deny('real AppPage', 'MaterialApp(home: AppPage(appId: app.listingKey))',
                  'MaterialApp(home: Scaffold())',
                  'integration_test/r02f_p03_app_cancel_test.dart')

    def test_no_direct_installer_bypass(self):
        self.deny('provider installation', 'provider.installApk(',
                  'StockInstaller(SettingsProvider()).installApk(',
                  'integration_test/r02f_p03_app_cancel_test.dart')

    def test_no_ignored_orphan_callback(self):
        self.deny('orphan recovery', 'RESTART_ORPHAN_ANDROID_STATUS_',
                  'IGNORED_ORPHAN_STATUS_',
                  'android/app/src/main/kotlin/dev/imranr/obtainium/R02fP03SessionBridge.kt')

    def test_no_unverified_native_apk_original(self):
        self.deny('unreadable baseline', 'ORIGINAL_APK_BYTES_UNREADABLE',
                  'UNREADABLE_BASELINE_IGNORED',
                  'android/app/src/main/kotlin/dev/imranr/obtainium/R02fP03SessionBridge.kt')

    def test_no_host_only_abandon(self):
        path='scripts/ci/r02f_p03_hosted.py'
        changed=dict(self.clean)
        changed[path] += "\nbase.adb('shell','input','keyevent','4')\n"
        with self.assertRaises(ValueError): contract.verify_sources(changed)

    def test_no_runtime_gate_drop(self):
        self.deny('host runtime', 'python3 -B scripts/ci/r02f_p03_hosted.py run',
                  '# omitted', '.github/workflows/obtainx-r02-rt02c.yml')

    def test_no_independent_android_receipt_drop(self):
        self.deny('independent receipt', 'python3 -B scripts/ci/r02f_p03_hosted.py verify',
                  '# omitted', '.github/workflows/obtainx-r02-rt02c.yml')

    def test_no_external_installer_receives_non_serializable_owner(self):
        self.deny('stock-only token',
                  "if (activeInstaller.modeKey == 'system' && preparationGate != null)",
                  'if (true)', 'lib/providers/apps_provider_install.dart')

    def test_no_background_stock_replacement(self):
        self.deny('legacy plugin path', 'AndroidPackageInstaller.installApk(',
                  'NotNativeInstaller.installApk(', 'lib/installers/stock_installer.dart')

    def test_no_missing_archive_owner(self):
        self.deny('nested archive', 'preparationGate: preparationGate,',
                  '// removed', 'lib/providers/apps_provider_install.dart')

    def test_no_cross_listing_cancel(self):
        self.deny('listing key', "'listingKey': owner.listingKey",
                  "'listingKey': appId", 'lib/installers/r02f_p03_cancellable_stock.dart')

if __name__ == '__main__': unittest.main()
