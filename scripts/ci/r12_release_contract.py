"""Source contract for the separately authorized R12 candidate lane."""
from pathlib import Path
import re
import yaml
from r07_workflow_contract import UniqueLoader

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = '.github/workflows/obtainx-r12-candidate.yml'


def inspect_workflow(text):
    doc = yaml.load(text, Loader=UniqueLoader)
    if not isinstance(doc, dict):
        raise ValueError('not a mapping')
    errors = []
    def check(ok, reason):
        if not ok:
            errors.append(reason)
    check(set(doc.get('on', {})) == {'workflow_dispatch'}, 'manual only')
    check(doc.get('permissions') == {'contents': 'read', 'actions': 'read', 'pull-requests': 'read'}, 'read-only token')
    check(doc.get('env') == {'OX_EXPECTED_SHA': '${{ inputs.source_sha }}'}, 'exact reviewed source input')
    jobs = doc.get('jobs', {})
    check(set(jobs) == {'authorize', 'build', 'sign-candidate'}, 'authorize, build and isolated signing only')
    for name, job in jobs.items():
        check('if' not in job, 'wrong-source dispatch must fail, not skip')
        check('permissions' not in job and 'env' not in job, 'no job credential override')
        check(job.get('runs-on') == 'ubuntu-24.04', 'disposable hosted runner only')
        steps = job.get('steps', [])
        if len(steps) < 2:
            errors.append('missing checkout and guard'); continue
        check(steps[0].get('uses', '').startswith('actions/checkout@') and steps[0].get('with', {}).get('ref') == '${{ github.sha }}' and steps[0].get('with', {}).get('persist-credentials') is False, 'pinned checkout with no retained credentials')
        check(steps[1].get('run') == 'python3 -B scripts/ci/r12_release_gate.py preflight --head "$OX_EXPECTED_SHA"', 'mandatory preflight immediately after checkout')
        for step in steps:
            check('if' not in step and not step.get('continue-on-error', False), 'no bypassable candidate gates')
            if 'uses' in step:
                check(bool(re.fullmatch(r'(?:actions/(?:checkout|setup-java|upload-artifact)|subosito/flutter-action)@[a-f0-9]{40}', step['uses'])), 'action not approved/pinned')
            env = step.get('env', {})
            if 'secrets.' in str(env):
                check(name == 'sign-candidate' and step.get('name') == 'Compare independent builds and sign verified bytes only' and set(env) == {'OX_CI_READ_TOKEN', 'OX_RELEASE_KEYSTORE_B64', 'OX_RELEASE_STORE_PASSWORD', 'OX_RELEASE_KEY_PASSWORD', 'OX_RELEASE_KEY_ALIAS', 'OX_RELEASE_CERT_SHA256'}, 'secrets outside isolated signer')
        check(not re.search(r'gh\s+release|git\s+push|git\s+tag|pull_request_target', str(job)), 'publication/mutation forbidden')
    build = jobs.get('build', {}); sign = jobs.get('sign-candidate', {})
    check(build.get('needs') == 'authorize' and 'environment' not in build and build.get('strategy', {}).get('matrix') == {'replica': ['a', 'b']}, 'two independent unsigned builders')
    check(sign.get('needs') == 'build' and sign.get('environment') == 'obtainx-release-candidate', 'protected isolated signing dependency')
    check(text.count('r12_release_gate.py verify-environment --head') == 1 and 'Verify signing environment policy before building' in str(jobs.get('authorize')), 'environment protection verification before builders')
    check(text.count('secrets.') == 4, 'unexpected or missing signing secret reference')
    for required in ('bats scripts/ci/r12_shell.bats', 'shellcheck --shell=bash build.sh sign.sh', 'node --check assets/translations/standardize.mjs', 'node --test assets/translations/standardize.test.mjs', 'eslint@9.39.1', './gradlew --no-daemon lint test', 'flutter pub get --enforce-lockfile', 'dart format --output=none --set-exit-if-changed', 'flutter analyze --fatal-infos --fatal-warnings', 'flutter test --no-pub', 'flutter build apk --release --split-per-abi --flavor normal --no-pub', 'r12_release_gate.py record-ci', 'r12_release_gate.py record-build', 'r12_release_gate.py sign-candidate', 'normalReleaseRuntimeClasspath', 'GITHUB_RUN_ATTEMPT', 'if-no-files-found: error'):
        check(required in text, 'missing mandatory release gate: ' + required)
    return errors
