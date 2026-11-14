# ObtainX R02F P04 — installer-backend qualification matrix

Scope: P04A first step, **not full P04 runtime qualification**. Source and Dart tests
are not a device receipt. The pending release must be tied to the listing and
match observed Android package identity/version before a broadcast can promote
that release to confirmed. Ordinary device observations may update a displayed
installed version, but never manufacture attribution to a pending downloaded release.

| Backend | Current evidence | P04 status |
| --- | --- | --- |
| System/stock | Prior RT02/RT02B/RT02C and P03 hosted API36; signed fixture 7/7 + UI cancel and original v1 bytes proof | Earlier scoped API36 PASS; P04 full success/rejection matrix pending |
| External (user-chosen installer) | Dart contract for unverified handoff; P04A pending-release-vs-observed package/version checks | **NOT_QUALIFIED** for real external target, approval, timeout, installed bytes |
| Shizuku/Sui | Existing binder installer strategy; no authorized disposable Shizuku service in hosted runtime | **NOT_AVAILABLE / NOT_QUALIFIED**, never PASS |
| Dhizuku Device Owner | Existing binder installer strategy; no authorized disposable device-owner service in hosted runtime | **NOT_AVAILABLE / NOT_QUALIFIED**, never PASS |

## P04 remaining acceptance (P04B)

Real disposable Android installer-target APK; provider to explicit external
activity; timed-out/dismissed handoff; delayed package broadcast; wrong-version
and different-package broadcast; actual `PackageManager` version/code and signed
APK-byte proof; independent success and refusal receipts. The target APK and
fixture package must be disposable. No privileged binder, device-owner setup,
root, or personal device usage to fake an unavailable backend.

Before closure preserve P03 six-source hosted checks, RT02C 7/7, P02 2/2, R02G
real incompatible-SDK rejection and no false success. No forced merge or release.
Then P05 ABI/locale/density/OBB and physical-device constraints; P06 user-facing
archive import; thereafter R03 downloads and R04 GitHub Actions source.
