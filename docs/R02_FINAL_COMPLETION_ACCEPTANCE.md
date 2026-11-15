# ObtainX R02 — Original phase consolidated implementation / acceptance ledger

**Authoritative roadmap:** `ORIGINAL_CONSOLIDATED_ROADMAP_2026-11-10.md` in the updated handoff, unchanged. This is one R02 delivery, not another set of Pxx/HFxx roadmap phases.

**Parent:** PR #21 `17662996fa1295867aa43c12afb1b7f5f8820dcc`, six exact-HEAD hosted GitHub workflows PASS. PRs remain stacked and unmerged. No auto-merge/release.

## Existing verified functionality retained

- R01 bounded ZIP/TAR extractor with atomic publish and hostile archive cases.
- R02 atomic package plans: APK, XAPK, APKS, APKM, ZIP and TAR, with base/config identity checks, ABI, locales/density, minSdk and targetSdk checks.
- Stock Android PackageInstaller positive/negative signed fixture tests, real UI cancellation, external handoff decline/approval and signed-byte receipts.
- Shizuku/Dhizuku permission/absence probes: absence PASS does not prove privileged installation.
- Android 11+ direct OBB delivery is refused when unsupported; source/destination SHA and symlink hardening are preserved.
- P05 API36 read-only profile receipts and optional read-only physical probe.

## New R02 user-facing local installation

- Import/Export now exposes **Install local APK / archive** on Android.
- Uses Android `ACTION_OPEN_DOCUMENT` through existing SAF picker with **no persistent grant**, copies with 64KiB native stream buffering to private cache, a 1GiB limit, SHA-256 and fsync/atomic stage, and cancellable copy.
- Detects installable type from a validated display name. Bounded R01 extraction, complete R02 metadata-driven plans, P05 profile and SDK guards, symlink and OBB checks remain mandatory.
- Requires exactly **one already tracked listing matching the APK package name**. This deliberately refuses standalone untracked packages and multiple-source attribution until a separate explicit-source/verification policy is established.
- Shows explicit package, version, selected APK count, OBB count and selected installer for user approval; refuses all local downgrades, unsupported containers and declined/cancelled picks.
- Calls **the existing** stock/external/Shizuku/Dhizuku installation pipeline with its malware gate and `InstallPrecommitGate`, never adds a parallel privileged installer.
- A reported success is independently checked against Android PackageManager package/version, installed signing certificates and exact source APK byte digests. If the installed state or byte read-back cannot be verified, the UI reports **NOT INDEPENDENTLY QUALIFIED** instead of claiming success.
- External handoff is not install confirmation. No automatic grant of Shizuku, Dhizuku, Device Owner or root privileges.

## CI and accepted evidence (pending new HEAD)

The R00 source-contract and Flutter suites must pass, including the source/mutation and Dart review-policy tests. All six existing exact-HEAD workflows, particularly RT02C's real hosted installers and independent receipts, must still pass. The new local picker path requires an *actual Android document picker selection and installed APK read-back journey* before it can be called fully qualified; code/source tests alone are not that evidence.

## R02 qualification matrix

| Requirement | Evidence / status |
| --- | --- |
| Standalone APK, archive formats, split selection | Existing scoped hosted API36 PASS (PR #21); regression required on this HEAD |
| Wrong signing, downgrade, incompatible SDK | Existing RT02B/R02G hosted PASS; new local flow refuses unreviewed downgrade |
| Stock user-approval, cancellation and third-party handoff | Existing hosted R02F P03/P04 PASS; regression required on this HEAD |
| Shizuku/Dhizuku binder availability | Hosted absence PASS; actual privileged install NOT_QUALIFIED |
| Real user-selected SAF archive import | Source implementation supplied; user-interface Android runtime ACCEPTANCE PENDING |
| Android-side installed signing and exact bytes after new import | Production verification implementation supplied; real runtime ACCEPTANCE PENDING |
| Android 11+ OBB write and atomic multi-OBB rollback | NOT_QUALIFIED / unsupported direct route stays fail-closed |
| ARM64 physical-device install matrix | NOT_QUALIFIED. Existing read-only probe is not an install test |
| Fully merged `main` / signed release | NOT_PERFORMED; explicit review/approval required |

**Never mark original R02 fully qualified** until pending runtime rows have real source-bound receipts, not just an overlay commit or six workflows.

## Safety and delivery

`python3 overlay.zip self-test|check|apply --root ~/Code/ObtainX`; Rich + Termux-safe, exact PR #21 HEAD and file preimage Git blob pins, transactional rollback, full Python regression before commit, one stacked R02 PR (not separate Pxx PRs), no local Gradle, no forced push, no physical-device writes, no merge or release. Resumable CI lookup accepts GitHub eventual consistency but rejects a genuinely moved PR/base. Historical handoff overlays remain `HISTORICAL_DO_NOT_APPLY`.
