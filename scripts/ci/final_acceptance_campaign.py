#!/usr/bin/env python3
"""Exact-source acceptance orchestration, read-only apart from private evidence.

No release dispatch, APK install, signing, publication or automatic approval.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

# Explicit trusted sibling path when invoked with Python safe-path enabled.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import r12_release_gate as gate
import r12_device_evidence as device
import r04_live_acceptance as actions
import r02f_p05_physical_probe as physical

ROOT = gate.ROOT
CAMPAIGN = 'FINAL-ACCEPTANCE-01'
HISTORICAL_COUNT = 139

def audit_inventory(root=ROOT):
    historical = device.load(root / 'docs/FINAL_ACCEPTANCE_HISTORICAL.json')
    rows = historical['rows']
    gate.require(historical['schema'] == 'obtainx.final-acceptance.historical.v1' and
                 gate.HEX64.fullmatch(historical['historical_audit_sha256']) and
                 len(rows) == HISTORICAL_COUNT and len({r['id'] for r in rows}) == HISTORICAL_COUNT,
                 'historical promise inventory mismatch')
    tracked = set(gate.git('ls-files', root=root).splitlines())
    result = []
    for row in rows:
        refs = {}
        for path in row['tracked_reference_paths']:
            gate.require(path in tracked and not Path(path).is_absolute() and '..' not in Path(path).parts,
                         'historical reference missing or unsafe')
            refs[path] = gate.digest(root / path)
        result.append({'id': row['id'], 'promise': row['promise'], 'historical_implementation': row['implementation'],
                       'historical_acceptance': row['acceptance'], 'current_reference_digests': refs,
                       'review_status': 'PENDING_INDEPENDENT_PROMISE_REVIEW', 'historical_remaining': row['remaining']})
    return {'historical_source': historical['historical_source'], 'historical_tree': historical['historical_tree'],
            'historical_audit_sha256': historical['historical_audit_sha256'], 'rows': result,
            'original_promises': HISTORICAL_COUNT, 'current_acceptance': 'NOT_ESTABLISHED'}


def provider_inventory(root=ROOT):
    source = (root / 'lib/providers/source_provider.dart').read_text()
    factories = source.split('_sourceFactories = [', 1)[1].split('];', 1)[0]
    names = re.findall(r'\(\)\s*=>\s*(\w+)\(\)', factories)
    gate.require(len(names) > 0 and len(names) == len(set(names)) and names[-1] == 'HTML', 'source factory inventory unavailable')
    return {name: {'production_route': 'SourceProvider._sourceFactories', 'live_acceptance': 'PENDING_EXTERNAL'} for name in names}


# Provider cases are observed using the signed app, not inferred from an HTTP
# probe or a mock. Each provider has a distinct file-backed review record.
PROVIDER_CHECKS = {'discovery': 'VERIFIED', 'metadata': 'VERIFIED', 'artifact-integrity': 'VERIFIED'}

def provider_review(candidate, document, evidence_dir, root=ROOT):
    gate.require(document.get('schema') == 'obtainx.final-acceptance.providers.v1' and
                 all(document.get(k) == candidate[k] for k in ('repository', 'source_sha', 'source_tree', 'certificate_sha256')),
                 'provider matrix candidate binding mismatch')
    rows = document.get('providers')
    expected = provider_inventory(root)
    gate.require(isinstance(rows, dict) and set(rows) == set(expected), 'provider coverage mismatch')
    result = {}; names=set(); hashes=set()
    for name, row in sorted(rows.items()):
        status = row.get('status')
        gate.require(status in ('PASS', 'FAIL', 'PENDING_EXTERNAL', 'UNSUPPORTED'), 'unknown provider status')
        if status in ('PENDING_EXTERNAL', 'UNSUPPORTED'):
            gate.require(device.label(row.get('reason')) and 'observations' not in row, 'provider pending status contradictory')
            result[name] = status
            continue
        checks = dict(PROVIDER_CHECKS)
        # The reviewed fixture must specify whether authentication and rate
        # limits apply, with separate denial evidence; never infer support.
        for capability in ('authentication', 'rate-limit'):
            value = row.get(capability)
            gate.require(value in ('SUPPORTED', 'NOT_APPLICABLE_REVIEWED'), 'provider capability review missing')
            checks[capability] = 'REFUSED' if value == 'SUPPORTED' else 'VERIFIED_NOT_APPLICABLE'
        apk = row.get('apk'); apks = candidate['apks']
        gate.require(apk in apks and row.get('apk_sha256') == apks[apk]['sha256'] and
                     device.label(row.get('reviewer')) and row.get('authorized_fixture') is True,
                     'provider APK identity or approval missing')
        observed = row.get('observations')
        gate.require(isinstance(observed, dict) and set(observed) == set(checks), 'provider observation coverage incomplete')
        outcomes=[]
        for check, outcome in checks.items():
            proof = device.file_proof(evidence_dir, observed[check], names, hashes)
            item = device.load(proof, observed[check]['sha256'])
            gate.require(item.get('schema') == 'obtainx.final-acceptance.provider-observation.v1' and
                         all(item.get(k) == candidate[k] for k in ('repository','source_sha','source_tree','certificate_sha256')) and
                         item.get('provider') == name and item.get('check') == check and
                         item.get('expected_outcome') == outcome and item.get('outcome') in (outcome, 'ERROR', 'REFUSED') and
                         item.get('apk') == apk and item.get('apk_sha256') == row['apk_sha256'] and
                         item.get('reviewer') == row['reviewer'] and item.get('authorized_fixture') is True and
                         item.get('route') == 'PRODUCTION_SIGNED_APP', 'provider observation binding invalid')
            device.utc_timestamp(item.get('observed_utc'))
            installed = device.package_state(item.get('candidate_package_state'))
            gate.require(all(installed.get(k) == apks[apk][k] for k in ('package','version_code','certificate_sha256')) and
                         installed['apk_sha256'] == apks[apk]['sha256'], 'provider observed different app')
            if check == 'artifact-integrity' and item.get('outcome') == outcome:
                gate.require(gate.HEX64.fullmatch(str(item.get('advertised_sha256',''))) and
                             item.get('advertised_sha256') == item.get('downloaded_sha256'), 'artifact digest proof missing')
            attachments=item.get('attachments')
            gate.require(isinstance(attachments,list) and 1 <= len(attachments) <= 8 and
                         any(a.get('kind') in ('receipt','sanitized-log') for a in attachments), 'provider machine evidence missing')
            for attachment in attachments:
                gate.require(attachment.get('kind') in ('receipt','sanitized-log','review-note','screenshot'), 'invalid provider attachment')
                device.file_proof(evidence_dir,attachment,names,hashes)
            outcomes.append(item['outcome'] == outcome)
        gate.require((status == 'PASS') == all(outcomes), 'provider verdict contradicts evidence')
        result[name]='EVIDENCE_READY_FOR_INDEPENDENT_REVIEW' if status == 'PASS' else 'FAIL'
    return {'providers': result, 'live_provider_acceptance': 'PENDING_INDEPENDENT_REVIEW'}


def promise_review(ident, inventory, document, evidence_dir):
    gate.require(document.get('schema') == 'obtainx.final-acceptance.promise-review.v1' and
                 all(document.get(k) == ident[k] for k in ('repository','source_sha','source_tree')) and
                 document.get('historical_audit_sha256') == inventory['historical_audit_sha256'], 'promise review source binding mismatch')
    rows=document.get('promises'); known={r['id']:r for r in inventory['rows']}
    gate.require(isinstance(rows,dict) and set(rows)==set(known), 'promise review inventory incomplete')
    result={}; names=set(); hashes=set()
    for key,row in sorted(rows.items()):
        status=row.get('status')
        gate.require(status in ('PENDING','GAP','REVIEWED_SOURCE_SUBSET','REVIEWED_ACCEPTANCE_EVIDENCE'), 'unsupported promise verdict')
        if status=='PENDING':
            gate.require(device.label(row.get('reason')) and 'evidence' not in row, 'promise pending status contradictory')
        else:
            gate.require(row.get('current_reference_digests')==known[key]['current_reference_digests'] and
                         device.label(row.get('reviewer')) and device.label(row.get('reason')), 'promise review reference drift')
            device.utc_timestamp(row.get('observed_utc'))
            evidence=row.get('evidence')
            gate.require(isinstance(evidence,list) and 1<=len(evidence)<=8,'promise review proof missing')
            for item in evidence:
                device.file_proof(evidence_dir,item,names,hashes)
        result[key]=status
    return {'promises':result,'historical_acceptance':'PENDING_INDEPENDENT_REVIEW'}


def private_receipt(path, record):
    """Exclusive private output, no overwrites or following symlinks."""
    gate.require(path.parent.is_dir() and not path.parent.is_symlink() and
                 not any(p.is_symlink() for p in path.parent.parents), 'unsafe evidence directory')
    gate.require(path.parent.stat().st_uid == os.getuid() and path.parent.stat().st_mode & 0o077 == 0,
                 'evidence directory must be owned and private')
    data = (json.dumps(record, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    return hashlib.sha256(data).hexdigest()


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--head', required=True)
    p.add_argument('--receipt', type=Path, required=True)
    sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('plan')
    sub.add_parser('observe-ci')
    sub.add_parser('readiness')
    audit = sub.add_parser('audit')
    audit.add_argument('--review-file', type=Path)
    audit.add_argument('--evidence-dir', type=Path)
    live = sub.add_parser('provider')
    live.add_argument('--provider-repo', required=True)
    live.add_argument('--branch', required=True)
    live.add_argument('--workflow', required=True)
    live.add_argument('--run-id', required=True, type=int)
    live.add_argument('--run-attempt', required=True, type=int)
    live.add_argument('--artifact-id', required=True, type=int)
    live.add_argument('--provider-head', required=True)
    live.add_argument('--download-verify', action='store_true')
    prof = sub.add_parser('device-profile')
    prof.add_argument('--serial', required=True)
    prof.add_argument('--ack', required=True)
    review = sub.add_parser('review')
    review.add_argument('--candidate', type=Path, required=True)
    review.add_argument('--expected-cert', required=True)
    review.add_argument('--matrix', type=Path, required=True)
    review.add_argument('--evidence-dir', type=Path, required=True)
    review.add_argument('--provider-matrix', type=Path)
    review.add_argument('--provider-evidence-dir', type=Path)
    return p


def execute(args, ident):
    if args.action == 'plan':
        return {'providers': provider_inventory(), 'device_lanes': device.LANE_RULES,
                'historical_promises': audit_inventory()['original_promises'],
                'release_workflow': '.github/workflows/obtainx-r12-candidate.yml',
                'release_dispatch': 'SEPARATE_APPROVAL_REQUIRED'}
    if args.action == 'observe-ci':
        return {'ci': gate.hosted_ci(ident['source_sha'], ident['source_tree'])}
    if args.action == 'readiness':
        ci = gate.hosted_ci(ident['source_sha'], ident['source_tree'])
        # GitHub's environment policy is separate from actual protected-main
        # dispatch; a readable environment does not authorize a release.
        gate.verify_signing_environment()
        return {'ci': ci, 'environment_policy': 'VERIFIED', 'tracked_files_scanned': gate.source_scan(ROOT),
                'release_mode_build': 'NOT_RUN', 'independent_unsigned_builds': 'NOT_RUN',
                'license_review': 'PENDING', 'signing': 'NOT_AUTHORIZED'}
    if args.action == 'audit':
        inventory = audit_inventory()
        gate.require(bool(args.review_file) == bool(args.evidence_dir), 'promise review requires file and evidence directory')
        if args.review_file:
            return promise_review(ident, inventory, device.load(args.review_file), args.evidence_dir)
        return inventory
    if args.action == 'provider':
        gate.require(all(x > 0 for x in (args.run_id, args.run_attempt, args.artifact_id)) and
                     gate.HEX40.fullmatch(args.provider_head), 'exact provider identities required')
        proof = actions.probe(args.provider_repo, args.branch, args.workflow, args.run_id, args.artifact_id,
                              10, run_attempt=args.run_attempt, head_sha=args.provider_head)
        if args.download_verify:
            proof = actions.verify_download(proof)
            after = actions.probe(args.provider_repo, args.branch, args.workflow, args.run_id, args.artifact_id,
                                  10, run_attempt=args.run_attempt, head_sha=args.provider_head)
            gate.require(all(proof[k] == after[k] for k in after), 'provider identity changed during download')
        # Private provider identifiers never enter the terminal transcript.
        return {'provider': 'GitHub Actions', 'proof': proof, 'app_device_acceptance': 'PENDING_EXTERNAL'}
    if args.action == 'device-profile':
        return physical.profile(args.serial, args.ack)
    if args.action == 'review':
        candidate = device.verify_candidate(args.candidate, ident, args.expected_cert)
        # A cached candidate's CI record is evidence, not permission to use an
        # outdated or superseded run. Re-observe exact current main.
        current = gate.hosted_ci(ident['source_sha'], ident['source_tree'])
        gate.require(current == device.load(args.candidate / 'ci.json'), 'candidate CI provenance no longer current')
        gate.require(bool(args.provider_matrix) == bool(args.provider_evidence_dir), 'provider review requires matrix and evidence directory')
        providers = (provider_review(candidate, device.load(args.provider_matrix), args.provider_evidence_dir)
                     if args.provider_matrix else {'live_provider_acceptance': 'PENDING_EXTERNAL'})
        return {'candidate_sha256': gate.digest(args.candidate / 'candidate.json'),
                'matrix': device.verify_matrix(candidate, device.load(args.matrix), args.evidence_dir),
                'provider_matrix': providers}
    raise gate.Refused('unsupported campaign action')


def main():
    args = parser().parse_args()
    os.environ['GIT_NO_REPLACE_OBJECTS'] = '1'
    try:
        ident = gate.identity(ROOT, args.head)
        # Untracked import shadowing and dirty campaign inputs are forbidden.
        gate.require(not gate.git('status', '--porcelain', '--untracked-files=all', root=ROOT), 'campaign requires clean exact checkout')
        result = execute(args, ident)
        gate.require(gate.identity(ROOT, args.head) == ident, 'source changed during observation')
        record = dict(ident, schema='obtainx.final-acceptance.campaign.v1', campaign=CAMPAIGN,
                      action=args.action, observed_utc=datetime.now(timezone.utc).isoformat(), result=result,
                      device_acceptance='NOT_ESTABLISHED', release_qualified=False, publication_authorized=False)
        sha = private_receipt(args.receipt, record)
        print(json.dumps({'action': args.action, 'receipt_sha256': sha, 'state': 'EVIDENCE_RECORDED_NOT_FULL_ACCEPTANCE',
                          'release_qualified': False}, sort_keys=True, allow_nan=False))
        return 0
    except (RuntimeError, actions.Refused, OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.TimeoutExpired):
        print(json.dumps({'action': args.action, 'state': 'REFUSED_OR_UNAVAILABLE', 'release_qualified': False}, sort_keys=True))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
