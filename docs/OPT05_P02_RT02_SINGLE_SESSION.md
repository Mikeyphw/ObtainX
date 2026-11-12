# ObtainX OPT05 P02 — RT02 real APK + split update in one Flutter session

Source-pinned to PR #11 and its exact pre-P02 commit. This is an optimization of
**hosted Android 16 / API36 emulator acceptance** only, not full R02 matrix,
physical-device, security or release qualification. **No releases. No merges.**

The original RT02 regression helper `one_scenario` is retained for HF06 pre-Dart
failure test compatibility but is NOT invoked by runtime qualification.
`r02_rt02_hosted.py run` instead executes `run_single_session` with one `flutter
test` of `integration_test/r02_opt05_single_session_test.dart`. The two actual
production StockInstaller calls remain distinct and sequential:

1. Fresh signed `base_v1.apk` installation, with exactly one observed and
   verified Android system Install dialog approval, versionCode 1, one installed
   base path, and exact SHA-256 of the generated signed fixture.
2. Signed `base_v2.apk` + `config.x86_64.apk` update, versionCode 2, two
   installed APK paths and exact signed-byte SHA-256 proof. The update may use
   zero observed dialogs ONLY when Android independently proves that the update
   was committed; one real dialog is also valid.

Each case emits an ordered `START`, `INSTALL_CALL`, `INSTALL_RETURNED`, `ACKED`
Dart event. The Dart test blocks between the cases on `/ack/<scenario>` over
ADB-reversed localhost HTTP. The host grants an ack **only after** independent
package manager hash/version/split verification and proper approval classification.
Duplicated, missing or reordered events are refused. The Dart test is not retried
after installer activity. On any failure, only bounded categories and private
log SHA may be recorded; raw Flutter logs are never uploaded to CI artifacts.

Receipt schema 2 includes source SHA, workflow run ID, one Flutter launch,
ordered host acknowledgements, exact Dart event sequence, the single ephemeral
log digest and two source-bound installed package-state proofs. Admission fields
for release, full R02 matrix, physical device and publication remain false.

Hosted acceptance requires: all Python source/mutation gates, Flutter analysis,
real KVM API36 emulator, the one Flutter test PASS, both actual Android transitions,
independent receipt verification and all six existing workflows green.
Only after successful hosted qualification should durations be compared to the
previous RT02 runner baseline of 519 seconds. CI runtime variance exists.
