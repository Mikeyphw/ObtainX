# RT02B — Android 16 installer rejection acceptance

**source-pinned parent:** RT02A PR #4, head `c1ec76cc2b34147c171a9be40c62fdc6411eefac`.

This is a new, separately reviewable, stacked feature PR. Its hosted Android API 36
Google APIs x86_64 emulator test is read-only with respect to the repository
and uses only disposable, CI-generated APK fixture identities. No merges,
No releases, no release signing keys, and no production credentials.

## What is actually tested

The host first uses ADB solely to provision a disposable version-2 baseline
of `dev.bikram.obtainx.rt02.fixture`. This is **not** claimed as an ObtainX
installation. It independently establishes that Android has exactly one base
APK, versionCode 2, and the exact byte hash of the signed baseline.

Then a real on-device Flutter `integration_test` calls **Production StockInstaller**
with each negative APK. The first APK has versionCode 3 but a **wrong certificate**
with an independently verified different SHA-256 signing identity. The second
APK is a same-certificate **downgrade** to versionCode 1. Both must result in
platform-reported errors. System approval screens, when present, may be acted on
only when the screen belongs to an approved Android installer and explicitly
names the disposable fixture package. Never fabricate approvals, fake a platform
result, invoke `adb install` for the negative attempts, or accept the absence
of a dialog as proof by itself.

After each attempt, the runner independently queries Android package state,
versionCode, installed path count and installed APK SHA-256. The baseline
must remain version 2, one base APK, unchanged bytes. If any mismatch, installer
failure, missing error, absent source proof, unexpected emulator identity, APK
signature collision, timeout or incomplete evidence occurs, the run remains red.

The independent receipt verifier demands two distinct real negative attempts,
unchanged installed version/bytes, signed fixture identity checks, exact commit
SHA and run ID. Only allowlisted phases, hashes and result fields are uploaded;
raw Flutter/device logs and private keys stay off artifacts.

**Scope:** RT02B demonstrates only Android 16 system-installer rejections for
wrong-signature updates and downgrades against a disposable baseline. This is
**NOT full R02** acceptance, not APKS/APKM/XAPK/ZIP/TAR end-to-end import,
not cancellation/approval interruption coverage, not Shizuku/Dhizuku/external
installer parity, not physical device qualification and not release signing.
The parent RT02A's actual successful standalone/split-install evidence remains
separate and unchanged.

## Delivery and governance

Apply with the embedded Termux Python ZIP entrypoint; it uses `$TMPDIR`, a clean
separate worktree, exact Git blob preimage checks and a fast-forward push to a
new stacked branch. It creates a PR rather than modifying main. The launcher
immediately opens the real GitHub CLI `gh run watch` interface for the exact
source commit, then verifies all five mandatory hosted checks. It sends a
SUCCESS or FAILURE Termux toast and vibration on exit. No automatic merge,
release or force-push is authorized.
