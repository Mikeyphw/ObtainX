#!/usr/bin/env python3
"""Read-only review-input verifier for the R12 physical acceptance matrix.

This validates bytes and evidence bindings, not authenticity of human review.
No installation, release publication, or automatic release authorization.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import re
import sys
from r12_release_gate import ROOT, ABIS, HEX40, HEX64, REPO, PACKAGE, Refused, digest, require, identity, inspect_apks

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


# Closed observation vocabulary: not arbitrary backend strings or a screenshot
# relabeled as eleven passes. Each item is an independently reviewable claim.
LANE_RULES = {
    'api36-system': ('system', 'emulator', {'standalone': 'INSTALLED', 'split': 'INSTALLED', 'wrong-signer': 'REFUSED', 'downgrade': 'REFUSED', 'archive-invalid': 'REFUSED'}),
    'physical-system': ('system', 'physical', {'standalone': 'INSTALLED', 'split': 'INSTALLED', 'cancel': 'CANCELLED', 'installed-identity': 'VERIFIED'}),
    'physical-shizuku': ('shizuku', 'physical', {'availability': 'VERIFIED', 'approved-install': 'INSTALLED', 'refusal': 'REFUSED'}),
    'physical-dhizuku': ('dhizuku', 'physical', {'availability': 'VERIFIED', 'approved-install': 'INSTALLED', 'refusal': 'REFUSED'}),
    'external-installer': ('external', 'physical', {'approved-handoff': 'INSTALLED', 'returned-identity-channel': 'VERIFIED', 'declined-handoff': 'REFUSED'}),
    'saf-obb': ('saf', 'physical', {'selection': 'VERIFIED', 'permission-refusal': 'REFUSED', 'obb-digest-cleanup': 'VERIFIED'}),
    'download-recovery': ('download', 'physical', {'network-power-policy': 'VERIFIED', 'interruption': 'RESUMED', 'process-death': 'RESUMED', 'unsafe-retry': 'REFUSED'}),
    'tasker-app-manager': ('automation', 'physical', {'consented-check': 'VERIFIED', 'queue': 'QUEUED', 'receipt': 'VERIFIED', 'revocation': 'REFUSED', 'wrong-channel': 'REFUSED'}),
    'accessibility': ('ui', 'physical', {'talkback': 'VERIFIED', 'text-200-percent': 'VERIFIED', 'contrast': 'VERIFIED', 'keyboard-mouse-tv': 'VERIFIED', 'localized-safety': 'VERIFIED'}),
    'live-providers': ('source', 'physical', {'authorized-public': 'VERIFIED', 'authorized-private': 'VERIFIED', 'rate-refusal': 'REFUSED', 'artifact-binding': 'VERIFIED'}),
    'signer-migration': ('system', 'physical', {'old-signer': 'REFUSED', 'new-signer': 'INSTALLED', 'export-restore': 'VERIFIED', 'migration-review': 'VERIFIED'}),
}
OUTCOMES = frozenset({'INSTALLED', 'REFUSED', 'CANCELLED', 'VERIFIED', 'RESUMED', 'QUEUED', 'ERROR'})
BINDINGS = ('source_sha', 'source_tree', 'certificate_sha256', 'apk', 'apk_sha256',
            'backend', 'device_kind', 'android_sdk', 'reviewer')


def utc_timestamp(value):
    require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z', value) is not None,
            'observation timestamp must be RFC3339 UTC')
    try:
        parsed = datetime.fromisoformat(value[:-1] + '+00:00')
    except ValueError as exc:
        raise Refused('invalid observation timestamp') from exc
    require(datetime(2026, 1, 1, tzinfo=timezone.utc) <= parsed <= datetime.now(timezone.utc) + timedelta(minutes=5),
            'observation timestamp outside accepted bounds')
    return parsed


def label(value):
    return isinstance(value, str) and 0 < len(value.strip()) <= 120 and not any(ord(c) < 32 or ord(c) == 127 for c in value)


def load(path, expected_digest=None):
    require(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= 32 * 1024 * 1024, 'missing/unsafe evidence document')
    def pairs(rows):
        out = {}
        for k, v in rows:
            require(k not in out, 'duplicate evidence key')
            out[k] = v
        return out
    raw = path.read_bytes()
    require(0 < len(raw) <= 32 * 1024 * 1024, 'evidence document changed size')
    if expected_digest is not None:
        import hashlib
        require(hashlib.sha256(raw).hexdigest() == expected_digest, 'observation changed after hash')
    return json.loads(raw, object_pairs_hook=pairs)


def file_proof(directory, row, used_names, used_digests):
    require(isinstance(row, dict), 'invalid evidence reference')
    name = row.get('path', '')
    require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,160}', name) is not None and '..' not in name, 'unsafe evidence path')
    p = directory / name
    require(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= 32 * 1024 * 1024, 'unsafe or empty evidence file')
    actual = digest(p)
    require(actual == row.get('sha256'), 'evidence digest mismatch')
    require(name.casefold() not in used_names and actual not in used_digests, 'duplicate evidence name or content')
    used_names.add(name.casefold())
    used_digests.add(actual)
    return p


def package_state(value):
    require(isinstance(value, dict) and isinstance(value.get('package'), str) and
            re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+', value['package']) and
            type(value.get('version_code')) is int and value['version_code'] > 0 and
            HEX64.fullmatch(str(value.get('certificate_sha256', ''))) and
            HEX64.fullmatch(str(value.get('apk_sha256', ''))) and
            value.get('independently_observed') is True, 'installed package identity missing')
    return value


def verify_matrix(candidate, matrix, evidence_dir):
    require(isinstance(candidate, dict) and isinstance(matrix, dict), 'invalid evidence root')
    require(candidate.get('schema') == 'obtainx.r12.signed-candidate.v1' and candidate.get('repository') == REPO and
            HEX40.fullmatch(str(candidate.get('source_sha', ''))) and HEX40.fullmatch(str(candidate.get('source_tree', ''))) and
            HEX64.fullmatch(str(candidate.get('certificate_sha256', ''))), 'invalid candidate identity')
    require(candidate.get('package_status') == 'SIGNED_CANDIDATE_VERIFIED' and candidate.get('publication_authorized') is False and
            candidate.get('SOURCE_PASS') == 'PASS_BUILD_LANES' and candidate.get('HOSTED_CI_PASS') in ('PASS_EXACT_MAIN_FULL_JOBS', 'PASS_EXACT_MERGED_TREE_FULL_JOBS'), 'candidate prerequisites absent')
    require(matrix.get('schema') == 'obtainx.r12.device-matrix.v2' and matrix.get('repository') == REPO, 'wrong device matrix schema')
    for key in ('source_sha', 'source_tree', 'certificate_sha256'):
        require(matrix.get(key) == candidate.get(key), 'stale device evidence binding')
    apks = candidate.get('apks', {})
    require(isinstance(apks, dict) and set(apks) == {f'app-{abi}-normal-release.apk' for abi in ABIS}, 'candidate ABI inventory missing')
    for name, apk in apks.items():
        require(isinstance(apk, dict) and HEX64.fullmatch(str(apk.get('sha256', ''))) and
                apk.get('package') == PACKAGE and type(apk.get('version_code')) is int and apk['version_code'] > 0 and
                label(apk.get('version_name')) and apk.get('certificate_sha256') == candidate['certificate_sha256'] and
                name == f'app-{apk.get("abi")}-normal-release.apk', 'invalid candidate APK metadata')
    rows = matrix.get('lanes', {})
    require(isinstance(rows, dict) and set(rows) == set(MATRIX), 'incomplete device matrix')
    pending, failed, complete = [], [], []
    used_names, used_digests = set(), set()
    for lane, row in rows.items():
        require(isinstance(row, dict), 'invalid lane record')
        status = row.get('status')
        require(status in ('PASS', 'FAIL', 'PENDING_EXTERNAL', 'UNSUPPORTED'), 'invalid device status')
        if status in ('PENDING_EXTERNAL', 'UNSUPPORTED'):
            require(label(row.get('reason')) and 'observations' not in row, 'missing pending reason or contradictory observations')
            pending.append(lane)
            continue
        apk_name = row.get('apk')
        require(isinstance(apk_name, str) and apk_name in apks and row.get('apk_sha256') == apks[apk_name]['sha256'], 'device tested wrong APK bytes')
        backend, device_kind, expected = LANE_RULES[lane]
        require(row.get('backend') == backend and row.get('device_kind') == device_kind, 'lane backend or device kind mismatch')
        sdk = row.get('android_sdk')
        require(type(sdk) is int and 26 <= sdk <= 100 and (lane != 'api36-system' or sdk == 36), 'invalid Android API evidence for lane')
        observed = utc_timestamp(row.get('observed_utc'))
        require(label(row.get('reviewer')) and row.get('authorized_fixture') is True, 'device observation metadata or fixture approval missing')
        require(row.get('abi') == apks[apk_name]['abi'], 'device ABI/candidate mismatch')
        observations = row.get('observations')
        require(isinstance(observations, dict) and set(observations) == set(expected), 'missing or unexpected lane observations')
        results = []
        for check, expected_outcome in expected.items():
            proof = file_proof(evidence_dir, observations[check], used_names, used_digests)
            obj = load(proof, observations[check]['sha256'])
            require(isinstance(obj, dict) and obj.get('schema') == 'obtainx.r12.device-observation.v2' and
                    obj.get('repository') == REPO and obj.get('lane') == lane and obj.get('check') == check,
                    'wrong observation identity')
            require(all(obj.get(k) == (candidate[k] if k in ('source_sha', 'source_tree', 'certificate_sha256') else row[k]) for k in BINDINGS), 'observation not bound to candidate/lane')
            stamp = utc_timestamp(obj.get('observed_utc'))
            require(stamp <= observed and obj.get('authorized_fixture') is True and obj.get('abi') == row['abi'], 'observation time/approval/ABI mismatch')
            result = obj.get('outcome')
            require(isinstance(result, str) and result in OUTCOMES and obj.get('expected_outcome') == expected_outcome, 'invalid observed outcome')
            installed = package_state(obj.get('candidate_package_state'))
            require(all(installed.get(k) == apks[apk_name][k] for k in ('package', 'version_code', 'certificate_sha256')) and
                    installed['apk_sha256'] == apks[apk_name]['sha256'], 'observed candidate package differs from signed bytes')
            if result == 'INSTALLED' or check == 'installed-identity':
                # The candidate is the app under test. Installed test target
                # may be a distinct disposable fixture.
                package_state(obj.get('target_package_state'))
            if check in {'wrong-signer', 'downgrade', 'archive-invalid', 'cancel', 'refusal', 'declined-handoff', 'old-signer'} and result in ('REFUSED', 'CANCELLED'):
                require('target_before' in obj and 'target_after' in obj, 'missing refusal package-state evidence')
                before, after = obj['target_before'], obj['target_after']
                require(before == after and obj.get('owned_session_remaining') is False, 'refusal mutated package or leaked owned session')
                if before is not None:
                    package_state(before)
            attachments = obj.get('attachments')
            require(isinstance(attachments, list) and 1 <= len(attachments) <= 8, 'missing or excessive observation attachments')
            kinds = set()
            for attachment in attachments:
                require(isinstance(attachment, dict) and attachment.get('kind') in ('receipt', 'sanitized-log', 'screenshot', 'review-note'), 'invalid evidence attachment kind')
                file_proof(evidence_dir, attachment, used_names, used_digests)
                kinds.add(attachment['kind'])
            require(bool(kinds & {'receipt', 'sanitized-log'}), 'machine/diagnostic evidence required; screenshot or assertion alone insufficient')
            results.append(result == expected_outcome)
        require((status == 'PASS') == all(results), 'lane verdict contradicts observations')
        (complete if status == 'PASS' else failed).append(lane)
    return {'complete': sorted(complete), 'failed': sorted(failed), 'pending': sorted(pending),
            'device_evidence_status': 'READY_FOR_INDEPENDENT_REVIEW' if not failed and not pending else 'INCOMPLETE',
            'DEVICE_RUNTIME_PASS': 'PENDING_INDEPENDENT_REVIEW', 'RELEASE_QUALIFIED': False,
            'publication_authorized': False}


def verify_candidate(directory, actual, expected_cert, *, root=ROOT):
    """Recheck all published provenance, including fresh-main CI and both builders.

    Unsigned APK bytes are not included in the signed evidence artifact. Their
    records are compared; no local unsigned-build execution is inferred.
    """
    from r12_release_gate import compare_builds, validate_ci_receipt, osv_queries
    require(directory.is_dir() and not directory.is_symlink(), 'unsafe candidate directory')
    candidate = load(directory / 'candidate.json')
    require(isinstance(candidate, dict) and candidate.get('schema') == 'obtainx.r12.signed-candidate.v1' and
            all(candidate.get(k) == v for k, v in actual.items()), 'candidate is not current exact source')
    require(HEX64.fullmatch(expected_cert) and candidate.get('certificate_sha256') == expected_cert,
            'candidate certificate differs from independent pin')
    require(candidate.get('package_status') == 'SIGNED_CANDIDATE_VERIFIED' and
            candidate.get('SOURCE_PASS') == 'PASS_BUILD_LANES' and
            candidate.get('reproducibility') == 'UNSIGNED_EXACT_BYTES_MATCH' and
            candidate.get('RELEASE_QUALIFIED') is False and candidate.get('publication_authorized') is False,
            'candidate provenance or authorization state invalid')
    require(type(candidate.get('run_id')) is str and candidate['run_id'].isdigit() and int(candidate['run_id']) > 0 and
            type(candidate.get('run_attempt')) is str and candidate['run_attempt'].isdigit() and int(candidate['run_attempt']) > 0,
            'candidate run identity missing')
    require(inspect_apks(root, directory, expected_signer=expected_cert) == candidate['apks'],
            'candidate APK bytes/signature/metadata changed')
    files = {'dependencies.json': 'dependencies_sha256', 'gradle-dependencies.txt': 'gradle_inventory_sha256',
             'sbom.cdx.json': 'sbom_sha256', 'advisories.json': 'advisories_sha256',
             'ci.json': 'ci_sha256', 'toolchain.json': 'toolchain_sha256'}
    for filename, field in files.items():
        require(digest(directory / filename) == candidate.get(field), 'candidate evidence changed')
    require('PASS_' + validate_ci_receipt(load(directory / 'ci.json'), actual) == candidate['HOSTED_CI_PASS'],
            'CI provenance mismatch')
    records = [load(directory / f'{replica}-build.json') for replica in ('a', 'b')]
    require([digest(directory / f'{replica}-build.json') for replica in ('a', 'b')] == candidate.get('unsigned_builds'),
            'unsigned provenance changed')
    run_ident = dict(actual, run_id=candidate['run_id'], run_attempt=candidate['run_attempt'])
    unsigned = compare_builds(*records, run_ident)
    require(set(unsigned) == set(candidate['apks']) == {f'app-{abi}-normal-release.apk' for abi in ABIS},
            'unsigned/signed ABI inventory mismatch')
    for name, row in unsigned.items():
        require(row['payload'] == candidate['apks'][name]['payload'] and
                all(row.get(k) == candidate['apks'][name].get(k) for k in ('package', 'abi', 'version_code', 'version_name')),
                'signed payload or identity differs from unsigned builders')
    inventory = load(directory / 'dependencies.json')
    queries = osv_queries(inventory['pub'], inventory['maven'])
    for replica, record in zip(('a', 'b'), records):
        for field in ('dependencies_sha256', 'sbom_sha256', 'toolchain_sha256', 'ci_sha256'):
            require(record.get(field) == candidate.get(field), 'unsigned common provenance mismatch')
        for filename, field in [('advisories.json', 'advisories_sha256'), ('gradle-dependencies.txt', 'gradle_inventory_sha256')]:
            require(digest(directory / f'{replica}-{filename}') == record.get(field), 'unsigned replica evidence changed')
            if replica == 'a':
                require(record.get(field) == candidate.get(field), 'candidate evidence differs from first replica')
        advisory = load(directory / f'{replica}-advisories.json')
        require(advisory.get('queries') == queries and advisory.get('status') == 'NO_KNOWN_FINDINGS' and advisory.get('findings') == [],
                'unsigned advisory evidence not clear')
    return candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True, help='directory of downloaded signed candidate evidence')
    parser.add_argument('--expected-sha', required=True)
    parser.add_argument('--expected-cert', required=True)
    parser.add_argument('--matrix', type=Path, required=True)
    parser.add_argument('--evidence-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        actual = identity(ROOT, args.expected_sha)
        candidate = verify_candidate(args.candidate, actual, args.expected_cert)
        print(json.dumps(verify_matrix(candidate, load(args.matrix), args.evidence_dir), indent=2, sort_keys=True))
        return 0
    except (Refused, OSError, ValueError, TypeError, KeyError, AttributeError):
        print('R12_REVIEW_REFUSED: missing, stale or inconsistent evidence', file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
