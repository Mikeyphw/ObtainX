# R02F P03 — app-owned native cancellation and source/Android acceptance

This consolidated change supersedes the unapplied P03-precommit partial ZIP and does **not** reapply historical HF09 overlays. Exact parent SHA `0dac5a2aba90118bfb6f050b86526851ae3a4e8e`. An unchanged upstream source is mandatory.

## In scope

The existing download cancellation token governs downloads. On an explicitly interactive install, the provider now issues an exact-listing `InstallPrecommitGate`. A Cancel action before native handoff blocks APK, archive, verification/permission path with a synchronous dispatch barrier. Only first-party stock sessions remain cancellable after native handoff; external/privileged installer handoffs are irreversible from ObtainX and never report rollback. Foreground stock sessions stage signed APK members, capture the original installed-version and APK-byte SHA256, persist the native session ID and ownership, and dispatch to Android's PackageInstaller user-action dialog. A production Flutter widget calls the provider, which requests `PackageInstaller.abandonSession` for precisely that session. Cancel may produce `cancelled` only if native session abandonment and original version+APK hash are independently verified. `unknown` and timeout never claim cancellation.

A private, non-exported native receiver handles PackageInstaller status. A synchronous SharedPreferences journal lets a new engine inspect pending session state after process death. On resumed UI an exact-listing owner can be explicitly cancelled; unknown outcomes retain pending evidence. A package-change notification alone is not a signed-source install receipt. The native bridge does not require root, Shizuku, Dhizuku, or an ADB shell. No release/merge action is automated.

## Negative coverage / required qualification

Local Python mutation tests reject removed tap/bridge/rollback/evidence gates, token reuse, suppressed cancellation, missing native session management, privileged shortcuts or host-only ADB abandonment. Flutter gate tests cover lifecycle/multi-source/stale owners. Hosted API 36 runs RT02C 7 archive cases, P02 2 native abandon cases, R02G refusal and P03 *actual production app Cancel widget* against a disposable signed APK v1/v2 pair. The hosted test must witness Android approval, return to ObtainX, tap its production widget, receive verified native `cancelled`, and prove `v1 base.apk` SHA256/version unchanged afterward. The CI artifact is only a small, exact-source result; private logs and original signed APKs are not published.

**NOT QUALIFIED at archive authoring time:** P03 Dart/Flutter compile, Kotlin Android compile, real P03 hosted UI Cancel, process-kill-during-approval, OEM/Oplus package race, all unsupported Shizuku/Dhizuku/Android 11+ OBB and physical-device acceptance. The six already-green runs belong to the *old* parent SHA. A later source-bound hosted run may fail and must yield `REFUSED` without overriding previous evidence.
