# ObtainX OPT06 P01 — bounded Gradle-phase runner polling

## Motivation and measurement

On the successful API36 RT02C run at `0169aa0f342f7ccac808a1e75e212a3705b29eb2`,
the Gradle build occupied roughly 204 seconds before the seven Dart cases began.
The RT02C host loop previously queried `adb shell pm path` once per second while
waiting for the test-runner APK to appear. During actual Gradle compilation,
these probes cannot attest an APK that has not yet been installed.

## Change

Only while the private Flutter log is classified `GRADLE_BUILD`, limit the
*preinstallation runner presence probe* to once every eight seconds. In every
other phase, including test APK installation and Dart execution, probe without
delay. The first probe is always immediate, and invalid/rollback monotonic
clocks refuse rather than silently suppressing a check. The host's `/prepare`
transition independently requires the installed runner package and authorizes
`REQUEST_INSTALL_PACKAGES` before the first archive test begins.

Track `runner_probe_count` and `runner_probe_skipped` in the source-bound
RT02C receipt. These counters are **diagnostic only**, not evidence of runtime
quality or a guaranteed performance improvement.

## Unchanged safety boundaries

Seven ordered archive cases still execute in one Flutter test session. Every
positive case still invokes production `StockInstaller`; every negative case
still refuses before installation. Exact installed APK SHA-256, version, base
plus configuration split paths, Android confirmations and host-driven boundaries
remain mandatory. The disposable API36 emulator, GitHub Actions permissions,
source contracts, full test suite, and artifact retention are unchanged.

No local Gradle, physical-device, release, publication, or full R02 acceptance
is implied. A fresh six-workflow hosted qualification is required after push.

## HF01 receipt test compatibility

The valid synthetic RT02C receipt now includes bounded `runner_probe_count`
and `runner_probe_skipped` fields. Six new negative tests require the verifier
to reject missing, bool, noninteger, negative and excessive values. This
changes no Android runtime qualification requirements.
