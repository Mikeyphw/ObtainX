# RT02F P02 — API36 abandoned session, source-bound acceptance

**Parent**: RT02F P01 PR #10 at `90888b0fcea5e89420afb48accfa8972d5f49c22`.

## Real Android acceptance

RT02F P02 reuses the RT02C API36 disposable x86_64 emulator and the same
short-lived signed fixture APKs. Immediately after RT02C's seven independently
verified archive cases, the host checks the installed version-1 base APK bytes,
then creates and stages two real PackageInstaller sessions (base-only and
base-plus-x86_64-config). Both sessions are explicitly abandoned, not committed.
The installed version 1 and its APK SHA256 must remain unchanged after **each**
session and after final cleanup. Session IDs come strictly from live Android
`pm install-create` output; `pm install-write` succeeds only with exact signed
bytes. The host does not simulate Android package state.

One emulator launch, one existing RT02C Flutter integration process, no new
Flutter test build; only bounded native Android shell session operations are
added. Source, run and fixture digests are independently verified and included
in an allowlisted receipt. Failure to verify any scenario keeps the workflow red.

**Limits**: This is native Android *session abandonment* only. ObtainX **app UI cancellation remains unqualified**, as do third-party installer UI,
Shizuku/Dhizuku, multi-file OBB rollback on a physical-device, Android 11+ OBB
write access, and releases. These are later RT02F acceptance slices.

## Optimization baseline

RT02F P01 RT02C was 819s at GitHub run `43078456735`, up from 670s at
`43069369078`. The latest CI log showed `gradle cache is not found`, and
Flutter/Gradle bootstrap consumed roughly 462s before seven real archive cases.
RT02F P02 uses **zero additional emulator launches** and no duplicate Flutter
compilation. The Gradle cache remains enabled but warm-cache benefit is not
assumed; the post-change exact-SHA hosted logs must be compared.

Retain risk-scoped CI from AuroraStore-Standalone. No silent qualifications,
merges, force pushes, releases, or destructive Git cleanup. R03 remains the next
main feature after R02 runtime qualification.
