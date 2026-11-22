# OPT06 P03 — bounded Gradle parallelism and disposable emulator cold boot

## Purpose

The last qualified OPT06 P02 run on PR #11 showed that Flutter compilation and
emulator execution dominate runner time. This is a **performance experiment**:
no speedup or behavioral qualification is claimed until the new exact-commit
GitHub Actions suite passes. The preceding OPT06 P02 SDK precheck and
OPT06 P01 RT02C bounded polling remain in place.

## Gradle job parallelism (five hosted jobs)

All existing hosted Android build jobs retain `-Dorg.gradle.caching=true` and add
`-Dorg.gradle.parallel=true` with `-Dorg.gradle.workers.max=2`. This applies to
R00 full Flutter, API36, RT02, RT02B and RT02C. Limiting Gradle to two workers
constrains memory and CPU contention on hosted runners. This is Gradle **project
parallelism** rather than Dart test parallelism; it does not alter any positive
or negative Android installer scenario, Flutter integration-test arguments,
APK signing identities, build flavors or split/OBB acceptance paths.

The R00 source optimization contract now requires the complete **exact**
`GRADLE_OPTS` header in all five jobs. A mutation suite verifies that turning
off Gradle caching, project parallelism or the worker cap refuses qualification.

## Cold disposable emulator (four API36 jobs)

The four existing emulator-runner steps retain the same pinned action,
Android API36 / google_apis / x86_64, Pixel 6 profile, cores, RAM, disk,
KVM and bounded read-only evidence uploads. They now pass `-no-snapshot`, which
prevents loading or saving prior device snapshots. Each job continues to
create a fresh AVD and must satisfy existing independent installed-APK proofs.
No snapshot cache, AVD restore, test fixture reuse or release APK is introduced.

`-no-snapshot` may eliminate shutdown snapshot writes but requires a cold boot;
net time savings are uncertain. This change *prioritizes clean-device identity*
over unverified snapshot startup acceleration.

## Qualification and measurements

The source-pinned overlay runs only Python source-contract and mutation suites
locally (including the complete `scripts/ci/test_*.py` inventory). It **never
runs Gradle on Termux**. It commits and pushes only after those gates pass.
The four Android hosted jobs, R00 source contracts and R00 full Flutter tests
must all succeed on the new exact commit. Measure GitHub Actions job durations,
Gradle build elapsed time, emulator step durations and compile errors against
OPT06 P02 HEAD `001373e55321159cf9b9e6ba4fa9f50b0a2d0307`.

No CI check is removed, skipped, marked `continue-on-error`, or changed to a
release or physical-device qualification claim. No rebase/reset/force push.
