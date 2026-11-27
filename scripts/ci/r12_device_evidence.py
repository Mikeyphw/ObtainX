#!/usr/bin/env python3
"""Read-only review-input verifier for the R12 physical acceptance matrix.

This validates bytes and evidence bindings, not authenticity of human review.
No installation, release publication, or automatic release authorization.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys
from r12_release_gate import ROOT, ABIS, HEX40, HEX64, REPO, Refused, digest, require, identity, inspect_apks

MATRIX = {
    'api36-system': 'Real stock installer positive, split, wrong-signer, downgrade and archive refusals on API36',
    'physical-system': 'Physical stock Android standalone and split install, cancellation, verified final package and signer',
    'physical-shizuku': 'Physical Shizuku availability, approved positive and refusal paths',
    'physical-dhizuku': 'Physical Dhizuku availability, approved positive and refusal paths',
    'external-installer': 'Approved external installer handoff and returned package/signature/channel evidence',
    'saf-obb': 'Storage Access Framework selection, scoped OBB permission/refusal, atomic cleanup and digest',
    'download-recovery': 'Wi-Fi/charging conditions, interruption, persisted restart/process-death recovery, no unsafe retry',
    'tasker-app-manager': 'Consent-bound Tasker/App Manager check, queue, receipt and revocation; wrong channel refused',
    'accessibility': 'TalkBack, 200% text, contrast, keyboard/mouse/TV navigation and localized safety labels',
    'live-providers': 'Authorized current public/private source retrieval, rate/refusal policy and exact artifact binding',
    'signer-migration': 'Old-signer update refused; new-signer fixture accepted; export/restore and reviewed migration notes',
}


def load(path):
    require(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= 32 * 1024 * 1024, 'missing/unsafe evidence document')
    def pairs(rows):
        out = {}
        for k, v in rows:
            require(k not in out, 'duplicate evidence key')
            out[k] = v
        return out
    return json.loads(path.read_text(), object_pairs_hook=pairs)


def file_proof(directory, row):
    name = row.get('path', '')
    require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,160}', name) is not None and '..' not in name, 'unsafe evidence path')
    p = directory / name
    require(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= 32 * 1024 * 1024, 'unsafe or empty evidence file')
    require(digest(p) == row.get('sha256'), 'evidence digest mismatch')
    return name


def verify_matrix(candidate, matrix, evidence_dir):
    require(candidate.get('schema') == 'obtainx.r12.signed-candidate.v1' and candidate.get('repository') == REPO and
            HEX40.fullmatch(str(candidate.get('source_sha', ''))) and HEX40.fullmatch(str(candidate.get('source_tree', ''))) and
            HEX64.fullmatch(str(candidate.get('certificate_sha256', ''))), 'invalid candidate identity')
    require(candidate.get('package_status') == 'SIGNED_CANDIDATE_VERIFIED' and candidate.get('publication_authorized') is False and
            candidate.get('SOURCE_PASS') == 'PASS_BUILD_LANES' and candidate.get('HOSTED_CI_PASS') == 'PASS_EXACT_MAIN_FULL_JOBS', 'candidate prerequisites absent')
    require(matrix.get('schema') == 'obtainx.r12.device-matrix.v1' and matrix.get('repository') == REPO, 'wrong device matrix schema')
    for key in ('source_sha', 'source_tree', 'certificate_sha256'):
        require(matrix.get(key) == candidate.get(key), 'stale device evidence binding')
    apks = candidate.get('apks', {})
    require(set(apks) == {f'app-{abi}-normal-release.apk' for abi in ABIS}, 'candidate ABI inventory missing')
    rows = matrix.get('lanes', {})
    require(isinstance(rows, dict) and set(rows) == set(MATRIX), 'incomplete device matrix')
    pending, failed, complete = [], [], []
    used = set()
    for lane, row in rows.items():
        status = row.get('status')
        require(status in ('PASS', 'FAIL', 'PENDING_EXTERNAL', 'UNSUPPORTED'), 'invalid device status')
        if status in ('PENDING_EXTERNAL', 'UNSUPPORTED'):
            require(bool(row.get('reason')), 'missing pending/unsupported reason')
            pending.append(lane)
            continue
        apk = row.get('apk')
        require(apk in apks and row.get('apk_sha256') == apks[apk]['sha256'], 'device tested wrong APK bytes')
        require(row.get('observed_utc') and row.get('reviewer') and row.get('backend') and row.get('android_sdk'), 'missing device observation metadata')
        require(type(row['android_sdk']) is int and 26 <= row['android_sdk'] <= 100, 'invalid Android API evidence')
        require(row.get('authorized_fixture') is True, 'device fixture approval missing')
        files = row.get('evidence')
        require(isinstance(files, list) and bool(files), 'missing device evidence')
        for f in files:
            name = file_proof(evidence_dir, f)
            require(name not in used, 'evidence reused across lanes')
            used.add(name)
        (complete if status == 'PASS' else failed).append(lane)
    return {'complete': sorted(complete), 'failed': sorted(failed), 'pending': sorted(pending),
            'device_evidence_status': 'READY_FOR_INDEPENDENT_REVIEW' if not failed and not pending else 'INCOMPLETE',
            'DEVICE_RUNTIME_PASS': 'PENDING_INDEPENDENT_REVIEW', 'RELEASE_QUALIFIED': False,
            'publication_authorized': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True, help='directory of downloaded signed candidate evidence')
    parser.add_argument('--expected-sha', required=True)
    parser.add_argument('--expected-cert', required=True)
    parser.add_argument('--matrix', type=Path, required=True)
    parser.add_argument('--evidence-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        candidate = load(args.candidate / 'candidate.json')
        actual = identity(ROOT, args.expected_sha)
        require(all(candidate.get(k) == v for k, v in actual.items()), 'candidate is not current exact source')
        require(candidate.get('certificate_sha256') == args.expected_cert, 'candidate certificate differs from independent pin')
        require(inspect_apks(ROOT, args.candidate, expected_signer=args.expected_cert) == candidate['apks'], 'candidate APK bytes/signature/metadata changed')
        for filename, field in [('dependencies.json', 'dependencies_sha256'), ('gradle-dependencies.txt', 'gradle_inventory_sha256'), ('sbom.cdx.json', 'sbom_sha256'), ('advisories.json', 'advisories_sha256'), ('ci.json', 'ci_sha256'), ('toolchain.json', 'toolchain_sha256')]:
            require(digest(args.candidate / filename) == candidate.get(field), 'candidate evidence changed')
        require([digest(args.candidate / f'{replica}-build.json') for replica in ('a', 'b')] == candidate.get('unsigned_builds'), 'unsigned provenance changed')
        print(json.dumps(verify_matrix(candidate, load(args.matrix), args.evidence_dir), indent=2, sort_keys=True))
        return 0
    except (Refused, OSError, ValueError, TypeError, KeyError):
        print('R12_REVIEW_REFUSED: missing, stale or inconsistent evidence', file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
