#!/usr/bin/env python3
"""ObtainX OPT07 PR scope router: exact baseline impact vs full Android gates.

Inspired by AuroraStore-Standalone's targeted+full gate split. Unlike Aurora's
integrated master branch, ObtainX has stacked PRs, so use a separately verified full baseline and exact HEAD.
A skipped heavy workflow is NOT runtime qualification.
"""
from __future__ import annotations
import argparse
import hashlib
import fnmatch
import json
import re
import subprocess
import sys
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHA = re.compile(r'^[0-9a-f]{40}$')
RISK_GLOBS = (
    'lib/http/linked_changelog_policy.dart',
    'lib/services/diagnostic_redaction.dart',
    'lib/custom_errors.dart',
    'lib/providers/logs_provider.dart',
    'lib/services/diagnostic_snapshot.dart',
    'test/final_audit_01_*',
    'scripts/ci/*final_audit_01*',
    'scripts/ci/r12_device_evidence.py',
    'lib/installers/**',
    'lib/providers/apps_provider_install.dart',
    'lib/widgets/r07_*',
    'lib/widgets/r05_*',
    'lib/pages/app.dart',
    'lib/components/r06_*',
    'test/r06_*',
    'scripts/ci/r06_*',
    'lib/providers/apps_provider.dart',
    'lib/providers/source_provider.dart',
    'lib/components/generated_form_renderer.dart',
    'lib/services/r03_*',
    'lib/services/r04_*',
    'lib/services/r07_*',
    'lib/services/r05_*',
    'lib/app_sources/github.dart',
    'test/r04_*',
    'test/r07_*',
    'test/r05_*',
    'scripts/ci/r04_*',
    'scripts/ci/r07_*',
    'lib/version/**',
    'lib/app_sources/**',
    'lib/http/r08_*',
    'lib/services/r08_*',
    'lib/pages/home.dart',
    'lib/components/version_regex_assist_dialog.dart',
    'test/r08_*',
    'scripts/ci/r08_*',
    'scripts/ci/test_r08_*',
    'lib/pages/apps.dart',
    'lib/providers/settings_provider.dart',
    'lib/folders/**',
    'lib/components/bulk_update_sheet.dart',
    'lib/components/app_detail_widgets.dart',
    'lib/pages/additional_options_page.dart',
    'lib/widgets/r04_actions_history_dialog.dart',
    'lib/services/r11_*',
    'lib/widgets/r11_*',
    'test/r11_*',
    'scripts/ci/test_r11_*',
    'lib/services/r09_*',
    'test/r09_*',
    'scripts/ci/r09_*',
    'scripts/ci/test_r09_*',
    'assets/translations/en.json',
    'scripts/ci/r05_*',
    'test/r03_*',
    'scripts/ci/r03_*',

    'lib/providers/apps_provider_updates.dart',
    'lib/providers/installer_provider.dart',
    'lib/providers/external_install_bridge.dart',
    'lib/services/install_bundle_plan.dart',
    'lib/services/verified_obb_delivery.dart',
    'lib/services/artifact_file_work.dart',
    'integration_test/**',
    'android/**',
    'packages/obtainx_native_evidence/**',
    '.github/workflows/**',
    'scripts/ci/r02_rt02**',
    'scripts/ci/r02f_p02_*',
    'scripts/ci/r02f_p03_*',
    'scripts/ci/r02f_p04b_*',
    'scripts/ci/r02f_p04_*',
    'lib/services/r02f_p04_backend_availability.dart',
    'scripts/ci/r02f_p05_*',
    'lib/services/r02f_p05_*',
    'test/r02f_p05_*',
    'scripts/ci/r02_final_*',
    'lib/services/r02_local_*',
    'test/r02_local_*',
    'scripts/ci/r02g_*',
    'scripts/ci/r02_sdk_retry.py',
    'scripts/ci/obtainx_ci_policy.py',
    'scripts/ci/*optimization*',
    'scripts/ci/obtainx_ci_optimization_opt03_apk_cache.py',
    'scripts/ci/test_obtainx_ci_optimization_opt03_cache.py',
    'scripts/ci/r00_source_contract.py',
    'pubspec.yaml',
    'pubspec.lock',
    'docs/SECURITY_RELEASE_POLICY.md',
)

def classify(paths: list[str], *, force: bool = False) -> dict:
    if not paths and not force:
        raise ValueError('empty change inventory cannot be marked safe')
    if any(not p or p.startswith('/') or '\\' in p or p.split('/').count('..')
           for p in paths):
        raise ValueError('invalid changed-file inventory')
    risky = sorted(p for p in paths if any(fnmatch.fnmatchcase(p, g) for g in RISK_GLOBS))
    dart = sorted(p for p in paths if p.endswith('.dart') and p.startswith(('lib/', 'test/', 'integration_test/')))
    unknown = sorted(p for p in paths if p.startswith('.github/') and not p.startswith('.github/workflows/'))
    # Unknown configuration is conservative; never accidentally skip compilation.
    full = bool(force or risky or unknown)
    targeted = bool(dart) and not full
    return {'full_flutter':full,'targeted_flutter':targeted,'source_contracts':True,
            'risk_paths':risky + unknown,'changed_files':len(paths),
            'reason':'manual' if force else ('high-risk' if full else ('dart-targeted' if targeted else 'source-only'))}

def run_git(*args: str, root: Path = ROOT) -> bytes:
    p = subprocess.run(['git', *args],cwd=root,stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    if p.returncode:
        raise RuntimeError('CI_SCOPE_REFUSED: git command failed: ' + ' '.join(args[:2]))
    return p.stdout

def paths_between(base: str, head: str, *, root: Path = ROOT) -> list[str]:
    if not SHA.fullmatch(base) or not SHA.fullmatch(head) or base == head:
        raise ValueError('CI_SCOPE_REFUSED: invalid or identical source SHAs')
    actual=run_git('rev-parse','HEAD',root=root).decode().strip()
    if actual != head:
        raise RuntimeError('CI_SCOPE_REFUSED: checkout not exact expected HEAD')
    run_git('merge-base','--is-ancestor',base,head,root=root)
    raw=run_git('diff','--name-only','-z','--no-renames',base,head,root=root)
    paths=[x.decode('utf8','strict') for x in raw.split(b'\0') if x]
    if not paths:
        raise RuntimeError('CI_SCOPE_REFUSED: no changed files')
    return paths

REPO = 'Mikeyphw/ObtainX'
REPO_ID = 1452827884
LANES = ('api36', 'rt02', 'rt02b', 'rt02c')
BASELINE_PATH = 'config/ci-incremental-baseline.json'
# Job and decisive step identities, not just a green workflow badge.
FULL_PROOFS = {
    'source': (413437262, 'source-contracts', ('Run bootstrap regression tests', 'Enforce bounded CI optimization and dev-only qualification guard')),
    'flutter': (413437265, 'flutter-and-android-debug', ('Analyze current source and tests', 'Execute full Flutter test suite', 'Compile unsigned debug Android APK')),
    'api36': (413666807, 'emulator-api36', ('Install and launch ObtainX on disposable API 36 emulator', 'Independently verify source-bound installed APK and launch evidence')),
    'rt02': (413864665, 'rt02-real-install', ('Real Android standalone and split install sessions', 'Independently verify exact source-bound RT02 receipts')),
    'rt02b': (414136383, 'rt02b-negative-install', ('Real Android wrong-signature and downgrade rejection sessions', 'Independently verify negative Android package-state receipts')),
    'rt02c': (414158361, 'rt02c-archive-install', ('Real Android archive update sessions and two extraction refusals', 'Independently verify archive-to-installer Android package-state receipts')),
}
DISCOVERY_TESTS = (
    'test/r09_discovery_test.dart', 'test/needs_attention_group_test.dart',
    'test/app_visibility_filter_test.dart', 'test/category_filter_test.dart',
    'test/multi_source_app_actions_test.dart', 'test/apps_scroll_work_test.dart',
    'test/update_status_grouping_test.dart', 'test/app_listing_key_test.dart',
)
ACTIONS_TESTS = (
    'test/r04_github_actions_test.dart', 'test/r04_archive_integrity_test.dart',
    'test/r04_actions_redirect_policy_test.dart', 'test/r04_actions_history_test.dart',
    'test/r04_generated_form_patch_test.dart', 'test/source_provider_test.dart',
)
# Closed-world narrowly understood impact groups. Shared production surfaces
# use broader gates. Paths not covered here are deliberately FULL.
SETTINGS_TESTS = (
    'test/r10_settings_navigation_test.dart', 'test/about_headline_fit_test.dart',
    'test/locale_resolution_test.dart', 'test/app_ui_scaling_test.dart',
    'test/settings_provider_theme_accent_test.dart', 'test/bg_check_scheduling_test.dart',
    'test/performance_recorder_test.dart',
    'test/r10_settings_context_test.dart', 'test/r10_regex_preview_test.dart',
    'test/version_regex_assist_sheet_layout_test.dart', 'test/r10_accessibility_test.dart', 'test/app_dropdown_field_test.dart',
)
RULES = (
    (('lib/pages/settings.dart', 'lib/widgets/r10_settings_navigation.dart',
      'scripts/ci/test_r10_settings_contract.py', 'lib/components/r10_settings_context.dart',
      'lib/components/r10_regex_preview.dart', 'lib/components/version_regex_assist_dialog.dart',
      'scripts/ci/test_r10_settings_context_contract.py'), SETTINGS_TESTS, ()),
    (('lib/pages/apps.dart', 'lib/folders/**', 'lib/components/bulk_update_sheet.dart', 'lib/services/r09_discovery.dart'), DISCOVERY_TESTS, ()),
    (('lib/widgets/r04_actions_history_dialog.dart', 'lib/services/r04_actions_history_catalog.dart', 'lib/components/generated_form_renderer.dart', 'lib/pages/add_app.dart', 'lib/pages/additional_options_page.dart'), ACTIONS_TESTS + DISCOVERY_TESTS + SETTINGS_TESTS, ()),
    (('lib/services/r04_actions_archive_integrity.dart', 'lib/app_sources/github.dart'), ACTIONS_TESTS + DISCOVERY_TESTS, ('rt02c',)),
    (('lib/components/app_detail_widgets.dart',), ACTIONS_TESTS + DISCOVERY_TESTS + ('test/r06_app_details_test.dart', 'test/app_bottom_sheet_test.dart'), ('api36', 'rt02c')),
    (('lib/providers/settings_provider.dart',), DISCOVERY_TESTS + ('test/settings_provider_theme_accent_test.dart','test/bg_check_scheduling_test.dart'), ('api36',)),
    (('assets/translations/*.json',), DISCOVERY_TESTS + SETTINGS_TESTS, ()),
    (('lib/providers/apps_provider_install.dart', 'lib/installers/**', 'lib/services/install_bundle_plan.dart', 'lib/services/artifact_file_work.dart', 'lib/services/verified_obb_delivery.dart'), ACTIONS_TESTS + DISCOVERY_TESTS + ('test/r02_install_bundle_plan_test.dart','test/r05_operation_receipt_test.dart','test/r05_operation_journal_test.dart','test/archive_extraction_security_test.dart','test/r02f_external_handoff_test.dart'), LANES),
    (('lib/services/r03_*',), ('test/r03_download_engine_test.dart',), ('rt02c',)),
    (('lib/services/r07_*', 'lib/widgets/r07_*'), ('test/r07_activity_center_test.dart','test/r05_operation_journal_test.dart','test/r07_operation_timeline_test.dart','test/r03_download_history_test.dart','test/multi_source_app_actions_test.dart','test/r03_download_engine_test.dart'), LANES),
    (('lib/version/**', 'lib/services/r08_*', 'lib/http/r08_*'), ('test/r08_source_regressions_test.dart','test/version_engine_test.dart','test/source_provider_test.dart'), ()),
)


def git(*args, root=ROOT):
    return run_git(*args, root=root).decode('utf8','strict')


def changes(base, head, root=ROOT):
    return sorted(set(paths_between(base,head,root=root)))


def read_api(path):
    token = os.environ.get('OX_SCOPE_TOKEN','')
    if not token:
        raise ValueError('baseline proof credentials unavailable')
    if not re.fullmatch(r'/actions/(?:runs/[0-9]+(?:/attempts/[0-9]+/jobs\?per_page=100)?|workflows/[0-9]+/runs\?head_sha=[a-f0-9]{40}&event=pull_request&per_page=50|workflows/[0-9]+/runs\?event=pull_request&status=success&per_page=30)',path):
        raise ValueError('unexpected proof endpoint')
    url = 'https://api.github.com/repos/'+REPO+path
    req = urllib.request.Request(url, headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'ObtainX-OPT07'})
    # No credentialed cross-origin redirect: the selected API endpoints do not redirect.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=8) as response:
        return json.loads(response.read(2_000_000))


def run_identity(row, workflow, source):
    return (row.get('workflow_id') == workflow and row.get('head_sha') == source
            and row.get('event') == 'pull_request' and row.get('status') == 'completed'
            and row.get('conclusion') == 'success'
            and row.get('repository',{}).get('id') == REPO_ID
            and row.get('head_repository',{}).get('id') == REPO_ID
            and type(row.get('id')) is int and type(row.get('run_attempt')) is int
            and row['run_attempt'] >= 1)


def full_job_proof(jobs, job_name, decisive):
    matched = [j for j in jobs if j.get('name') == job_name]
    if len(matched) != 1 or matched[0].get('conclusion') != 'success':
        return False
    steps = matched[0].get('steps') or []
    return all(sum(s.get('name') == name and s.get('conclusion') == 'success' for s in steps) == 1 for name in decisive)


def verify_baseline(pin, api=read_api):
    source = pin.get('source_sha','')
    runs = pin.get('runs')
    if pin.get('schema') != 1 or pin.get('repository') != REPO or not SHA.fullmatch(source) or not isinstance(runs,dict) or set(runs) != set(FULL_PROOFS):
        return False
    for lane, (workflow,job,steps) in FULL_PROOFS.items():
        run = runs[lane]
        if type(run) is not int or run <= 0:
            return False
        row = api(f'/actions/runs/{run}')
        if row.get('id') != run or not run_identity(row,workflow,source):
            return False
        jobs = api(f'/actions/runs/{run}/attempts/{row["run_attempt"]}/jobs?per_page=100')
        if jobs.get('total_count') != len(jobs.get('jobs',[])) or not full_job_proof(jobs['jobs'],job,steps):
            return False
    return True


def discover_baseline(head, pin, root=ROOT, api=read_api):
    """Choose a recent, exact full ancestor, never a merely green scoped run.

    The source workflow is deliberately red for scoped development, so its
    successful run history bounds discovery. Every other workflow still needs
    independent decisive-step evidence. Limit API work and fall back safely.
    """
    candidate_rows=api('/actions/workflows/413437262/runs?event=pull_request&status=success&per_page=30').get('workflow_runs',[])
    ancestry=set(git('rev-list','--first-parent','--max-count=128',head,root=root).splitlines())
    ancestry.discard(head)
    checked=set()
    for row in candidate_rows:
        source=row.get('head_sha','')
        if source in checked or source not in ancestry or source==pin.get('source_sha') or not run_identity(row,413437262,source):
            continue
        checked.add(source)
        if len(checked)>3:break
        try:
            runs={'source':row['id']}
            for lane,(workflow,job,steps) in FULL_PROOFS.items():
                if lane=='source':continue
                candidates=api(f'/actions/workflows/{workflow}/runs?head_sha={source}&event=pull_request&per_page=50').get('workflow_runs',[])
                matched=next((r for r in candidates if run_identity(r,workflow,source)),None)
                if matched is None:raise ValueError('candidate full lane missing')
                runs[lane]=matched['id']
            candidate={'schema':1,'repository':REPO,'source_sha':source,'runs':runs}
            if verify_baseline(candidate,api):return candidate
        except (OSError,ValueError,KeyError,TypeError,AttributeError,RuntimeError,urllib.error.URLError):
            continue
    if verify_baseline(pin,api):return pin
    raise ValueError('no verified full baseline')


def policy_migration(head,root=ROOT):
    # All jobs independently compute this exact first-parent change inventory.
    # It is deterministic and independent of live API observations; it cannot
    # turn a partially deferred run into full qualification.
    parent=git('rev-parse',head+'^',root=root).strip()
    return any(p.startswith('.github/workflows/') or p=='scripts/ci/obtainx_ci_policy.py' or p.startswith('scripts/ci/obtainx_ci_optimization_contract') for p in changes(parent,head,root=root))


def requested_mode(event_name, event):
    if event_name != 'pull_request':
        return 'full'
    pr = event.get('pull_request',{})
    labels = {x.get('name') for x in pr.get('labels',[]) if isinstance(x,dict)}
    # Legacy explicit development-only still prevents full qualification.
    if 'ci:development-only' in labels:
        return 'scoped'
    # Review readiness is not a qualification input. Normal drafts execute
    # the same full gate as ready PRs; only an explicit development label
    # may request scoped, non-accepting feedback.
    return 'full'


def full_plan(mode, head, reason, base=None, paths=()):
    return {'schema':'obtainx.ci-scope.v1','mode':mode,'head':head,'baseline':base,'reason':reason,
            'paths':list(paths),'full_flutter':True,'targeted_flutter':False,'tests':[],
            'lanes':dict.fromkeys(LANES,True),'full_acceptance_possible':mode=='full'}


def impact(paths, head, base, root=ROOT):
    classify(list(paths))  # Validate existing conservative risk inventory.
    tests=set(); lanes=set()
    for path in paths:
        if path == BASELINE_PATH or (path.startswith('docs/') and path != 'docs/SECURITY_RELEASE_POLICY.md'):
            continue
        if path.startswith('test/') and path.endswith('_test.dart') and (root/path).is_file():
            tests.add(path);continue
        hits=[(cases,runtime) for patterns,cases,runtime in RULES if any(fnmatch.fnmatchcase(path,g) for g in patterns)]
        if not hits:
            return full_plan('scoped',head,'uncertain-or-shared-impact:'+path,base,paths)
        for cases,runtime in hits:
            tests.update(cases); lanes.update(runtime)
    if any(not (root/test).is_file() for test in tests):
        return full_plan('scoped',head,'mapped-test-unavailable',base,paths)
    return {'schema':'obtainx.ci-scope.v1','mode':'scoped','head':head,'baseline':base,
            'reason':'verified-baseline-impact','paths':list(paths),'full_flutter':False,
            'targeted_flutter':bool(tests),'tests':sorted(tests),'lanes':{x:x in lanes for x in LANES},'full_acceptance_possible':False}


def plan(head,event_name,event,*,root=ROOT,api=read_api):
    if not SHA.fullmatch(head or '') or git('rev-parse','HEAD',root=root).strip()!=head:
        raise ValueError('checkout not exact expected HEAD')
    mode=requested_mode(event_name,event)
    if mode=='full':
        return full_plan(mode,head,'full-unless-explicit-development-only')
    try:
        pr=event['pull_request']
        if pr['head']['sha']!=head or pr['head']['repo']['id']!=REPO_ID or pr['base']['repo']['id']!=REPO_ID or pr['base']['ref']!='main':
            raise ValueError('PR identity mismatch')
        pin=json.loads((root/BASELINE_PATH).read_text(encoding='utf8'))
        git('merge-base','--is-ancestor',pr['base']['sha'],head,root=root)
        pin=discover_baseline(head,pin,root=root,api=api)
        base=pin['source_sha']
        paths=changes(base,head,root=root)
        selected=impact(paths,head,base,root=root)
        return selected
    except (OSError,ValueError,TypeError,KeyError,subprocess.SubprocessError,RuntimeError,AttributeError,urllib.error.URLError):
        return full_plan(mode,head,'unverified-baseline-or-ancestry')


def plan_digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()


def outputs(value,path):
    scalars={'plan_digest':plan_digest(value),'mode':value['mode'],'full_flutter':value['full_flutter'],'targeted_flutter':value['targeted_flutter'],**value['lanes']}
    with open(path,'a',encoding='utf8') as f:
        for k,v in scalars.items():f.write(f'{k}={str(v).lower()}\n')
        encoded=json.dumps(value,separators=(',',':'),ensure_ascii=True)
        if len(encoded)>200_000:raise ValueError('scope plan exceeds output bound')
        f.write('plan='+encoded+'\n')


def run_targeted(value,head):
    if value.get('head')!=head or value.get('mode')!='scoped' or value.get('full_flutter') is not False or value.get('targeted_flutter') is not True:
        raise ValueError('invalid targeted plan')
    tests=value.get('tests')
    if not tests or any(not re.fullmatch(r'test/[A-Za-z0-9_./-]+_test\.dart',p) or '..' in p.split('/') or not (ROOT/p).is_file() for p in tests):
        raise ValueError('invalid targeted tests')
    subprocess.run(['flutter','analyze','lib','test','integration_test'],check=True)
    subprocess.run(['flutter','test','--no-pub',*sorted(set(tests))],check=True)
    print('OX_CI_SCOPED_FLUTTER_PASS; FULL_ACCEPTANCE_NOT_ESTABLISHED',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['plan','run-flutter']);p.add_argument('--head',required=True);p.add_argument('--github-output');p.add_argument('--event-file',default=os.environ.get('GITHUB_EVENT_PATH'));p.add_argument('--event-name',default=os.environ.get('GITHUB_EVENT_NAME'));p.add_argument('--plan-json',default=os.environ.get('OX_SCOPE_PLAN'));a=p.parse_args()
    if a.command=='run-flutter':
        if git('rev-parse','HEAD').strip()!=a.head:raise ValueError('checkout mismatch')
        run_targeted(json.loads(a.plan_json),a.head);return 0
    event=json.loads(Path(a.event_file).read_text(encoding='utf8'))
    value=plan(a.head,a.event_name,event)
    print('OX_CI_SCOPE_PLAN '+json.dumps(value,sort_keys=True),flush=True)
    if a.github_output:outputs(value,a.github_output)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf8') as f:
            f.write('### OPT07 '+value['mode']+' qualification\n\nSource: `'+a.head+'`\n\nBaseline: `'+str(value['baseline'])+'`\n\nReason: '+value['reason']+'\n\n')
            for lane,run in value['lanes'].items():f.write('- '+lane+': '+('SELECTED' if run else 'DEFERRED (not qualified)')+'\n')
            f.write('\nFull acceptance possible: '+str(value['full_acceptance_possible'])+'\n')
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,TypeError,KeyError,RuntimeError,subprocess.SubprocessError) as exc:
        print('OX_CI_SCOPE_REFUSED '+type(exc).__name__,file=sys.stderr);raise SystemExit(1)
