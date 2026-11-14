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

## HF02 — full regression contract repair and early Flutter failure inspection

The PR #16 batch at source `50184478b9932ef725679be8151c93c9e4b55b71`
completed **4/6 PASS**. R00 source contracts failed two historic mutation tests:
`test_09_no_package_bytes` (the same independent v2 verifier was now called
in two locations) and `test_15_no_false_scope` (a document weakening escaped a
substring-only contract). RT02C verified archives 7/7, P03 Cancel, and P04B
P01 decline, but P04B P02 failed with `approval_pending`, no verified system
approval, and nonzero Flutter exit. No exact root cause can be established from
the privacy-preserving public log alone.

HF02 routes both v2 observations through ONE exact, mutation-tested
`package_observation(fx,2)` gate and strengthens the qualification-source
contract to check the exact bold `NOT_QUALIFIED` statement. This preserves the
existing 16 mutations while adding the full repository regression suite before
any commit. The Android monitor samples only a disposable target's status
before declaring early Flutter exit; the refusal receipt includes a strictly
bounded, allowlisted error **category** and numeric exit code, not raw stdout,
UI XML, package data or stack traces. The UI approval scanner only runs once
the explicit callback reports `user_approval_requested` — never merely because
a native session wrote `approval_pending`. It still requires a verified system
approval tap, `STATUS_SUCCESS`, and fresh signed v2 PackageManager byte proof.

HF02 does not claim that the underlying Flutter failure has been eliminated.
An exact-SHA API36 acceptance and full six-workflow success remain required;
failed or absent receipts remain unqualified. P04B P03, physical
phones, Shizuku/Dhizuku, merged main and release are still outside scope.

## HF03 — Android PackageInstaller broadcast callback and explicit UI launch

HF02 PR #17 run `43638414384` (source `3af3de8c26a2164d3cbdecd8da63c982d4517f1e`)
passed R00 contracts and archives 7/7, P03 UI Cancel, and external decline,
but the positive target remained in `approval_pending` for 420 seconds with
zero user-approval callbacks, scans, or taps. This is *not* a positive pass.

HF03 sends the Android `Session.commit()` mutable status IntentSender to a
manifest-declared, nonexported `BroadcastReceiver` instead of a background
Activity. The receiver records actual `STATUS_PENDING_USER_ACTION` and holds
the OS-provided approval Intent only in memory, without persisting the token.
After observing that exact native callback, the hosted API36 runner may
bring the disposable external target Activity foreground once, causing it to
launch the OS-provided permission UI. The runner still accepts a tap only in
a verified system-package install dialog. A missing callback, process death,
missing system UI, or absence of installed signed-v2 bytes fails closed.

The receiver, activity UI, and PackageInstaller callback do not themselves
qualify installation. The real Android user-approval tap, native
`STATUS_SUCCESS`, current installed version 2, exact installed base APK SHA256,
Flutter's unverified handoff result, and independent offline receipt remain
mandatory. The existing archive, decline, SDK and cancellation gates remain.
The full Python suite must pass prior to commit and six exact-head hosted
workflows must pass before qualification. Physical devices, privileged/remote
installers, Shizuku/Dhizuku, release and main merge remain outside scope.
