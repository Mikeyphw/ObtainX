# R08 — Source reliability, version engine and issue regression fixes

Predecessor: green R07-F02 `e008f52b7d1f801a0f27c73dafccead3dc701f02`,
PR #30. Preserve this historical CI evidence; new source requires fresh native
and hosted validation. No merge, release, or device acceptance is asserted.

| Promise / issue | Source change | Remaining proof |
|---|---|---|
| R08-P01 #336 | Mozilla aN/bN parsing in the shared comparison engine | Hosted ordering/regression test |
| R08-P02 #353 | Asset labels only; APK regex sheet previews kept samples with inversion | Hosted filtering test and interactive preview/device check |
| R08-P03 #363 | Shared compatible ARM64 preference, generic filtering and F-Droid metadata | Hosted fixture and real device ABI selection |
| R08-P04 #347 | Exact matching acknowledgement before versionCode tie-break; retain installed version and newer guard | Hosted receipt/source change regression |
| R08-P05 #339 | Per-isolate serialized request pacing (2s), bounded queue, server cooldown, session coalescing, no repeated unchanged listing HTML; bounded optional size walk | PARTIAL: no multi-isolate or live-provider request-volume evidence |
| R08-P06 #333 #345 #357 | APKCombo single variant fallback; safe HTTPS asset parsing; Farsroid query encoding/shape; RuStore 419 diagnostic and refusal of incomplete split response | PARTIAL: no supported RuStore session solution, live Farsroid root cause and service behavior unverified |
| R08-P07 #368 | Decode outer link once; preserve inner URL, reject ambiguous/non-web links, exact-event deduplication, serialized warm routing | Hosted parsing tests and Android cold/warm routing acceptance |

All named regressions live in `test/r08_source_regressions_test.dart` and the
existing mandatory Flutter workflow runs them. Local source-contract validation
is targeted, not a substitute for hosted Flutter. The APKMirror guard is
isolate-local and intentionally does not bypass access controls. RuStore 419
is NOT a provider-session repair: do not copy extracted credentials or silently
install a single split. Farsroid's actual current service failure remains open.
The existing source identity and install evidence checks remain authoritative.

R07 persistent check/extraction/scan history, per-source counts, Android
approval/notification after process death and background recovery still need
acceptance. CI24, physical-device tests and signed release are independent.

## R08-F03 / RT02C-HF10 failure remediation

The legacy SourceProvider URL-matching expectation conflicted with the #353
filename-only policy. The replacement covers URL-only refusal, inversion,
filename matching, and empty pattern; the APK preview shares `filterApks`.

RT02C run 45459045944 had zero completed cases and zero confirmed taps at
`STOCK_INSTALLER_CALL`. Its former `GRADLE_BUILD_FAILED` diagnostic was not
proof of a Gradle failure. The repair uses phase-specific error categories,
unique fresh uncompressed hierarchy dumps, checked cleanup, bounded approval
observations and read-only signed-package state evidence before fixture cleanup.
Neither a tap attempt nor a package observation replaces the test's required
seven-case and independent receipt checks. The actual cause of the prior stall
remains open pending a new hosted run; no physical-device or release acceptance.

RT02C now probes the hierarchy outside the session state lock, then rechecks
the active case and boundary index under lock immediately before the bounded
input mutation. A late probe cannot approve or pollute a later case. Installer
identity and action must be in the same allowlisted system UI. All six CI
workflows pin checkout, evidence and cache identities to the PR head via
OX_EXPECTED_SHA (or the actual event commit outside PRs); structural regressions
cover synthetic merge substitution, unbound artifacts and conditional guards.

## FINAL-AUDIT-03 — approved F06 limit

The public Farsroid format change is addressed in the source parser and deterministic fixtures. Current-format malformed metadata refuses rather than falling back. Live provider acceptance remains pending. RuStore unsupported authentication is explicitly accepted; no extracted official-client credentials are used. APKMirror access-control refusal and shared pacing are preserved. See `FINAL_AUDIT_03_TRUST.md`.
