#!/usr/bin/env python3
"""R01 fail-closed source wiring and signing-policy audit.

Supplemental guard only: the actual extractor's behavior is exercised by
Flutter tests with real adversarial archives. Never substitute this for them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_WORKFLOWS = {"build.yml", "release.yml", "pr-base-guard.yml", "format-issue-body.yml"}
EXPECTED_SECURITY_TEST = "test/archive_extraction_security_test.dart"
FIXTURE_DIR = "test/fixtures/r01_archives"


def inspect(root: Path = ROOT, *, git_check: bool = True) -> list[str]:
    failures = []
    def check(condition: bool, problem: str) -> None:
        if not condition:
            failures.append(problem)

    def read(path: str) -> str:
        file = root / path
        if not file.is_file():
            failures.append(f"missing R01 source/contract: {path}")
            return ""
        return file.read_text(encoding="utf-8")

    s = read("lib/services/artifact_file_work.dart")
    app = read("lib/providers/apps_provider_install.dart")
    wf = read(".github/workflows/obtainx-r00-flutter.yml")
    quick = read(".github/workflows/obtainx-r00-contracts.yml")
    policy = read("docs/SECURITY_RELEASE_POLICY.md")
    test = read(EXPECTED_SECURITY_TEST)
    read("docs/R01_ARCHIVE_SECURITY.md")
    for part in ("_safeRelativePath", "_LimitedOutputStream", "maxExpandedBytes",
                 "maxEntryBytes", "maxEntries", "ArchiveExtractionLimits",
                 "FileSystemEntity.typeSync", "stage.renameSync", "seen.add",
                 "directory.fileHeaders", "entry.isSymbolicLink",
                 "_checkArchiveInput", "_fileCrc32", "extractZipOffIsolate", "extractTarballOffIsolate"):
        check(part in s, f"R01 safe extractor enforcement missing: {part}")
    check("_fileCrc32(file) != entry.crc32" in s,
          "ZIP member checksum verification was removed")
    check("byteCount > maxBytes - written" in s,
          "R01 decoded-byte guard expression was removed")
    check("ZipFile.extractToDirectory" not in app,
          "unsafe native ZIP extraction path resurrected")
    check("flutter_archive/flutter_archive.dart" not in app,
          "stale native ZIP import resurrected")
    check(bool(re.search(r"Future<void> unzipFile\([^}]+await extractZipOffIsolate\(", app, re.S)),
          "unzipFile no longer delegates to R01 safe ZIP extraction")
    check("await extractTarballOffIsolate(filePath, destinationPath)" in app,
          "TAR path no longer uses R01 safe extractor")
    check("flutter analyze lib test" in wf and "flutter test --no-pub" in wf and
          "flutter test --no-pub test/archive_extraction_security_test.dart" in wf,
          "R01 Flutter tests/analyzer are not mandatory")
    check("python3 -m unittest discover -s scripts/ci -p 'test_*.py' -v" in quick and
          "r01_security_contract.py --check" in quick,
          "R01 source-contract gate is not wired to push CI")
    check("NO PUBLIC RELEASE QUALIFIED" in policy,
          "release qualification boundary was weakened")
    check("extractZipOffIsolate" in test and "extractTarballOffIsolate" in test,
          "R01 behavioral test file not checking both archive families")

    fixture_receipt = read("docs/R01_FIXTURE_SHA256.json")
    try:
        receipt = json.loads(fixture_receipt)
        check(receipt.get("schema") == 1, "wrong R01 fixture receipt schema")
        files = receipt.get("files")
        check(isinstance(files, dict) and len(files) >= 12, "R01 fixture inventory incomplete")
        if isinstance(files, dict):
            local = root / FIXTURE_DIR
            check(set(files) == {p.name for p in local.glob("*") if p.is_file()},
                  "R01 fixture inventory drift")
            for name, digest in files.items():
                if not re.fullmatch(r"[a-zA-Z0-9_.-]+", name):
                    failures.append("unsafe fixture filename")
                    continue
                p = local / name
                check(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == digest,
                      f"R01 fixture corrupted: {name}")
    except ValueError:
        failures.append("R01 fixture SHA-256 receipt malformed")
    workflows = root / ".github/workflows"
    check(not (FORBIDDEN_WORKFLOWS & {p.name for p in workflows.glob("*")}),
          "legacy release/write workflows resurrected")
    if git_check:
        p = subprocess.run(["git", "ls-files", "-z"], cwd=root,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        check(p.returncode == 0, "cannot check tracked files")
        if p.returncode == 0:
            tracked = [s.decode("utf-8", "replace").lower() for s in p.stdout.split(b"\0") if s]
            check(not [name for name in tracked if name.endswith((".jks", ".p12", ".keystore", ".pfx", ".pem", ".key"))],
                  "tracked signing/private key material")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.parse_args()
    issues = inspect()
    for issue in issues:
        print("OX_R01_SECURITY_CONTRACT_FAIL:", issue)
    if issues:
        return 1
    print("OX_R01_SECURITY_CONTRACT_PASS")
    print("OX_R01_ANDROID_RUNTIME_QUALIFICATION=NOT_PERFORMED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
