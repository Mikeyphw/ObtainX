# ObtainX R02F P04B P01 — actual external declined handoff

This milestone wires a test-only, signed **unprivileged** Android external target
into the existing production `installApkViaThirdParty`/ACTION_VIEW bridge.
The target reads the exact downloaded signed v2 APK through ObtainX's granted
`content://` URI, hashes it and **declines**. The host separately verifies that
signed v1 package version and base APK SHA-256 remain unchanged. The receiver
is disposable, debuggable only in the emulator, and neither requests nor calls
Android PackageInstaller. The fixture signing key is generated on the GitHub
runner and deleted immediately after use; no APK or key is uploaded.

Source/Dart/Python tests alone are **NOT_QUALIFIED** as runtime evidence. The
hosted API36 test must actually pass, publish a bounded source-bound receipt,
and pass the independent post-emulator receipt verification before marking the
**decline-path** positive. Any broadcast/timeout/bridge boolean alone remains
unverified handoff, never installation success.

**NOT_QUALIFIED** for positive external installation: this test intentionally
does not approve or install v2. Also **NOT_QUALIFIED** for Shizuku or Dhizuku
privileged binder modes, physical-device acceptance, OEM approval flows,
background completion, or release. Do not extrapolate this negative to full P04.

Remaining P04B: positive signed v2 update with external target + Android approval,
late broadcasts, unrelated package/version probes, split archives and complete
provider pending-receipt reconciliation. Continue P05 device/OBB only after
explicitly documenting still-unqualified P04 variants.
