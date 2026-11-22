# ObtainX OPT06 P02 — hosted SDK preflight and bounded emulator diagnostics

## Scope

This optimization applies to **all four existing API36 hosted workflows** by
changing their common `scripts/ci/r02_sdk_retry.py` helper. The source-pinned
workflow command, Android 36 / Google APIs / x86_64 targets, pinned emulator
runner, KVM and disk hard gates, production StockInstaller, API36 app launch,
RT02/RT02B/RT02C real Android package-state verification, mandatory evidence
artifacts and independent receipt verification are **unchanged**. The feature
runs only on an authenticated GitHub-hosted Linux x64 runner.

## Conservative SDK precheck

The original helper called `sdkmanager --install` for all three SDK packages
on every run. OPT06 P02 attests the installed `android.jar`, `aapt2` and
`system.img` against their **exact SDK package directories**, conservative
minimum file sizes, unsymlinked directory paths and corresponding bounded
`source.properties` values. It checks API 36, build-tools 35.0.0, Google APIs
and x86_64 where applicable. Invalid/missing/ambiguous metadata is a cache
**miss**, not an acceptance pass.

Only package components passing the precheck are excluded from that
`sdkmanager --install` invocation. A complete precheck permits zero
`sdkmanager` calls, but **still executes the original mandatory `sdk_proof`**.
A partial precheck requests only the missing packages, and still requires
`SDK_IMAGE_PROOF` after installation. The existing single exact-corrupt-ZIP
retry remains; all other failures refuse without retry, deleting caches,
changing the acceptance mode or bypassing download/installs.

## Bounded telemetry

The helper emits `OX_OPT06_P02_SDK_PRECHECK` as a three-bit present bitmap in
the fixed order platform / build-tools / system image. It emits
`OX_OPT06_P02_SDK_DIAGNOSTICS schema=1` with that bitmap, the count of packages
requested, sdkmanager attempts, elapsed time in seconds and a coarse KVM
`ready`/`unavailable` indication. A minimal summary line is appended to the
existing `GITHUB_STEP_SUMMARY` only when writable. It intentionally excludes
paths, environment variables, credentials, raw SDK output and device logs.
KVM status here is **telemetry only**; existing shell/device KVM checks remain
the authority and are not replaced by the status field.

## Qualification and measurement

This source-only change requires the full repository Python test suite, R00 and
SDK source contracts, followed by **all six hosted PR checks**, including all
four API36 workflows. Source-only tests do not confer Android, physical device,
full matrix, user-facing import, publication or release qualification. Runtime
savings depend on actual SDK inventory and hosted runner variance; a `preinstalled`
bitmap by itself does not establish measurable performance improvement.

The overlay never runs local Android Gradle, writes GitHub Actions workflows,
publishes APKs, merges, releases, resets, rebases or force-pushes.
