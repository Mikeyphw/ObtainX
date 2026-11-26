# R07 — Activity Center: operational scope and acceptance

**Baseline:** ObtainX `main` `181191cc9a09c9c3053d837a3dfb24e9d98bafa0`, tree `2f409c11f02e1698dc5619d0555015a6e3957e0a`, following merged PR #29.

## Source architecture

R07 is a read-only Activity Center derived from the existing R03 persisted chunk/download records and the existing R05 single-attempt installation journal. It **does not create a competing database or introduce a second install-success authority**. Only R05 independently verified Android package/version/signature evidence can authorize confirmed installation. The R03 final digest is proof only of a download's file integrity, never of an install. In-memory update-check/download progress is shown separately from durable historical records and never persisted as success.

The old R05 activity-page implementation is retired (keeping its extra approval preference tile). The new page is reachable in the main navigation and in Settings and R06 app details. Review, Resume, Retry, Cancel, Open and Details actions are gated against stage, exact listing, active state and independent installed-package checks. Each notification carries the exact R05 attempt identifier and routes to that specific record. Cold starts and warm taps use the existing NotificationsProvider; no hidden background worker is added.

## Safety and explicit limitations

- R03 journal filenames carry an origin-and-header fingerprint rather than an explicit listing ID. The projection **refuses ambiguous cross-listing associations**. A source that cannot be associated gets a read-only details card, not a dangerous Retry/Cancel button.
- A pending R05 operation is only recovered by the existing app startup hook. Opening/refreshing R07 does **not** treat a currently active operation as interrupted.
- Android-owned approval tokens cannot always be recreated after process death. Review can reconcile the original attempt against Android; if not independently confirmable, it remains unknown/handed off, and the user may explicitly start a **new** attempt. A notification is not itself a resumed Android PendingIntent.
- Source-check counts are shown as unknown when only the live provider batch guard is available. Native scheduling remains subject to Android OS restrictions; no promise is made of unrestricted background checks.
- Unknown transfer totals are indeterminate. A displayed quantitative 100% requires the R03 finalized download digest. No 100% display implies installed-package confirmation.
- Read-only journal errors (unsafe symlink, malformed/untrusted file or oversize) are visible and **never silently deleted**.

## Regressions

R07 source contract and adversarial mutations: `python3 -B scripts/ci/r07_contract.py --check` and `python3 -B -m unittest scripts.ci.test_r07_contract`. Flutter: `flutter test --no-pub test/r07_activity_center_test.dart` (hosted only). Existing R05 confirmation, R03 download-engine tests and R02 legacy recovery hooks must remain green; all six required hosted workflows including API36 real-installer, negative and archive scenarios remain necessary. CI24 remains separate.

**Device/runtime, accessibility large-text/TalkBack, notification tap, real Android approval, physical installer, CI24 and signed release acceptance:** `NOT_QUALIFIED` until independently observed on the final source SHA. Source-only contract success must not be promoted to those gates.

## R07-F01: workflow registration correction

PR #30 at `840f2c7eab4838c2b536649b433945c90b3d0bbe` contained two malformed YAML step insertions. Repair preserves the R05 journal and R06 contract steps, installs structural YAML and duplicate-key validation for all six required workflows, and retains all hosted CI requirements. The three installer lanes additionally stopped on four fatal analyzer-info findings in the new R07 Dart files; brace the three multi-line/guarded statements and use an initializing formal for the existing testingRoot argument, preserving callers and behavior. Local native validation is targeted to the workflow guard, R07 negative fixtures and affected R07/R05/R06 and CI policy contracts. Source repair does not attest hosted CI, CI24, Android runtime or release.

## R07-F02: real journal widget-test synchronization

On PR #30 head `6c146dda3e6914190badbae074c4f51f3a5808cd`, five required workflows succeeded. Hosted Flutter run 45396187724 failed one of 17 R07 tests: the empty view was asserted after a simulated 250ms delay, without awaiting real disk I/O. The test now runs actual catalog I/O in the real asynchronous zone, awaits the first request with a bounded deadline, renders completion and disposes the refresh timer. The original empty-state assertion remains, and an additional two-receipt fixture verifies exact operation routing and absent unsafe actions. No production behavior or hosted qualification gate changed. Fresh hosted evidence is required.

## GAP-05 — Localized controls and queued automation

Activity Center presents localized status and evidence explanations. Filters wrap at large text sizes, action targets are padded to at least 48 logical pixels, and review remains accessible without gestures. Raw diagnostic evidence remains in Details. Automation may enqueue an exact download intent only; explicit continuation revalidates listing, release and eligibility. A failed queued cancellation is reported as a failure rather than a successful cancellation request.
