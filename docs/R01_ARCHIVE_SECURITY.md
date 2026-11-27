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

### GAP-02-HF02: independently generated XZ regression fixtures

The pinned archive 4.3.0 encoder's `_writeMultibyteInteger` (upstream commit
`b48a841b586af8b41c67ce2cbeebc8db632ed13e`, encoder blob
`82a778fbc27a9c6bb9ca39531953bd5c6597c521`) writes reversed multi-byte VLI
values in the index. Do not relax `_preflightXz`, change decoder verification,
or interpret this fixture defect as permission to accept noncanonical XZ.
The original 2048-byte nested-APK TAR requires unpadded size 2072 in the stored
block: canonical index prefix `000198108010`, malformed prefix `000190189000`.
The frozen malformed fixture uses this exact encoder mechanism with deterministic
USTAR metadata, not the original transient runner bytes. Correcting only the
index and its CRC makes it independently readable; malformed index and corrupted
block-check inputs must be refused with no published or orphan staging tree.

Positive fixtures are independently compressed using Python `tarfile` (USTAR,
`nested/app.apk`, mode 0644, uid/gid 0, mtime 0, two 512-byte terminating zero
blocks) and `lzma` (FORMAT_XZ, LZMA2 only, 1 MiB dictionary, CRC32/CRC64/SHA256).
Small payload is `test apk content`; large payload is 196608+37 bytes with byte
`(i*31)%251`. The malformed fixture is the small TAR in one stored LZMA2 chunk
with an 8 MiB dictionary, valid metadata CRCs and CRC64 block check, but the
reversed legacy index fields. The corrupted block-check fixture is the valid
large CRC64 fixture with the last check byte toggled by 1. All new bytes are
pinned in `docs/R01_FIXTURE_SHA256.json`. The independent Python regression
`test_gap02_hf02_contract.py` verifies decoded payload, compression, index
mechanism, and refusal by liblzma. The maintained Flutter tests exercise the
actual application extractor (including cleanup and byte budget). Python
fixture verification is not Flutter/runtime qualification.
