# ObtainX OPT05 P01 — RT02B single Flutter session

This is a source-pinned CI performance experiment on a disposable Android 16
(API 36) emulator. It is **not** physical-device, complete R02, release, or
publication qualification.

## Changes

The RT02B hosted Python runner invokes `flutter test` **exactly once** using
`integration_test/r02b_rejection_test.dart` and two distinct immutable fixture
SHA-256 values in Dart defines. The Dart test checks each downloaded signed
fixture's digest, uses production `StockInstaller`, requires an error for the
unsafe update, and emits ordered case-tagged evidence markers.

The host always stages the same independently checked signed v2 fixture before
testing. Its HTTP acknowledgment endpoint remains unacknowledged until the host
has re-read Android PackageManager state, checked the exact SHA-256 of the
installed `/data/app/.../base.apk`, and verified package version 2. The first
case's host acknowledgment is a mandatory barrier before the second case can
begin. Both rejection cases are verified separately. A missing, duplicate,
reordered or unexpected marker fails the run.

The real system installer UI is probed **only after** the corresponding Dart
production `StockInstaller` call. Each case permits at most one confirmed tap
of the OS installer UI; no blind coordinates or simulated installer results.
The host refuses unexpected source/fixture digests, missing installed app,
interrupted test sessions, invalid timestamps and receipts.

The receipt has schema 2 and requires `flutter_launches=1`, the exact
acknowledgment order, one session log SHA-256 and two distinct package-state
proofs bound to the same session. Raw Flutter logs remain private to the hosted
runner. The existing workflow still runs `r02_rt02b_hosted.py run` and an
independent `verify` command, so other R02 lanes remain untouched.

## Acceptance

Run the complete local Python repository suite, R00 and RT02B source contracts,
Flutter analyzer and hosted API36 real installer acceptance. Success can only
be claimed after the current source SHA has six qualifying green workflows.
Compare runner duration with OPT04 baseline RT02B **442 seconds**, and verify
both rejection scenarios and one Flutter launch in the current RT02B receipt.

This OPT05 P01 overlay makes no RT02 standalone/split changes; those are
reserved for a separate, independently qualified P02.
