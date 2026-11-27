#!/usr/bin/env python3
"""Full R04 consolidated acceptance contracts. Not physical-device proof."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = (
 'lib/services/r04_github_actions.dart',
 'lib/components/generated_form_renderer.dart',
 'lib/services/r04_actions_history_catalog.dart',
 'lib/services/r04_actions_redirect_policy.dart',
 'lib/services/r04_actions_archive_integrity.dart',
 'lib/app_sources/github.dart',
 'lib/providers/source_provider.dart',
 'lib/providers/apps_provider_install.dart',
 'lib/widgets/r04_actions_history_dialog.dart',
 'test/r04_actions_history_test.dart',
 'test/r04_generated_form_patch_test.dart',
 'test/r04_actions_redirect_policy_test.dart',
 '.github/workflows/obtainx-r00-flutter.yml',
 '.github/workflows/obtainx-r00-contracts.yml',
 'scripts/ci/obtainx_ci_policy.py',
 'docs/R04_ACTIONS_CHANNEL.md',
 'scripts/ci/r04_live_acceptance.py',
 '.github/workflows/obtainx-r02-api36.yml',
 '.github/workflows/obtainx-r02-rt02.yml',
 '.github/workflows/obtainx-r02-rt02b.yml',
 '.github/workflows/obtainx-r02-rt02c.yml',
 'test/r04_archive_integrity_test.dart',
 'config/delivery-required-ci.json',
)

def verify(root: Path = ROOT) -> int:
    def src(path: str) -> str:
        return (root / path).read_text(encoding='utf-8')
    try:
        data={p:src(p) for p in FILES}
    except (FileNotFoundError, UnicodeError) as ex:
        print('OX_R04_FINAL_REFUSED missing/non-UTF8 source:',ex)
        return 1
    failures=[]
    def require(path: str, markers: tuple[str,...]) -> None:
        for marker in markers:
            if marker not in data[path]:
                failures.append(f'{path}: missing {marker}')
    require('lib/components/generated_form_renderer.dart', (
      'formInputs[r][e] = KeyedSubtree(',
      'patches.containsKey(item.key)',
      "key: ValueKey('r04-assist-",
      'value: values[item.key]',
    ))
    require('test/r04_generated_form_patch_test.dart', (
      "seen['r04GitHubSourceMode'], 'actions'",
      "seen['r04RunId'], '42'",
      "find.text('Actions'), findsWidgets",
    ))
    require(FILES[0], (
      "part 'r04_actions_history_catalog.dart';",
      'String? runAttempt,', 'String? commitSha,', 'String? artifactId,',
      "throw const R04ActionsFailure('invalid selected artifact ID');",
      'selectedArtifactId != null && id != selectedArtifactId',
      'run attempt changed after manual selection',
      'commit SHA changed after manual selection',
      'artifact run/commit provenance changed',
      "raw['expired'] != false", "!expires.isAfter(current)",
    ))
    require(FILES[2], (
      "part of 'r04_github_actions.dart';", 'Future<List<R04ActionsHistoryItem>> history(',
      'run not successful; not installable', 'no installable Android archive in run',
      "reason == 'eligible'", 'raw[\'expired\'] == false',
      'isCandidateName(artifactName)', "owner['head_sha'] == commit",
      'archiveSha256', 'maxRuns > 30',
    ))
    require(FILES[3], (
      'r04IsCanonicalArtifactDownload', 'r04ValidateArtifactRedirect',
      'r04ArtifactStorageHeaders', 'uri.scheme == \'https\'',
      ".endsWith('.blob.core.windows.net')", '.actions.githubusercontent.com',
      'HttpHeaders.acceptHeader: \'application/octet-stream\'',
      'crossOriginDownloadHeaders(original)',
    ))
    require(FILES[4], (
      'verifyR04ActionsArchiveBeforeExtraction(', 'sha256.bind(archive.openRead())',
      'if (actual != expected)', 'await archive.delete()',
      'runAttempt is! int', 'artifactId is! int',
      "rawEvidence['expiresAt']",
      'expiresAt == null || !expiresAt.isAfter(now.toUtc())',
    ))
    require(FILES[5], (
      'r04ArtifactIdKey', 'r04RunAttemptKey', 'r04CommitShaKey',
      'assistAction: _browseR04ActionsHistory',
      'R04ActionsHistoryDialog(', '.history(branch: branch, workflow: workflow)',
      'r04SourceModeKey: r04ModeActions', 'r04ArtifactFilterKey: \'\'',
      'artifactId: additionalSettings[r04ArtifactIdKey]',
      'runAttempt: additionalSettings[r04RunAttemptKey]',
      'commitSha: additionalSettings[r04CommitShaKey]',
      "headers[HttpHeaders.acceptHeader] = 'application/vnd.github+json';",
      "'application/vnd.github+json'", "'X-GitHub-Api-Version'",
      'Actions source requires direct HTTPS and certificate validation',
      'if (archive.archiveSha256 == null)', 'r04ActionsArchiveEvidenceKey',
      "'expiresAt': archive.expiresAt.toUtc().toIso8601String()",
    ))
    require(FILES[6], (
      'r04IsCanonicalArtifactDownload(currentUrl)',
      'r04ArtifactStorageHeaders(requestHeaders)',
      'r04ValidateArtifactRedirect(currentUrl, nextUrl)',
      'r04StorageHop = true',
      'request.cookies.addAll(cookies)',
    ))
    require(FILES[7], (
      'await verifyR04ActionsArchiveBeforeExtraction(',
      'allowInsecure: app.additionalSettings[GitHub.r04SourceModeKey]',
      'GitHub.r04ModeActions ||',
    ))
    # The GitHub artifact ZIP must be hashed BEFORE archive extraction.
    production_start = data[FILES[7]].find('Future<Object> downloadApp(')
    verify_position = data[FILES[7]].find('await verifyR04ActionsArchiveBeforeExtraction(', production_start)
    extract_position = data[FILES[7]].find('final artifactFormat = installArtifactFormat(', production_start)
    if verify_position < 0 or extract_position < 0 or verify_position > extract_position:
        failures.append('P02 digest gate must precede APK/archive extraction')
    require(FILES[8], (
      'Manual GitHub Actions history',
      'Only completed successful runs', 'row.canSelect',
      'No matching runs/artifacts', 'Navigator.of(context).pop(row)',
    ))
    if 'expired cached ZIP is refused after source receipt expiry' not in data['test/r04_archive_integrity_test.dart']:
        failures.append('missing pre-install expired receipt regression')
    if 'JSON persisted evidence remains source-bound across process restart' not in data['test/r04_archive_integrity_test.dart']:
        failures.append('missing process-restart receipt regression')
    require(FILES[9], (
      'failed and in-progress runs are visible but never selectable',
      'duplicate archive names', 'changed attempt, SHA and branch',
      'manual browser labels non-installable entries',
    ))
    require(FILES[11], (
      'PAT, cookie, proxy auth and custom secrets never reach artifact host',
      'signed object-store HTTPS redirects accepted',
    ))
    require(FILES[12], (
      'flutter test --no-pub test/r04_actions_history_test.dart',
      'flutter test --no-pub test/r04_generated_form_patch_test.dart',
      'flutter test --no-pub test/r04_actions_redirect_policy_test.dart',
      'flutter test --no-pub test/r04_archive_integrity_test.dart',
    ))
    require(FILES[13], ('python3 -B scripts/ci/r04_completion_contract.py --check',))
    require(FILES[14], ("'lib/providers/source_provider.dart'", "'lib/services/r04_*'"))
    require(FILES[15], ('R04 consolidated completion overlay', 'NOT_QUALIFIED', 'R05'))
    require(FILES[16], (
      "'state':'LIVE_METADATA_CHECKED_NOT_DEVICE_QUALIFIED'",
      'def trusted_storage_url(url: str) -> bool:',
      "'Authorization': 'Bearer '+token",
      "headers=api_headers if hop==0 else {'Accept':'application/octet-stream'}",
      'urllib.parse.urlencode(', 'run_attempt: int | None',
      'O_NOFOLLOW',
      'def verify_download(', 'receipt[\'zip_sha256\']',
      'APK signing', 'GitHub API unavailable, unauthorized or throttled',
      "'physical_install':'NOT_QUALIFIED'",
    ))
    for path in FILES[17:21]:
        require(path, ("scripts/ci/obtainx_ci_policy.py plan --head", "ready_for_review, converted_to_draft"))
    # This must be committed before Devtool delivery CI. Never infer a
    # required set from observed runs or mark release qualification complete.
    try:
        policy=json.loads(data['config/delivery-required-ci.json'])
        expected={
          'ObtainX R00 / Source and Contract Integrity':413437262,
          'ObtainX R00 / Hosted Flutter Qualification':413437265,
          'ObtainX R02 / API 36 Hosted Emulator Bootstrap':413666807,
          'ObtainX R02 / RT02 Real System Installer API36':413864665,
          'ObtainX R02 / RT02B Negative Installer API36':414136383,
          'ObtainX R02 / RT02C Archive-to-Installer API36':414158361,
        }
        req=policy.get('required_workflows') if isinstance(policy,dict) else None
        actual={x['name']:x['workflow_id'] for x in req} if isinstance(req,list) and all(
            isinstance(x,dict) and set(x)=={'name','workflow_id'} and
            isinstance(x['name'],str) and type(x['workflow_id']) is int for x in req
        ) else None
        if (not isinstance(policy,dict) or set(policy)!={
              'schema_version','repository','base_branch','event',
              'required_workflows','release_qualification'} or
            policy.get('schema_version') != 1 or
            policy.get('repository') != 'Mikeyphw/ObtainX' or
            policy.get('base_branch') !=
              'main' or
            policy.get('event') != 'pull_request' or
            policy.get('release_qualification') != 'separate' or
            len(req or ()) != len(expected) or actual != expected):
            failures.append('committed native Devtool required-CI policy mismatch')
    except (ValueError,TypeError,KeyError):
        failures.append('committed native Devtool CI policy must be valid strict JSON')
    if failures:
        for problem in failures:
            print('OX_R04_FINAL_REFUSED '+problem, flush=True)
        return 1
    print('OX_R04_COMPLETE_SOURCE_CONTRACT_PASS',flush=True)
    return 0

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--root',type=Path,default=ROOT)
    options=parser.parse_args()
    raise SystemExit(verify(options.root))
