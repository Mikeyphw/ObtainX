# ObtainX R02 — deterministic package discovery and atomic split-session plans

**Status: source implementation only. Android device-runtime installation and release signing are NOT qualified.** This PR is stacked on the successful R01 commit `3a57cfdced5940d3cdebd2396ba9c86c21d4926c` (hosted run `42859288599`). It does not merge PR #1 or release an APK.

## Why this slice is necessary

The R01 archive reader safely extracted downloaded bundles, but the install path still used `_preferMatchingApk`: its `removeWhere()` implementation discarded all app-prefixed APK members except the last one, and download metadata discovery picked the first parseable APK. Consequently an archive could silently install only part of a split session, mix incompatible ABIs or select an unexpected package. `installApkDir` also copied OBB expansion data before confirming installation.

## Delivered source behavior

- Every archive is classified as APK, XAPK, APKS, APKM, ZIP, raw TAR, TAR.GZ/TGZ, TAR.BZ2 or TAR.XZ before extraction; unsupported download suffixes are rejected.
- All extracted **`.apk`** files, rather than nested `.zip` containers, are inventoried. Each candidate is inspected with Android's `getPackageArchiveInfo` where possible. Missing metadata for a recognized `config` split may be tolerated; a missing/invalid base identity never is.
- `resolveInstallBundlePlan` creates one immutable base-first list for a single Android package/version. It rejects missing or multiple base APKs, unknown extra APK roles, package/version mismatches, incompatible ABIs, conflicting duplicate names, incorrect minimum Android API, and comma/line-feed path injection.
- On multi-ABI archives, the first supported device ABI present in the split inventory is chosen; language and density `config` splits are preserved rather than incorrectly treating them as standalone APKs.
- System, Shizuku and Dhizuku installers receive all selected paths together; existing backend-specific session APIs are reused. External installers receive the *original* container only after planning/identity checks, with existing handoff semantics preserved.
- OBB filenames must be `main.<int>.<package>.obb` or `patch.<int>.<package>.obb`. Internal OBB copying occurs only after the package installer returns success; external handoff never copies OBBs internally.
- User-defined archive regex filtering is prohibited from silently excluding any recognized config split. Unsupported dynamic-feature `split_<feature>.apk` grouping refuses automatic installation until native Android split metadata can be authenticated.
- Existing archive byte/entry/path budgets, verification checks, pending-install confirmation and signing/release restrictions are preserved.

## Explicit remaining requirements

R02 is **not fully qualified** until genuine Android API 36 and representative lower-API installation sessions prove: standalone APK, XAPK, APKS, APKM, ZIP and TAR; language/density/config splits; ABI preference; signature mismatch; SDK incompatibility; downgrade; user cancellation; external handoff; and Android-confirmed final package state.

`getPackageArchiveInfo` is a metadata discovery interface, **not** cryptographic provenance. Android PackageInstaller still enforces package certificates and install outcomes. The plan does not claim a verified SHA-256, signing identity, attestation, or device acceptance; these require later verification and receipt work. Installer implementation quirks, dynamic feature APKs, compressed split formats and ambiguous multi-variant APK sets deliberately fail closed rather than guessing.

## Testing and contract audit

- `flutter test --no-pub test/r02_install_bundle_plan_test.dart`: deterministic split/standalone/ABI/mismatch/OBB/path fixtures.
- Full `flutter analyze lib test`, complete `flutter test --no-pub`, and unsigned debug build remain mandatory hosted gates (not merely quick regression tests).
- `scripts/ci/r02_install_contract.py --check` audits actual source integration, workflows, documentation, old selectors, and release policy.
- `scripts/ci/test_r02_install_contract.py` mutation-tests dangerous bypasses; it executes alongside all earlier R00/R01/HF02/HF03 contracts with no stale allowlist or weakened checks.

**Qualification labels:** `R02_SOURCE_PASS` does not mean `R02_HOSTED_PASS`, `R02_DEVICE_PASS`, or `RELEASE_QUALIFIED`.


## R02 HF01 — Published-archive cleanup source contract repair

The R02 mutation `test_bad_archive_inventory_cleanup_removed` detected a real
contract gap: the previous audit looked for `extracted.deleteSync(recursive: true)`
**anywhere** in the provider. A different cleanup code path kept the global
substring check green even after the invalid-inventory catch had its deletion
removed. This HF01 delivery requires the entire archive discovery catch to
check `extracted.existsSync()`, delete its published directory and `rethrow`.
Three further mutation cases protect against removing the existence guard,
swallowing the exception, and retaining the deletion text only inside a comment.
No application install, approval, release, or security expectation is weakened.
The same classifier is exercised during `python3 overlay.zip --self-test`.
The hosted Flutter tests and Android debug build are still mandatory; no device
installation or signing qualification is implied by the local Python tests.
