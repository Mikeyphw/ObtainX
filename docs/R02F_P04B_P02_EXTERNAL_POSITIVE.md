# ObtainX P04B P02 — disposable external installer positive-path acceptance

Stacked on P04B P01 (external ACTION_VIEW receiver decline). Adds an independent
signed disposable positive target. An Android PackageInstaller session and
**actual user approval in a hosted API 36 emulator** must precede external update
qualification; a Dart bridge boolean or package-change broadcast never suffice.

Expected strict sequence: source-bound signed v1 baseline; signed disposable
installer APK installed; system REQUEST_INSTALL_PACKAGES app-op authorized on
**emulator only**; target receives the SHA-bound signed v2 APK via production
`installApkViaThirdParty`; target writes a PackageInstaller session, launches the
system approval UI, receives `STATUS_SUCCESS`; fresh PackageManager package
version and installed base APK SHA256 independently equal the signed v2 fixture.
Independent offline verifier must rehash retained v1/v2/target signed APKs and
private log; raw logs and keys cannot be uploaded. Any unexpected UI, missing
approval, stale package, changed SHA, or interrupted session is a refusal.

**NOT_QUALIFIED** until hosted API 36 workflow actually passes. **P04B P03**
will cover delayed broadcasts, spoof/mismatched versions and parallel handoffs.
Shizuku, Dhizuku and physical devices remain unqualified, as do release and
self-update. No device-owner, root, shell-privileged install or personal package
operation is authorized. This overlay does not merge or publish a release.

## HF01 — lifecycle recovery and stage-bound failure diagnostics

The P04B P02 first hosted positive attempt (GitHub run `43554835212`,
November 14, 2026) timed out after the P03 user-UI cancellation and P04B P01
external-decline tests passed. **Do not classify that run as P04B P02 PASS.**

HF01 repairs the disposable Java installer target to finish its source Activity
after the system PackageInstaller session is submitted. The independent explicit
`StatusActivity` still owns the actual user-approval callback. The hosted runner
records a bounded positive-test stage and reads only the disposable target's
limited shared-preference status. It never guesses that an Android session was
approved. Only if actual `system_status_success`, a recorded verified system UI
tap, and a fresh independent v2 PackageManager+SHA256 inspection all exist may
it restore the original Flutter test Activity using CLEAR_TOP/SINGLE_TOP.

On any refusal, `r02f-p04b-p02-diagnostics.json` is uploaded (not private
Flutter stdout, signed APKs, emulator UI XML or signing keys). It records stage,
strictly classified target state, bounded counters and private-log SHA256,
`REFUSED_NOT_QUALIFIED`, and false qualification flags. On a genuine pass, the
original positive receipt verifier remains mandatory and unchanged. Full
six-workflow exact-head CI and hosted API36 Android acceptance are required.
P04B P03, Shizuku, Dhizuku, physical-device and release qualification remain
unqualified. No device writes outside the disposable hosted emulator.
