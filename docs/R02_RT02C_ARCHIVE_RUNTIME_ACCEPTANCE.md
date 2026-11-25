# R02 RT02C — Android 16 archive-to-installer acceptance

**Stacked parent:** ObtainX PR #5, exactly `3d435792348e719a1f366c1ee44f5a2529ba0bc3`.

This lane exercises **five archive formats**: `.apks`, `.apkm`, `.xapk`, `.zip`, and `.tar.gz`. The CI-only fixture generator creates signed base APK v2 and a matching `config.x86_64.apk` split from the inherited RT02A signing script, embeds them in seven reproducible disposable archives, and records exact archive and member SHA-256. The signer generates and deletes its ephemeral CI key; APK bytes and signing keys are never uploaded or published.

A real Flutter `integration_test` downloads a source-bound archive from an emulator-local service, uses ObtainX's bounded atomic `extractZipOffIsolate` or `extractTarballOffIsolate`, validates both extracted signed APK byte digests, calls the deterministic `resolveInstallBundlePlan`, and invokes **Production StockInstaller** for a v1-to-v2 update. Android API36 PackageManager then independently verifies the installed package name, v2 versionCode, presence of exactly two APKs, and exact signed bytes for both base and x86_64 split. The test does not mock the installer, use ADB for positive installation, or fabricate a confirmation tap. ADB is allowed only to provision a disposable version-1 precondition and read package state.

Two **preinstall refusals** must leave the known signed v1 baseline unchanged: a path-traversal `.apks` entry must be rejected before atomic extraction publishes, and an `.apkm` with two ambiguous base APK candidates must be rejected before any StockInstaller call. The harness checks the v1 installed APK hash and versionCode independently after each refusal. It runs each scenario from a freshly restored disposable v1 baseline.

No user data or real installed packages are touched. Every scenario is source- and GitHub-run-bound, with a sanitized per-scenario receipt and bounded progress. Raw Flutter logs remain private to the short-lived CI runner; no APK archives, signing material, screenshots, or private keys are uploaded. Any mismatch, missing evidence, unexpected device, timeout, missing split, insufficient Android state or failed mutation test makes CI fail closed.

**Scope limitations:** This is NOT full R02 runtime-matrix acceptance. It is an archive **extraction-to-session** hosted emulator test, NOT qualification of the complete user-facing download/import/picker UX, XAPK OBB installation or data paths, SAF, external/Shizuku/Dhizuku installers, API-specific UI, user cancellation or interrupted-install rollback. Actual application UX and physical devices remain unqualified. No releases. No merges. No force-pushes. PR #5 and its RT02B evidence remain untouched.

The self-executing `python3 overlay.zip` launcher creates one new stacked PR, runs all inherited Python contracts and source mutation tests in an isolated `$TMPDIR` worktree, checks staged whitespace, and follows **six** exact-head pull-request-triggered GitHub Actions workflows (R00 source, R00 Flutter, RT01, RT02A, RT02B and RT02C). `--watch-only` resumes monitoring without another push; `gh run watch` opens the native GitHub terminal UI, followed by independent SHA-scoped checking and optional Termux success/failure notifications.

## HF11 — owned foreground installer

All five positive archives now use the first-party production StockInstaller
foreground owner (sealed `InstallPrecommitGate`), not the legacy plugin route.
A matching terminal journal, exact baseline and resulting signed APK hashes,
a distinct positive Android session identity, exactly one observed installer
approval, and independent host package-state verification are required. No
negative case may reach the session bridge or publish a session identity. The
previous exact-head run `45512130442` failed before completing a case; no new
hosted result is claimed by this change.

## HF12 — analyzer-safe digest uniqueness

The three `String.fromEnvironment` constants can have equal default values
when analyzed without compile-time defines. Constructing the set through a
list's runtime `toSet()` preserves the distinct-digest assertion without the
static duplicate-set warning. The source gate and mutation tests reject the
original literal, missing/relaxed uniqueness, duplicate inputs and analyzer
warning suppression; actual strict hosted analysis remains required. All
HF11 owned-session and seven-case receipt requirements remain unchanged.
