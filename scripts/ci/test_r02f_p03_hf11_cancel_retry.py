"""P03 HF11: bounded Android cancellation retry and failure-diagnostic contracts.

Source checks cannot substitute for real API36 PackageInstaller runtime evidence.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
NATIVE = 'android/app/src/main/kotlin/dev/imranr/obtainium/R02fP03SessionBridge.kt'
DART = 'integration_test/r02f_p03_app_cancel_test.dart'
DIAG = 'scripts/ci/r02f_p03_failure_diagnostics.py'
HOST = 'scripts/ci/r02f_p03_hosted.py'
PATHS = (NATIVE, DART, DIAG, HOST)


def inspect(inputs: dict[str, str]) -> list[str]:
    problems=[]
    def need(flag: bool, label: str):
        if not flag: problems.append(label)
    for f in PATHS:
        need(f in inputs, 'missing '+f)
    n=inputs.get(NATIVE,'')
    d=inputs.get(DART,'')
    h=inputs.get(HOST,'')
    c=inputs.get(DIAG,'')
    block=n.split('    private fun cancel(id: String?, reply: MethodChannel.Result) {',1)[-1].split('    private fun finish(',1)[0]
    need(block.count('for (attempt in 0 until 3) {') == 1, 'native retry count must be exactly three')
    need(block.count('installer.abandonSession(op.sessionId)') == 1, 'owned session abandon must be in loop')
    need(block.count('installer.getSessionInfo(op.sessionId) == null') >= 2, 'session absence must be checked twice')
    need(block.count('baselineStillProven(op)') == 2, 'native double baseline comparison missing')
    need('if (abandoned || !cancellationWindow) break' in block, 'retry escaped approval guard')
    need('if (attempt < 2)' in block and 'Thread.sleep(150L)' in block, 'settle delay unbounded/absent')
    need('val unchanged = unchangedBeforeSettle &&' in block, 'second baseline gate removed')
    need('if (abandoned && stillAbsent && unchanged && cancellationWindow)' in block, 'rollback success gate weakened')
    need('"cancelled"\n        } else "unknown"' in block, 'unknown outcome wrongly promoted to success')
    need('installer.abandonSession(op.sessionId)' in n.split('    private fun stage(',1)[-1], 'owned stage source changed')
    need("expect(terminal?['outcome'], 'cancelled'" in d, 'real Flutter terminal cancellation assertion missing')
    need("debugPrint('OX_P03_DART_STAGE=REAL_APP_PAGE_CANCEL_TAPPED')" in d, 'real AppPage tap proof missing')
    for label in ('UNKNOWN','ERROR','MISSING','UNEXPECTED'):
        need("'"+label+"'" in d and "('P03_NATIVE_TERMINAL_"+label+"', 'OX_P03_DART_NATIVE_TERMINAL="+label+"')" in c,
             'bounded terminal classifier missing '+label)
    need('final_stage = stage' in h and 'for marker, label in reversed(tuple(zip(MARKERS,' in h,
         'runner loses last milestone on fast exit')
    need('stage = final_stage\n            diag = write_failure(out, log, process.returncode, stage, source, runid)' in h,
         'diagnostic runner does not assign final milestone into protected stage argument')
    need('P03Handler.foreground_count == 1' in h and 'rt02c.baseline_v1(fixtures)' in h,
         'Android screen/source-bound evidence missing')
    need('return InstallResult.success()' not in n and 'install-abandon' not in n,
         'native shell or false success added')
    return problems


def read(root=ROOT) -> dict[str,str]:
    return {name:(root/name).read_text(encoding='utf-8') for name in PATHS}


class P03BoundedNativeCancellation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src=read()
    def test_00_original_sources_are_guarded(self):
        self.assertEqual(inspect(self.src),[])
    def mutate(self,path:str,old:str,new:str):
        self.assertEqual(self.src[path].count(old),1, 'mutation anchor not exact: '+old)
        changed=dict(self.src)
        changed[path]=changed[path].replace(old,new,1)
        self.assertTrue(inspect(changed),'unsafe mutation escaped '+old)
    def test_01_extra_abandon_retries_refused(self):
        self.mutate(NATIVE,'for (attempt in 0 until 3) {','for (attempt in 0 until 30) {')
    def test_02_no_abandon_retry_refused(self):
        self.mutate(NATIVE,'for (attempt in 0 until 3) {','for (attempt in 0 until 0) {')
    def test_03_abandon_call_removed_refused(self):
        self.mutate(NATIVE,'            try {\n                installer.abandonSession(op.sessionId)\n',
                           '            try {\n                println("no abandon")\n')
    def test_04_no_second_session_absence_refused(self):
        self.mutate(NATIVE,'        val stillAbsent = try { installer.getSessionInfo(op.sessionId) == null }',
                           '        val stillAbsent = true // unverified')
    def test_05_no_double_baseline_refused(self):
        self.mutate(NATIVE,'        val unchanged = unchangedBeforeSettle &&',
                           '        val unchanged = true || unchangedBeforeSettle &&')
    def test_06_suppress_baseline_condition_refused(self):
        self.mutate(NATIVE,'if (abandoned && stillAbsent && unchanged && cancellationWindow)',
                           'if (abandoned || stillAbsent || unchanged || cancellationWindow)')
    def test_07_retry_guard_removed_refused(self):
        self.mutate(NATIVE,'if (abandoned || !cancellationWindow) break',
                           'if (abandoned) break')
    def test_08_flutter_rollback_assertion_required(self):
        self.mutate(DART,"expect(terminal?['outcome'], 'cancelled'", "expect(terminal?['outcome'], isNotNull")
    def test_09_flutter_cancel_widget_required(self):
        self.mutate(DART,"debugPrint('OX_P03_DART_STAGE=REAL_APP_PAGE_CANCEL_TAPPED')",
                           "debugPrint('OX_P03_DART_STAGE=FAKE_TAP')")
    def test_10_terminal_unknown_cannot_be_hidden(self):
        self.mutate(DIAG,"('P03_NATIVE_TERMINAL_UNKNOWN', 'OX_P03_DART_NATIVE_TERMINAL=UNKNOWN')",
                         "('P03_NATIVE_TERMINAL_UNKNOWN', 'OX_P03_DART_NATIVE_TERMINAL=SUCCESS')")
    def test_11_terminal_missing_cannot_be_hidden(self):
        self.mutate(DIAG,"('P03_NATIVE_TERMINAL_MISSING', 'OX_P03_DART_NATIVE_TERMINAL=MISSING')",
                         "('P03_NATIVE_TERMINAL_MISSING', 'OX_P03_DART_NATIVE_TERMINAL=SUCCESS')")
    def test_12_runner_must_use_final_milestone(self):
        self.mutate(HOST,'stage = final_stage\n            diag = write_failure',
                         'stage = stage\n            diag = write_failure')
    def test_13_diagnostic_allowlist_is_fixed(self):
        spec=importlib.util.spec_from_file_location('p03_hf11_diag_under_test',ROOT/DIAG)
        self.assertIsNotNone(spec)
        mod=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        s='OX_P03_DART_NATIVE_TERMINAL=UNKNOWN\nNative abandon and original APK integrity must be established\n'
        d=mod.classify(s,1,'UI_CANCEL_TAPPED','a'*40,'12345',s.encode())
        self.assertIn('P03_NATIVE_TERMINAL_UNKNOWN',d['failure_categories'])
        self.assertEqual(d['last_runner_stage'],'UI_CANCEL_TAPPED')
        self.assertFalse(d['android_live_audit_passed'])
        self.assertFalse(d['release_qualified'])
        self.assertNotIn('org.example',str(d))
    def test_14_error_outcomes_are_distinct(self):
        spec=importlib.util.spec_from_file_location('p03_hf11_diag_under_test',ROOT/DIAG)
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        for status in ('ERROR','MISSING','UNEXPECTED'):
            txt='OX_P03_DART_NATIVE_TERMINAL='+status
            out=mod.classify(txt,1,'UI_CANCEL_TAPPED','b'*40,'12345',txt.encode())
            self.assertIn('P03_NATIVE_TERMINAL_'+status,out['failure_categories'])
            self.assertFalse(out['android_live_audit_passed'])

    def test_15_runner_cannot_bypass_protected_diagnostic_source_anchor(self):
        self.mutate(HOST,
          'write_failure(out, log, process.returncode, stage, source, runid)',
          'write_failure(out, log, process.returncode, final_stage, source, runid)')

if __name__=='__main__': unittest.main()
