# R01 — Archive extraction security

Status: implementation staged; **no Android runtime qualification or release authorization**.

Scope: replaces the previous native ZIP extraction entry point and TAR extraction with a shared bounded, isolated, atomic extractor. This is an R01 security change, *not* the R02 APK/split-package planner.

## Enforced checks

- Both `unzipFile()` and `extractTarballFile()` call the shared pure-Dart extractor via an isolate.
- Refuse archive input symlinks and inputs larger than the configured cap.
- Reject absolute paths, Windows drive paths, `..`, dot segments, empty path segments, special links, duplicate/case-folded paths, control characters, excessive depth and oversized entry names.
- Check ZIP central-directory entries rather than trusting archive v4's deduplicated model.
- Bound entries, per-file decoded bytes, total decoded bytes, and intermediate decoded TAR output. The actual emitted byte count is checked against declared size, and extracted ZIP members are checked against their CRC32 (which is not a cryptographic authenticity check).
- Extract into a fresh private sibling directory; only publish on full success by rename. Failed extraction removes the staging tree, leaving the destination untouched.
- Preserve ZIP, TAR, TAR.GZ, TAR.BZ2, TAR.XZ; no silent fallback to the previous unrestricted extraction path.
- Do not create public releases or sign APKs during R01.

## Acceptance evidence and remaining gates

`test/archive_extraction_security_test.dart` exercises valid ZIP/TAR.GZ and negative fixtures: traversal, symlink, absolute names, duplicate ZIP central-directory entries, case collision, malformed input, file count, path depth, source size, cumulative expanded size, ZIP CRC32 handling and expanded TAR intermediate size. CI runs `flutter analyze lib test` and the full `flutter test` suite. Hosted Android debug compilation is *not* a device runtime install test.

The current ZIP/TAR format parser is the pinned `archive: ^4.0.9` library. Its decoder allocation behavior still warrants Android-device memory/resource acceptance; no runtime claim is made until that gate passes.

R02 must introduce complete APK/split planning; do not interpret the R01 extraction tests as proof that APKS/APKM/XAPK installation is correct. Release signing remains prohibited by `docs/SECURITY_RELEASE_POLICY.md`.
