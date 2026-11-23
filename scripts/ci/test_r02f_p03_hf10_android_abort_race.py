"""HF10 source guard: real callback race, byte proof, and no fake cancellation.

Static checks do not establish Android runtime acceptance. The existing
integration_test and real API36 workflow remain mandatory and unchanged.
"""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]

class RealCancelRaceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native=(ROOT/'android/app/src/main/kotlin/dev/imranr/obtainium/R02fP03SessionBridge.kt').read_text()
        cls.dart=(ROOT/'integration_test/r02f_p03_app_cancel_test.dart').read_text()
        cls.host=(ROOT/'scripts/ci/r02f_p03_hosted.py').read_text()

    def test_android_abort_requires_true_platform_status(self):
        self.assertIn('status == PackageInstaller.STATUS_FAILURE_ABORTED',self.native)
        self.assertIn('op.androidAbortObserved = true',self.native)
        self.assertIn('!it.cancelRequested',self.native)
        self.assertIn('ANDROID_ABORT_NO_USER_CANCEL',self.native)
        self.assertIn('}, 4000L)',self.native)

    def test_no_unverified_success_or_cancel(self):
        self.assertIn('val closureProven = abandoned || (androidAborted && stillAbsent)',self.native)
        self.assertIn('closureProven && stillAbsent && unchanged && cancellationWindow',self.native)
        self.assertIn('val unchangedBeforeSettle',self.native)
        self.assertIn('val unchanged = unchangedBeforeSettle &&',self.native)
        self.assertIn('baselineStillProven(op)',self.native)
        self.assertNotIn('finish(op, "cancelled", null)',self.native)

    def test_receipts_do_not_claim_native_abandon_on_android_abort(self):
        self.assertIn('closureProof',self.native)
        self.assertIn('originalBytesVerified',self.native)
        self.assertIn("expect(terminal?['originalBytesVerified'], isTrue",self.dart)
        self.assertIn('first_party != android_abort',self.host)
        self.assertIn("'android_abort_observed_before_cancel':android_abort",self.host)
        self.assertIn("'native_session_abandoned_from_application':first_party",self.host)

    def test_late_abort_after_cancel_is_not_generic_unknown(self):
        self.assertIn('if (op.cancelRequested) {', self.native)
        self.assertIn('worker.execute { reconcileLateAndroidAbort(op) }', self.native)
        self.assertIn('op.state != "approval" && op.state != "cancel_uncertain"', self.native)
        self.assertIn('cancelWindowAccepted', self.native)
        self.assertIn('absentBefore && absentAfter && unchangedBefore && unchangedAfter', self.native)
        self.assertIn('CANCEL_SETTLEMENT_UNPROVEN', self.native)
        self.assertIn('RESTART_SESSION_FINALIZED_UNOBSERVED', self.native)
        self.assertNotIn('op.state != "approval" || op.cancelRequested', self.native)

    def test_bounded_diagnostic_categories_only(self):
        self.assertIn('OX_P03_DART_CANCEL_DIAGNOSTIC=TERMINAL_UNKNOWN', self.dart)
        self.assertIn('OX_P03_DART_CANCEL_DIAGNOSTIC=TERMINAL_MISSING', self.dart)
        self.assertIn('OX_P03_DART_CANCEL_DIAGNOSTIC=TERMINAL_ERROR', self.dart)
        self.assertIn('OX_P03_DART_STAGE=APP_OWNED_CANCEL_RESULT_VERIFIED', self.dart)

    def test_original_real_android_acceptance_retained(self):
        self.assertIn('await tester.tap(realCancel)',self.dart)
        self.assertIn('provider.installApk(',self.dart)
        self.assertIn('rt02c.baseline_v1(fixtures)',self.host)
        self.assertIn('def audit(out: Path) -> int:',self.host)
        self.assertIn('def verify(out: Path) -> int:',self.host)

if __name__ == '__main__': unittest.main()
