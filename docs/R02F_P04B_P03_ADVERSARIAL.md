# ObtainX R02F P04B P03 — native external installer adversarial acceptance

Source base: PR #19, `5fe3639844f2c1c0f210c12acb433fd0b92472ed`.

**NOT_QUALIFIED until the P03 source tests and all six exact-HEAD hosted workflows pass.**
The verified P02 Android positive path is retained unchanged. P03 covers hostile
negative events; it does not grant physical, privileged, Shizuku, Dhizuku or
release acceptance.

## Scenarios and actual proof

1. **Overlapping native handoffs:** the production `MainActivity` refuses a
   second `launchInstallIntent` with `INSTALL_IN_PROGRESS` **before** copying
   files, preserving the first watcher, its dynamic receiver and cache ownership.
   A signed disposable delayed-decline target keeps the first handoff pending
   long enough for a second real Flutter-to-Kotlin call.
2. **Untrusted broadcast:** the host sends a custom, unprotected Android
   broadcast carrying the correct package URI while the native watcher is
   active. This must not be confused with an Android-protected
   `ACTION_PACKAGE_REPLACED` broadcast or a verified installation.
3. **Late event:** the same custom signal is delivered after the first handoff
   finishes and before a new handoff, confirming no stale event is promoted.
4. **Mismatched expected package/version:** a second real external decline
   handoff expects a deliberately incorrect package name, and the independent
   Android PackageManager check still finds exactly the original signed v1
   fixture, rather than the source-bound signed v2. The unverified Dart bridge
   classifier MUST NOT report success, even for a `true` broadcast signal.

The target is compiled and signed **only on the disposable GitHub-hosted API36
emulator**. It reads the signed APK through the production FileProvider and
always declines; no PackageInstaller session is committed in P03. No `pm
install` bypass occurs in Dart; the host installs only disposable baseline
fixtures and the signed nonprivileged test target.

## Fail-closed acceptance

The real Flutter integration run must produce four distinct, unique milestone
markers, two executed custom spoof probes, a platform `INSTALL_IN_PROGRESS`
refusal, and two unverified decline handoffs. Android's signed v1 `base.apk`
SHA256 and versionCode must be identical before/after. The disposable target
must show that it actually read the SHA-bound signed v2 file. A bounded receipt
with exact source SHA and Actions run ID is independently rehashed offline,
including the privately retained Flutter log. On failure only a classified
refusal JSON may be uploaded; raw Flutter logs, APK bytes, signing material,
private shared preferences and screen XML remain in the ephemeral runner.

P03 cannot qualify Android positive installation on its own; P02's separate
`STATUS_SUCCESS`, real verified user-approval tap, exact signed-v2 bytes and
independent receipt remain mandatory in the **same RT02C workflow**. All six
exact-HEAD workflows must pass for scoped hosted acceptance.

## Remaining roadmap

After P03: R02F P04 backend availability/refusal matrix for Shizuku/Dhizuku
(with explicit authorization and NOT_AVAILABLE ≠ PASS); R02F P05 OBB + ABI,
locale, density and minSdk compatibility and physical read-only preflight;
R02F P06 real user-facing archive import/cancel; dependency-ordered review of
stacked PRs (no automatic merge); R03 durable resumable downloads; R04 GitHub
Actions artifact source; R05 transactional lifecycle; R06 app detail/version;
R07 Activity Center; R08 source/version reliability; R09 discovery/picker;
R10 settings/accessibility; R11 integrations/history; R12 full release and
security/physical qualification. R00/R01 audits remain continuous.
