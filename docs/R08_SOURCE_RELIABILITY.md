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
