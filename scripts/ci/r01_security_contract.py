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
                 "_readZipInventory", "!const [0, 0x4000, 0x8000].contains(fileType)",
                 "length > limits.maxMetadataBytes", "_preflightXz", "_verifyXzChecks",
                 "header[p] > 24", "metadata > limits.maxMetadataBytes",
                 "decodedBytes > limits.maxExpandedBytes - total - outputLength",
                 "_stageExtractionInput", "lock.lockSync(FileLock.exclusive)",
                 "_checkArchiveInput", "_fileCrc32", "extractZipOffIsolate", "extractTarballOffIsolate"):
        check(part in s, f"R01 safe extractor enforcement missing: {part}")
    # The worker must never know or publish the final destination. Keep the
    # publication and cleanup ordering in the controlling isolate. Static
    # checks supplement, not substitute for the Dart execution tests.
    worker_start = s.find('void _extractionWorker(')
    owner_start = s.find('Future<void> _runExtraction(')
    decoder_start = s.find('void _extractArchive(')
    worker = s[worker_start:owner_start]
    owner = s[owner_start:s.find('class _LimitedOutputStream', owner_start)]
    decoder = s[decoder_start:]
    check(worker_start >= 0 and owner_start > worker_start and decoder_start > owner_start and
          'Isolate.exit(reply, true)' in worker and 'renameSync(' not in worker and
          'renameSync(' not in decoder, 'extraction publication must be caller-owned')
    check('onExit: reply.sendPort' in owner and 'onError: reply.sendPort' in owner and
          'worker?.kill(priority: Isolate.immediate)' in owner and
          'await exited.future;' in owner and
          0 <= owner.find('await exited.future;') < owner.find('stage.renameSync(target.path)'),
          'extraction must stop and observe worker exit before publication')
    cleanup = owner[owner.index('} finally {\n    watchdog?.cancel();'):] if '} finally {\n    watchdog?.cancel();' in owner else ''
    check('worker.kill(priority: Isolate.immediate)' in cleanup and
          0 <= cleanup.find('await exited.future;') < cleanup.find('work.deleteSync(recursive: true)'),
          'extraction cleanup must await actual worker exit')
    check('elapsed.elapsed >= limits.maxWallTime' in owner and
          'checkCancellation?.call();' in owner and
          'Timer.periodic(' in owner and 'watchdog?.cancel();' in cleanup,
          'bounded extraction watchdog and cancellation missing')
    check("Directory('$work/decoded')" in decoder and
          'Directory.systemTemp.createTempSync' not in decoder,
          'decoded TAR must share caller-owned staging lifetime')
    for token in ('class _StrictBzipInput extends archive.InputFileStream',
                  'bool get isEOS => false', 'fileRemaining <= 0',
                  'strict.fileRemaining != 0', 'header[3] < 49 || header[3] > 57',
                  'Decoder whole-output readback is forbidden',
                  '++streams > limits.maxEntries'):
        check(token in s, 'strict decoder resource/integrity boundary missing '+token)
    check("_fileCrc32(file) != entry.crc" in s,
          "ZIP member checksum verification was removed")
    check("byteCount > maxBytes - written" in s,
          "R01 decoded-byte guard expression was removed")
    check("ZipFile.extractToDirectory" not in app,
          "unsafe native ZIP extraction path resurrected")
    check("flutter_archive/flutter_archive.dart" not in app,
          "stale native ZIP import resurrected")
    check(bool(re.search(r"Future<void> unzipFile\([^}]+await extractZipOffIsolate\(", app, re.S)),
          "unzipFile no longer delegates to R01 safe ZIP extraction")
    check("await extractTarballOffIsolate(filePath, destinationPath," in app,
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
