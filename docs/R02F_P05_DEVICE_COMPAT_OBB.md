# ObtainX R02F P05 — Android device profile, SDK and OBB acceptance

Source parent: PR #20 HF01 at `c3b96b8cda72f1a4b2de96b594e9cc85ad8e5dfa`.
Previous P03/P04 hosted API36 qualification: six exact-head workflows PASS.

## Scope of this consolidated P05 overlay

- Reuse the RT02D production bundle planner for ABI order (including ARM64 preference),
  all configured locales, nearest-density split, base/split package and version identity.
- Validate the real device SDK, ABI list, locale and display metadata **before**
  invoking the production plan; validate the selected min/target SDK envelope
  after selection; preserve the existing signed-session gate.
- Harden RT02E verified OBB copy by refusing symlink ancestors before creating
  a destination and again after directory creation. Preserve streaming source
  SHA256 and staged SHA256, length checks, source immutability, cancellation and
  rollback. No multi-file atomic-across-power-loss claim.
- Keep the existing Android 11+ (API30+) direct OBB refusal **before install**.
  A third-party original-container handoff does not prove OBB delivery.
- Add real hosted API36 read-only observations of emulator ABI, SDK, density,
  and locale with independent source-bound fixture bytes and offline receipt.
- Add an explicitly acknowledged optional **physical** read-only profile probe,
  with zero app installs, no root, no device-owner changes and no personal
  package enumeration. It cannot qualify physical ARM64 installation.

## Mandatory acceptance

R00 Python source/mutation tests and Flutter analyzer/unit tests are mandatory.
RT02C runs the original archive/SDK/stock/cancellation/P04 positive/P03
adversarial/P04 backend matrix unchanged, *then* records P05 read-only API36
profile and verifies the exact receipt independently after emulator exit.
All six GitHub Actions workflows must finish successfully on the same PR HEAD.

## Explicit nonqualification

**NOT_QUALIFIED**: physical ARM64 APK writes, Android 11+ OBB copy, privileged
Shizuku/Dhizuku installation, locale/density-specific real physical install,
production multi-file OBB rollback, main-branch merge and release. Source
and hosted emulator checks are not substitutes for device consent/evidence.

## Remaining roadmap

R02F P06: user-selected archive file import and cancellation, SAF grants,
Android real UI and signed package-state receipts. Then dependency-ordered PR
review/merge only with approval, R03 durable Range/ETag verified downloads,
R04 Actions artifact acquisition, R05-R11 UX and transaction flow, and R12
full physical-device security and release acceptance.
