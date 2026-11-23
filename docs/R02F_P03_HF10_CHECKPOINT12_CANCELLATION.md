# ObtainX R02 P03 HF10 — Checkpoint #12 cancellation race

Source baseline: `c003b16902f16c1f5fa841960b437b7bf07c867d` on `main`.
Original source must match the four Git blob preimages bound by the source operator.

## Observed reproducer

GitHub Actions run 45076519352, attempt 1 and 2, on exact above `main` SHA.
Step `Real Android archive update sessions and two extraction refusals` fails
within `r02f_p03_hosted.py` after the real Cancel widget is tapped. Observed
categories: `P03_NATIVE_ROLLBACK_UNPROVEN`, `P03_WIDGET_ASSERTION`; Dart markers
1–4 recorded; marker 5 absent. Other archive/negative cases passed.

## Production behavior changed

Android `STATUS_FAILURE_ABORTED` can arrive during return from its native
approval UI before the app-owned Cancel MethodChannel request reaches the
serialized session worker. Instead of prematurely clearing that journal, hold
it for at most 4 seconds to allow a real app cancellation request. For closure
already performed by Android, recognize ONLY the matching, observed abort
status and independently verified session absence and two installed APK byte
observations. For closure performed by ObtainX, retain independent abandon and
byte checks. No Cancel within the deadline ends `unknown`, never `cancelled`.

The durable terminal carries `closureProof` (`native_abandon` or
`android_abort`) and `originalBytesVerified`. The live Flutter integration test
and hosted receipt distinguish those cases: `native_session_abandoned_from_application`
versus `android_abort_observed_before_cancel` are exclusive booleans, never both.
The native-Android origin is never mislabeled as an ObtainX-native abandon.

## HF11 regression: post-Cancel STATUS_FAILURE_ABORTED (23 November 2026)

PR #27 source `1fb0801dea7b0e07da3d08abdbcb578c7baf3b1b` still fails
RT02C run `45165996590` at the real production AppPage Cancel assertion.
The callback previously ignored `STATUS_FAILURE_ABORTED` when Cancel was already
requested; it took the generic terminal UNKNOWN path instead of independently
checking that Android closed the exact session while original signed APKs
remained unchanged. This revision preserves the durable accepted-cancel window,
reconciles a later matching abort, enforces session absence before/after
settling and two original-byte observations, and resolves uncertain sessions to
UNKNOWN on a bounded deadline. It does not turn Android status into install
success or count a user cancellation when the UI was never tapped.

The Dart integration test emits fixed allowlisted categories only for failure
triage. No raw Flutter logs or device/package inventory are published. Full
API36 hosted acceptance is still required at the new exact PR head.

## Required acceptance (NOT YET ATTESTED)

- Native Devtool source-bound validation, apply, committed session, delivered PR.
- All preexisting source/negative tests and the new HF10 source guards.
- Exact-head required hosted CI and API36 RT02C live runtime (not only mocks).
- After hotfix merge, requalify six workflow-dispatch checks on exact new main.
- Device and release qualification are separate and remain pending.

No force push, test skip, branch protection override, or false-pass fallback.
The remaining PRs #13–#26 must be reviewed for compatibility after main changes.
