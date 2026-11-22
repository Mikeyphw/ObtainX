# ObtainX RT02F HF05 — bounded infrastructure recovery

Source-pinned to PR #11 HEAD `419f654128d66f3a5b96fdfeec5f4f3a6eecb3b2` before this overlay.
This is a narrow hosted CI reliability patch, not an installer feature or qualification claim.

## Evidence and failure separation

- Full PR matrix: Flutter, source, API36 bootstrap, and RT02B passed.
- RT02C: Android SDK package `system-images;android-36;google_apis;x86_64` failed
  extraction with `Error reading Zip content from a SeekableByteChannel` before boot.
- RT02: real standalone install passed. Split test hung in `TEST_APK_INSTALL`
  for 900 seconds with no Dart started and zero Android confirmations.
- Both tests have passed on previous runs; this patch must still rerun the current
  source-bound matrix, and cannot substitute an earlier or manually dispatched run.

## Changes

- All four API36 jobs use the same helper and classify edits to it as high-risk. It retries sdkmanager at most once,
  exclusively after the specific corrupt-ZIP error. It does not clear caches,
  suppress an error, or use stale images. It verifies the platform, build tools,
  and system image files before emulator boot.
- RT02 independently proves the original exact signed v1 fixture is still
  installed before a second split Flutter bootstrap attempt. A successful
  standalone cannot be undone, retried, or re-committed by this recovery.
- A split Flutter pre-Dart stall is detected only after 360s with 180s of no
  log growth. Recovery is one attempt maximum and only if no Dart stage or
  installer confirmation has occurred. Flutter process group is stopped and
  the test app force-stopped; the exact signed v1 package state is rechecked.
- Real signed base/split hashes, version, stock installer approval path, and
  independently verified receipt remain required. No raw device or Flutter
  logs, private data, keys, or fixture APKs are published.

## Scope and limits

Source/mutation checks run locally via the embedded Python ZIP launcher; Gradle
and Android emulator are hosted-only. No fake runtime acceptance, user-device
install, full R02 matrix, release, PR merge, reset, rebase, clean or force push.

Workflow dispatch and PR label changes should remain deliberate user actions.
With `ci:development-only` absent, pushing this fix will start the full
qualification workflows automatically. The prior run is not a current-SHA pass.
