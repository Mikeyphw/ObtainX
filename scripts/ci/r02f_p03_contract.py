#!/usr/bin/env python3
"""R02F P03 exact-source cancellation security and hosted-runtime gate.

Textual structure tests are NOT runtime qualification. The hosted Android job
must independently run integration_test/r02f_p03_app_cancel_test.dart and verify
APK version+bytes. This contract refuses deletion of that runner/receipt gate.
"""
from __future__ import annotations
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RULES = {
    'lib/services/install_precommit_gate.dart': (
        'bool get canCancel => !_cancelRequested && !_finished &&',
        'bool sealForHandoff({bool nativeCancelable = false})',
        'if (!identical(_gates[gate.listingKey], gate)) return false;',
        'listener();',
        'bool get nativeCancelable => _nativeCancelable;',
    ),
    'lib/installers/r02f_p03_cancellable_stock.dart': (
        "'stage'", "'commit'", "'cancel'", "'pending'",
        'owner.addCancelListener(onCancel)',
        'Future<Map<dynamic, dynamic>?> cancelOnce()',
        'owner.finish();',
        'owner.wasCancelled',
        'return InstallResult.handedOff();',
        "'listingKey': owner.listingKey",
    ),
    'lib/installers/stock_installer.dart': (
        "owner is InstallPrecommitGate && owner.nativeCancelable",
        'R02fP03CancellableStock.instance.install(',
        'AndroidPackageInstaller.installApk(',
    ),
    'lib/providers/apps_provider.dart': (
        'final InstallPrecommitRegistry _installPrecommit',
        'recoveredNativeInstallIds',
        'uncertainNativeInstallListings',
        'isNativeInstallOutcomeUncertain(String listingKey)',
        '_installPrecommit.requestCancel(listingKey)',
        'R02fP03CancellableStock.instance.cancelRecovered(id)',
        '_installPrecommit.sealForHandoff(gate,',
        'Future<void> recoverNativeInstallSessions() async',
        'InstallReleaseSnapshot.fromJson(',
        'discardPendingInstall(entry.app, pending)',
    ),
    'lib/providers/apps_provider_install.dart': (
        'InstallPrecommitGate? preparationGate,',
        'nativeCancelable: activeInstaller.modeKey == \'system\'',
        "if (activeInstaller.modeKey == 'system' && preparationGate != null)",
        "'r02fP03Gate': preparationGate",
        'preparationGate: preparationGate,',
        'preparationGate: installPreparationGate,',
        'endInstallPreparation(id, installPreparationGate);',
        'unawaited(recoverNativeInstallSessions());',
        "if (getInstaller().modeKey == 'external')",
        'element.downloadProgress != _recoveredNativeInstallSentinel',
    ),
    'lib/providers/apps_provider_lifecycle.dart': (
        'if (singleId == null) unawaited(recoverNativeInstallSessions());',
    ),
    'lib/pages/app.dart': (
        "import 'package:obtainium/widgets/r02f_p03_cancel_button.dart';",
        'R02fP03CancelButton(',
        'canCancelInstallPreparation(appId)',
        'isNativeInstallOutcomeUncertain(app.listingKey)',
    ),
    'lib/pages/apps.dart': (
        "import 'package:obtainium/widgets/r02f_p03_cancel_button.dart';",
        'R02fP03CancelButton(',
        'canCancelInstallPreparation(app.listingKey)',
    ),
    'lib/widgets/r02f_p03_cancel_button.dart': (
        'class R02fP03CancelButton extends StatelessWidget',
        "Key('p03-cancel-$listingKey')",
        '.cancelInstallPreparation(listingKey)',
    ),
    'android/app/src/main/kotlin/dev/imranr/obtainium/R02fP03SessionBridge.kt': (
        'class R02fP03SessionBridge(',
        'installer.createSession(params)',
        'installer.abandonSession(op.sessionId)',
        'session.commit(callback.intentSender)',
        'baselineStillProven(op)',
        'info.applicationInfo?.splitSourceDirs',
        'oldSha.length != 64 || oldSha != newSplits.optString(i, "")',
        'val outcome = if (abandoned && stillAbsent && unchanged && cancellationWindow)',
        'PendingIntent.FLAG_MUTABLE',
        'PREFS = "obtainx_r02f_p03_sessions"',
        'ORIGINAL_APK_BYTES_UNREADABLE',
        'RESTART_ORPHAN_ANDROID_STATUS_',
        'prefs.edit().remove("orphanStatus").commit()',
        'RESTART_SESSION_FINALIZED_UNOBSERVED',
        'op.cancelRequested = true',
    ),
    'android/app/src/main/kotlin/dev/imranr/obtainium/MainActivity.kt': (
        'R02fP03SessionBridge(this, flutterEngine.dartExecutor.binaryMessenger)',
        'r02fP03Bridge?.detach()',
    ),
    'android/app/src/main/AndroidManifest.xml': (
        'android:name=".R02fP03ResultReceiver"',
        'android:exported="false"',
    ),
    'integration_test/r02f_p03_app_cancel_test.dart': (
        'MaterialApp(home: AppPage(appId: app.listingKey))',
        'provider.installApk(',
        'preparationGate: owner',
        'final realCancel = find.byKey(cancelKey)',
        'await tester.tap(realCancel)',
        "pending['state'] == 'approval'",
        "expect(terminal?['outcome'], 'cancelled'",
        'OX_P03_DART_STAGE=APP_ROUTE_OWNER_SURVIVED',
        'OX_P03_DART_STAGE=PRODUCTION_PROVIDER_INSTALL_STARTED',
        'OX_P03_DART_STAGE=REAL_APP_PAGE_CANCEL_TAPPED',
    ),
    'scripts/ci/r02f_p03_hosted.py': (
        'base.host_check()',
        'write_failure(out, log, process.returncode, stage, source, runid)',
        'rt02c.baseline_v1(fixtures)',
        'P03Handler.foreground_count == 1',
        'integration_test/r02f_p03_app_cancel_test.dart',
        'native_session_abandoned_from_application',
        'before == after',
        'OX_R02F_P03_INDEPENDENT_ANDROID_UI_CANCEL_RECEIPT_PASS',
        'OX_R02F_P03_OFFLINE_SOURCE_BOUND_LIVE_AUDIT_RECEIPT_VERIFIED_PASS',
        'def audit(out: Path) -> int:',
        'def verify(out: Path) -> int:',
        'base.identity_check()',
        'r02f-p03-android-audit.json',
    ),
    'test/r02f_p03_precommit_gate_test.dart': (
        'user cancellation before platform handoff',
        'native pending-approval session remains cancellable',
        'an external handoff cannot be cancelled after sealing',
        'process restart never fabricates prior success',
    ),
    '.github/workflows/obtainx-r00-contracts.yml': (
        'scripts/ci/r02f_p03_contract.py --check',
    ),
    '.github/workflows/obtainx-r02-rt02c.yml': (
        'python3 -B scripts/ci/r02f_p03_hosted.py run',
        'python3 -B scripts/ci/r02f_p03_hosted.py verify',
        'python3 -B scripts/ci/r02f_p03_hosted.py audit',
        'r02f-p03-android-audit.json',
        'r02f-p03-app-ui-cancel.json',
        'r02f_p03_contract.py --check',
        'r02f_p02_session_abandon.py run',
        'r02g_incompatible_sdk_hosted.py run',
        'r02_rt02c_hosted.py run',
    ),
}


def ensure_live_audit_is_before_shutdown(workflow: str, hosted: str) -> None:
    import re
    runner = re.findall(r"(?m)^\s*script: bash -c '([^\n]*)'$", workflow)
    if len(runner) != 1:
        raise ValueError('OX_P03_REFUSED one pinned API36 emulator runner required')
    body = runner[0]
    order = [
        'scripts/ci/r02_rt02c_hosted.py run --out',
        'scripts/ci/r02f_p02_session_abandon.py run --out',
        'scripts/ci/r02g_incompatible_sdk_hosted.py run --out',
        'scripts/ci/r02f_p03_hosted.py run --out',
        'scripts/ci/r02f_p03_hosted.py audit --out',
    ]
    positions = [body.find(k) for k in order]
    if any(x < 0 for x in positions) or positions != sorted(positions):
        raise ValueError('OX_P03_REFUSED live Android audit must follow actual UI in same emulator')
    if body.count('scripts/ci/r02f_p03_hosted.py audit --out') != 1:
        raise ValueError('OX_P03_REFUSED missing or duplicated live emulator audit')
    outer = workflow.split('      - name: Independently verify archive-to-installer Android package-state receipts', 1)
    if len(outer) != 2:
        raise ValueError('OX_P03_REFUSED missing independent offline receipt gate')
    after = outer[1].split('      - name: Record only bounded receipt hashes before artifact upload', 1)
    if len(after) != 2 or after[0].count('scripts/ci/r02f_p03_hosted.py verify --out') != 1 or \
       'scripts/ci/r02f_p03_hosted.py audit --out' in after[0]:
        raise ValueError('OX_P03_REFUSED offline verifier must follow emulator teardown')
    if 'r02f-p03-android-audit.json' not in after[1]:
        raise ValueError('OX_P03_REFUSED separate live Android audit receipt not uploaded')
    parts = hosted.split('def audit(out: Path) -> int:', 1)
    if len(parts) != 2 or 'base.host_check()' not in parts[1].split('def verify(out: Path)',1)[0] or \
       "rt02c.baseline_v1(out/'fixtures')" not in parts[1].split('def verify(out: Path)',1)[0]:
        raise ValueError('OX_P03_REFUSED no independent live Android package-state query')
    tail = parts[1].split('def verify(out: Path) -> int:', 1)
    if len(tail) != 2 or 'base.identity_check()' not in tail[1] or \
       'base.host_check()' in tail[1] or 'rt02c.baseline_v1(' in tail[1] or 'base.adb(' in tail[1]:
        raise ValueError('OX_P03_REFUSED post-emulator verifier depends on live ADB')

def verify_sources(sources: dict[str,str]) -> None:
    for path, anchors in RULES.items():
        if path not in sources:
            raise ValueError('OX_P03_REFUSED missing file: '+path)
        for anchor in anchors:
            if anchor not in sources[path]:
                raise ValueError('OX_P03_REFUSED missing protected anchor: '+path+' '+anchor)
    provider=sources['lib/providers/apps_provider_install.dart']
    if provider.count('preparationGate: installPreparationGate,') != 2 or \
       provider.count('preparationGate: preparationGate,') != 1 or \
       provider.count('InstallPrecommitGate? preparationGate,') != 2:
        raise ValueError('OX_P03_REFUSED exact-listing token forwarding lost')
    if provider.count('if (!sealInstallHandoff(preparationGate,') != 1 or \
       provider.count('if (!sealInstallHandoff(preparationGate))') < 1:
        raise ValueError('OX_P03_REFUSED stock/external handoff gates drifted')
    if "result = await activeInstaller.installApk(" not in provider:
        raise ValueError('OX_P03_REFUSED owned native stock dispatch absent')
    # Abort if a new await was inserted between the guard and installer handoff.
    first=provider.index('if (!sealInstallHandoff(preparationGate,')
    call=provider.index('result = await activeInstaller.installApk(',first)
    if 'await ' in provider[first:call]:
        raise ValueError('OX_P03_REFUSED async gap between sealed owner and native call')
    native=sources['android/app/src/main/kotlin/dev/imranr/obtainium/R02fP03SessionBridge.kt']
    for banned in ('Runtime.getRuntime().exec(', 'su -c', 'shell pm ',
                   'install-abandon', 'STATUS_PENDING_USER_ACTION) {\n            finish(op, "success"'):
        if banned in native:
            raise ValueError('OX_P03_REFUSED unsupported privileged or false-success backend')
    integration=sources['integration_test/r02f_p03_app_cancel_test.dart']
    if 'StockInstaller(' in integration or 'R02fP03CancelButton(' in integration:
        raise ValueError('OX_P03_REFUSED synthetic UI or direct installer bypasses production provider/page')
    if 'await tester.tap(realCancel)' not in integration or \
       'MaterialApp(home: AppPage(appId: app.listingKey))' not in integration or \
       'provider.installApk(' not in integration:
        raise ValueError('OX_P03_REFUSED real production app/page/provider path missing')
    if 'PendingIntent.FLAG_MUTABLE' not in native:
        raise ValueError('OX_P03_REFUSED Android target SDK 35+ callback invalid')
    if 'ORIGINAL_APK_BYTES_UNREADABLE' not in native or \
       'RESTART_ORPHAN_ANDROID_STATUS_' not in native or \
       'cancellationWindow' not in native:
        raise ValueError('OX_P03_REFUSED unsafe native rollback or orphan recovery')
    if native.count('baselineStillProven(op)') != 3 or 'sourceDir' not in native:
        raise ValueError('OX_P03_REFUSED missing actual installed APK baseline check')
    hosted=sources['scripts/ci/r02f_p03_hosted.py']
    if "base.adb('shell','input','keyevent'" in hosted or "'install-abandon'" in hosted:
        # User taps the production widget. Do not substitute a host abandon.
        raise ValueError('OX_P03_REFUSED host substitutes Android-only abandon')
    workflow=sources['.github/workflows/obtainx-r02-rt02c.yml']
    if workflow.count('scripts/ci/r02f_p03_hosted.py run') != 1 or \
       workflow.count('scripts/ci/r02f_p03_hosted.py audit') != 1 or \
       workflow.count('scripts/ci/r02f_p03_hosted.py verify') != 1:
        raise ValueError('OX_P03_REFUSED missing/doubled hosted acceptance')
    ensure_live_audit_is_before_shutdown(workflow, hosted)
    print('OX_R02F_P03_APP_UI_NATIVE_SOURCE_AND_NEGATIVE_CONTRACT_PASS')


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument('--check',action='store_true',required=True)
    ap.parse_args()
    verify_sources({k:(ROOT/k).read_text(encoding='utf-8') for k in RULES})

if __name__=='__main__': main()
