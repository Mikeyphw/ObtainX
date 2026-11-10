# R02 RT02A — Hosted Android 16 genuine system installer acceptance

**Base commit:** `eee62aa6d0b6eadec5543d6ed0ee67e3fc57e373` (qualified RT01 HF04).

This additive lane uses the same API36 Google APIs x86_64 KVM provisioning as
`Mikeyphw/Cinderbox-Companion` and RT01. It executes **real** on-device Flutter
`integration_test` code that calls ObtainX's production `StockInstaller`, not
mocked platform methods or direct ADB installation of the fixture.

The hosted runner generates a fresh, time-limited CI-only signing identity and
three disposable fixture APKs: base version 1, base version 2, and a matching
x86_64 resource split version 2. The key is deleted immediately after signing.
The APK bytes never enter a release or CI artifact. The fixture is served only
through a localhost port reversed to the Android emulator. The device test checks
SHA-256 before use. The host validates the Android package installer UI target
label before clicking Install, then verifies package versionCode, split count
and exact installed APK SHA-256. Any missing approval, unexpected package,
unknown device, crash, timeout, test failure or hash mismatch remains red.

**Scope:** standalone first install and a base+configuration-split update using
production StockInstaller on Android 16. NOT full R02 runtime-matrix acceptance.
APKS/APKM/XAPK/ZIP/TAR container selection and import, alternate ABIs,
cancellation, signatures mismatches, rejected downgrades, external handoff,
Shizuku and Dhizuku remain **unqualified**. A green RT02A is not the same as
validating the complete user-facing download-to-install flow. Physical devices
and release builds remain unqualified.

No releases, No merges, no private signing material, and no Android permission
or installation confirmation bypass. Read-only GitHub credentials. Evidence
receipts are source- and run-ID-bound, fail closed by default, and upload only
`rt02-receipt.json` and `fixture_inventory.json` (no APK, private key,
raw device logs or screenshots). GitHub Actions runner builds and verifies.

Potential first CI incompatibilities: minimal AAPT2 configuration split parsing,
Android 16 UI wording, or Flutter integration-test registration. These must
remain red until resolved with source-pinned evidence and mutation tests.

### RT02A HF01 — Staged whitespace guard

- Corrected one trailing-whitespace-only line in `scripts/ci/r02_rt02_hosted.py`.
- The executable ZIP now checks whitespace for **all** payload files immediately after digest validation.
- The pre-commit audit stages all exact touched paths and runs `git diff --cached --check` before declaring the host contracts green.
- The self-test repeats this test inside a disposable Git repository, including newly added files. Installer code and security admission criteria are unchanged.

## HF02 hosted analyzer recovery (10 November 2026)

Run 42908393885 failed before emulator invocation: `flutter analyze integration_test lib test` rejected `r02_real_installer_test.dart:47` (`prefer_const_declarations`). The fixture selector is now `const version`, and RT02's strict source contract and mutation regression require that declaration. This is source-only recovery, **not** evidence of an Android install. The hosted RT02 workflow must rerun and pass both system-install sessions before RT02A can be qualified.

### RT02A HF03 — API36 split-manifest fixture recovery

The disposable `config.x86_64.apk` fixture now uses the native manifest
`split="config.x86_64"` identifier and **omits** `configForSplit` when targeting
its base APK. `android:configForSplit` is not an Android SDK namespaced
attribute and fails AAPT2 linking. Android's dependency loader implicitly
associates such a configuration split with the base package. The fixture
compiler runs before emulator startup, and its results remain temporary,
CI-only and signed with a freshly generated key deleted after use.

This is only a fixture-generation correction. It does not qualify the real
StockInstaller journeys, the full R02 matrix, signing for release, or a
physical device until the corresponding hosted acceptance receipts pass.
