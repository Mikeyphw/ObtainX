# R02 RT01 — API 36 Hosted Emulator Bootstrap

This is **NOT a split-install E2E qualification**. It is a source-pinned first
stage to establish reproducible Android 16 emulator boot and actual ObtainX
debug APK installation, installed APK bytes, native MainActivity start, stable
running process and screenshot evidence. It does not exercise the Flutter
installer flow, split APK application, OBB handoff, user consent, cancellation,
or failure recovery through ObtainX.

## Trusted emulator reference

Source reference: `Mikeyphw/Cinderbox-Companion`, especially
`.github/workflows/r48-real-activity-acceptance.yml` and
`scripts/devtool/r48_emulator_ci.sh`. Reuse only its proven hosted Linux
KVM + ReactiveCircus pinned API 36 x86_64/Google APIs configuration, with
SDK provision and disk preflight; do not copy game-specific tests.

ObtainX R02 certified source parent: `dd297f3e0e503e1a1b59b0ce2a0b629e05808204`,
R02 source and Flutter CI runs `42872288443` and `42872288271` (success).
R01 base remains `3a57cfdced5940d3cdebd2396ba9c86c21d4926c`.

## R00 default-deny workflow inventory

The R00 source contract retains its strict `EXPECTED_WORKFLOWS` allowlist and
explicitly admits only `obtainx-r02-api36.yml` in addition to the two
previously reviewed workflows. The original read-only permission, 40-character
pinned action, no release/write and unexpected workflow checks remain mandatory.
Updated R00 regression tests prove that the new workflow is required and that
unreviewed workflows, mutable actions and release commands are still rejected.
This is an additive control, **not** a wildcard or a relaxation of R00.

## Qualification and evidence boundaries

- Only `ubuntu-24.04` with `/dev/kvm`, `Android 36`, x86_64, Google APIs,
  Flutter `3.47.6`, and ephemeral `emulator-5554` are permitted.
- Only `flutter build apk --debug --flavor normal --no-pub` is built.
  No production signing credentials, public releases, merges or packages from
  external mirrors are accessed.
- Require `dev.bikram.obtainx.debug` as the package ID, verify the debug APK's
  cert, refuse a preinstalled copy, install it, compare the installed base APK
  SHA-256 to the exact built artifact, launch `MainActivity`, check its process
  remains alive, and capture one app screenshot. The image is **evidence, not
  a visual acceptance test**.
- Initialize a fail-closed NOT_RUN JSON receipt before provisioning. Allowlist
  only `receipt.json` and `app_launch.png` in upload, with run SHA/ID binding.
- Receipt fields explicitly mark physical device, ObtainX-driven split E2E,
  release and publication qualification as **false**, even when emulator boot
  succeeds. Workflow remains red on any missing evidence.
- Source and mutation tests prohibit silent substitutions of emulator ABI/API,
  physical device fallback, loss of APK identity/byte proof, and premature
  claims of R02 full runtime acceptance.

## Next R02 RT02 gate

Add controlled, signed lab APK plus real base/config split inventory on the
emulator. Drive installation through ObtainX's own session APIs and capture
Android PackageManager installed splitNames, status, consent and cleanup. Do
not label R02 fully runtime-qualified until that follow-up E2E gate succeeds.
