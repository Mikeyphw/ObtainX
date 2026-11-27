#!/usr/bin/env python3
"""R12 non-publishing release qualification. No secret values are logged.

Builds and signing are separate jobs; this script never publishes or tags.
A candidate receipt is evidence of packaging only, not device/release approval.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import stat
import datetime
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import zipfile
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
REPO = 'Mikeyphw/ObtainX'
PACKAGE = 'dev.bikram.obtainx'
ABIS = {'x86_64': 1, 'armeabi-v7a': 2, 'arm64-v8a': 3}
HEX40 = re.compile(r'[0-9a-f]{40}\Z')
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
MAX_APK = 512 * 1024 * 1024
MAX_EXPANDED = 2 * 1024 * 1024 * 1024
SECRETS = ('OX_RELEASE_KEYSTORE_B64', 'OX_RELEASE_STORE_PASSWORD',
           'OX_RELEASE_KEY_PASSWORD', 'OX_RELEASE_KEY_ALIAS')
# Construct patterns without embedding literal example secrets in tracked source.
SECRET_PATTERNS = {
    'private-key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED |DSA )?PRIVATE KEY-----'),
    'github-token': re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})'),
    'aws-access-key': re.compile(rb'(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])'),
}

class Refused(RuntimeError):
    pass


def require(condition, reason):
    if not condition:
        raise Refused(reason)


def digest(path: Path) -> str:
    require(path.is_file() and not path.is_symlink(), 'missing or unsafe file')
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def command(args, *, root=ROOT, env=None, timeout=120, allow_failure=False):
    if env is None:
        env = {k: v for k, v in os.environ.items() if k not in SECRETS}
    result = subprocess.run(args, cwd=root, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=timeout, check=False)
    if not allow_failure:
        require(result.returncode == 0, f'{Path(args[0]).name} failed ({result.returncode})')
    return result


def git(*args, root=ROOT):
    return command(['git', *args], root=root).stdout.decode('utf-8', 'strict').strip()


def identity(root, head):
    require(bool(HEX40.fullmatch(head)), 'invalid expected source SHA')
    require(git('rev-parse', 'HEAD', root=root) == head, 'wrong checkout')
    require(not git('status', '--porcelain', '--untracked-files=no', root=root), 'tracked source drift')
    return {'repository': REPO, 'source_sha': head, 'source_tree': git('rev-parse', 'HEAD^{tree}', root=root),
            'pubspec_lock_sha256': digest(root / 'pubspec.lock')}


def dispatch_guard(root, head, env):
    ident = identity(root, head)
    require(env.get('GITHUB_REPOSITORY') == REPO and env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
            and env.get('GITHUB_REF') == 'refs/heads/main' and env.get('GITHUB_REF_PROTECTED') == 'true'
            and env.get('GITHUB_SHA') == head and env.get('OX_EXPECTED_SHA') == head,
            'release candidate requires explicit dispatch on protected exact main')
    require(env.get('GITHUB_RUN_ID', '').isdigit() and env.get('GITHUB_RUN_ATTEMPT', '').isdigit(),
            'missing hosted run identity')
    return dict(ident, run_id=env['GITHUB_RUN_ID'], run_attempt=env['GITHUB_RUN_ATTEMPT'])


def emit(path, value):
    require(not path.exists() and not path.is_symlink(), 'output already exists')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')


def scan_stream(stream, label):
    # Overlap chunk boundaries; only report category and path, never match bytes.
    tail = b''
    while chunk := stream.read(1024 * 1024):
        data = tail + chunk
        for kind, pattern in SECRET_PATTERNS.items():
            require(pattern.search(data) is None, f'secret signature {kind} in {label}')
        tail = data[-4096:]


def source_scan(root):
    from r00_source_contract import check_private_material
    paths = command(['git', 'ls-files', '-z'], root=root).stdout.decode().split('\0')
    paths = [p for p in paths if p]
    require(not check_private_material(paths), 'tracked signing material')
    for name in paths:
        p = root / name
        require(p.is_file() and not p.is_symlink(), f'unsafe tracked path {name}')
        require(p.name != '.env' and not p.name.startswith('.env.') and p.suffix.lower() not in ('.pem', '.key'),
                f'credential material path {name}')
        with p.open('rb') as stream:
            scan_stream(stream, name)
    return len(paths)


def dependency_inventory(root):
    import yaml
    from r07_workflow_contract import UniqueLoader
    lock = yaml.load((root / 'pubspec.lock').read_text(), Loader=UniqueLoader)
    packages = lock['packages']
    require(isinstance(packages, dict) and packages, 'empty dependency lock')
    config = json.loads((root / '.dart_tool/package_config.json').read_text())
    resolved = {x['name']: x for x in config['packages']}
    components = []
    for name, row in sorted(packages.items()):
        source, description = row['source'], row['description']
        require(name in resolved, f'unresolved locked dependency {name}')
        item = {'name': name, 'version': row['version'], 'source': source,
                'scope': row['dependency']}
        if source == 'hosted':
            require(description['url'] == 'https://pub.dev' and HEX64.fullmatch(description['sha256']),
                    f'unpinned hosted dependency {name}')
            item['sha256'] = description['sha256']
        elif source == 'git':
            require(description['url'].startswith('https://github.com/') and
                    HEX40.fullmatch(description['resolved-ref']) and description['ref'] == description['resolved-ref'],
                    f'unpinned git dependency {name}')
            item.update(url=description['url'], revision=description['resolved-ref'])
        elif source == 'path':
            path = (root / description['path']).resolve()
            require(path.is_relative_to(root / 'packages') and path.is_dir(), f'external local dependency {name}')
            item['path'] = description['path']
        else:
            require(source == 'sdk', f'unsupported dependency source {name}')
        uri = urlparse(resolved[name]['rootUri'])
        require(uri.scheme in ('', 'file') and not uri.netloc, f'nonlocal package location {name}')
        location = Path(unquote(uri.path))
        if not location.is_absolute():
            location = root / '.dart_tool' / location
        license_files = sorted(p for p in location.iterdir() if p.is_file() and
                               p.name.upper().startswith(('LICENSE', 'COPYING', 'NOTICE')))
        item['license_evidence'] = [{'name': p.name, 'sha256': digest(p)} for p in license_files]
        item['license_review'] = 'PENDING_REVIEW' if license_files else 'MISSING_LICENSE_FILE'
        components.append(item)
    return components


def maven_inventory(text, gradle_home):
    require(not re.search(r'\bFAILED\b', text), 'unresolved native dependency graph')
    coordinates = set()
    # Gradle dependency trees may have constraint/repeated node markers; the
    # resolved version (arrow), not the requested version, is the identity.
    for line in text.splitlines():
        node = re.search(r'(?:\+---|\\---) (.+)$', line)
        if not node:
            continue
        spec = node[1].split(' (', 1)[0]
        if spec.startswith('project '):
            continue
        match = re.fullmatch(r'([A-Za-z0-9_.-]+):([A-Za-z0-9_.-]+)(?::([^ ]+))?(?: -> ([^ ]+))?', spec)
        require(match is not None, 'unrecognized native dependency node')
        group, name, requested, resolved = match.groups()
        if resolved and ':' in resolved:
            replacement = resolved.split(':')
            require(len(replacement) == 3, 'unrecognized dependency substitution')
            group, name, resolved = replacement
        version = resolved or requested
        require(isinstance(version, str) and re.fullmatch(r'[A-Za-z0-9_.+-]+', version) is not None, 'nonexact resolved native dependency')
        require(all(re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', v) for v in (group, name)) and version not in ('.', '..'), 'unsafe native dependency coordinate')
        coordinates.add((group, name, version))
    require(bool(coordinates), 'empty native dependency graph')
    result = []
    for group, name, version in sorted(coordinates):
        directory = gradle_home / 'caches/modules-2/files-2.1' / group / name / version
        files = sorted(directory.glob('*/*.pom'))
        licenses = []
        for p in files:
            require(p.stat().st_size <= 2 * 1024 * 1024, 'oversized native dependency metadata')
            document = ET.fromstring(p.read_bytes())
            for element in document.findall('.//{*}licenses/{*}license'):
                licenses.append({'name': element.findtext('{*}name', ''),
                                 'url': element.findtext('{*}url', '')})
        result.append(dict(group=group, name=name, version=version,
                           pom_sha256=sorted({digest(p) for p in files}), licenses=licenses,
                           license_review='PENDING_REVIEW' if licenses else 'MISSING_LICENSE_METADATA'))
    return result


def sbom(ident, pub, maven):
    components = []
    for row in pub:
        item = {'type': 'library', 'name': row['name'], 'version': row['version'],
                'bom-ref': 'pub:' + row['name'], 'properties': [
                    {'name': 'obtainx:source', 'value': row['source']},
                    {'name': 'obtainx:scope', 'value': row['scope']}]}
        if row['source'] == 'hosted':
            item['purl'] = f"pkg:pub/{row['name']}@{row['version']}"
            item['hashes'] = [{'alg': 'SHA-256', 'content': row['sha256']}]
        if row['source'] == 'git':
            item['externalReferences'] = [{'type': 'vcs', 'url': row['url'] + '#' + row['revision']}]
        components.append(item)
    for row in maven:
        components.append({'type': 'library', 'group': row['group'], 'name': row['name'],
                           'version': row['version'], 'bom-ref': f"maven:{row['group']}:{row['name']}:{row['version']}",
                           'purl': f"pkg:maven/{row['group']}/{row['name']}@{row['version']}"})
    return {'bomFormat': 'CycloneDX', 'specVersion': '1.5', 'version': 1,
            'metadata': {'component': {'type': 'application', 'name': PACKAGE,
                                       'version': ident['source_sha']}}, 'components': components}


def osv_queries(pub, maven):
    queries = [{'package': {'ecosystem': 'Pub', 'name': x['name']}, 'version': x['version']}
               for x in pub if x['source'] == 'hosted']
    queries += [{'commit': x['revision']} for x in pub if x['source'] == 'git']
    queries += [{'package': {'ecosystem': 'Maven', 'name': x['group'] + ':' + x['name']}, 'version': x['version']}
                for x in maven]
    return queries


def vulnerability_audit(pub, maven, fetch=None):
    # Only public package coordinates are sent, with bounded responses and no credentials.
    def query(batch):
        request = urllib.request.Request('https://api.osv.dev/v1/querybatch',
            data=json.dumps({'queries': batch}).encode(), headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(request, timeout=45) as response:
            require(response.geturl() == request.full_url, 'unexpected advisory endpoint')
            data = response.read(8 * 1024 * 1024 + 1)
            require(len(data) <= 8 * 1024 * 1024, 'oversized advisory response')
            return json.loads(data)
    fetch = fetch or query
    queries = osv_queries(pub, maven)
    require(bool(queries) and len(queries) <= 3000, 'invalid advisory query inventory')
    findings = []
    for start in range(0, len(queries), 100):
        batch = queries[start:start+100]
        response = fetch(batch)
        results = response.get('results')
        require(isinstance(results, list) and len(results) == len(batch), 'incomplete advisory response')
        for spec, result in zip(batch, results):
            require(isinstance(result, dict) and not result.get('next_page_token'), 'incomplete advisory pagination')
            vulns = result.get('vulns', [])
            require(isinstance(vulns, list) and all(isinstance(v, dict) and v.get('id') for v in vulns), 'invalid advisory evidence')
            findings.extend({'query': spec, 'id': v['id']} for v in vulns)
    return {'schema': 'obtainx.r12.osv.v1', 'endpoint': 'https://api.osv.dev/v1/querybatch',
            'checked_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'queries': queries, 'findings': findings, 'status': 'FAIL' if findings else 'NO_KNOWN_FINDINGS',
            'limitations': ['No advisory database proves absence of vulnerabilities', 'SDK and local code require independent review']}


def sdk_tool(name):
    sdk = os.environ.get('ANDROID_SDK_ROOT') or os.environ.get('ANDROID_HOME')
    require(bool(sdk), 'Android SDK not configured')
    p = Path(sdk) / 'build-tools/35.0.0' / name
    require(p.is_file() and os.access(p, os.X_OK), f'missing pinned build-tool {name}')
    return str(p)


def apk_entries(path):
    require(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= MAX_APK, 'unsafe APK size/type')
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        require(0 < len(infos) <= 20000 and sum(i.file_size for i in infos) <= MAX_EXPANDED, 'APK inventory exceeds bounds')
        result = {}
        for i in infos:
            name = i.filename
            require(name not in result and not name.startswith('/') and '\\' not in name and
                    '..' not in name.split('/') and not i.flag_bits & 1 and
                    (i.external_attr >> 16) & 0o170000 != 0o120000, 'unsafe APK member')
            with z.open(i) as stream:
                h = hashlib.sha256()
                while chunk := stream.read(1024 * 1024):
                    h.update(chunk)
                result[name] = h.hexdigest()
            with z.open(i) as stream:
                scan_stream(stream, name)
        require('AndroidManifest.xml' in result and 'classes.dex' in result, 'not an Android application APK')
        return result


def metadata(text, version, code, abi):
    line = next((s for s in text.splitlines() if s.startswith('package: ')), '')
    fields = dict(re.findall(r"(\w+)='([^']*)'", line))
    require(fields.get('name') == PACKAGE and fields.get('versionName') == version and
            fields.get('versionCode') == str(code * 10 + ABIS[abi]), 'unexpected APK package or version')
    require(not any(s.startswith('application-debuggable') for s in text.splitlines()), 'debuggable release APK')
    require("sdkVersion:'26'" in text.splitlines(), 'wrong min SDK')
    native = next((s for s in text.splitlines() if s.startswith('native-code:')), '')
    require(re.findall(r"'([^']+)'", native) == [abi], 'unexpected ABI inventory')
    return {'package': PACKAGE, 'version_name': version, 'version_code': int(fields['versionCode']), 'abi': abi}


def signer(text, expected):
    require(bool(HEX64.fullmatch(expected)), 'invalid independently configured certificate digest')
    fingerprints = re.findall(r'^Signer #\d+ certificate SHA-256 digest:\s*([a-fA-F0-9]{64})\s*$', text, re.M)
    require([v.lower() for v in fingerprints] == [expected], 'unexpected signing certificate or signer count')
    return expected


def version_of(root):
    text = (root / 'pubspec.yaml').read_text()
    matches = re.findall(r'^version:\s*([0-9]+\.[0-9]+\.[0-9]+)\+([0-9]+)\s*$', text, re.M)
    require(len(matches) == 1, 'ambiguous application version')
    return matches[0][0], int(matches[0][1])


def has_apk_signing_block(path):
    with zipfile.ZipFile(path) as z, path.open('rb') as stream:
        if z.start_dir < 16:
            return False
        stream.seek(z.start_dir - 16)
        return stream.read(16) == b'APK Sig Block 42'


def inspect_apks(root, directory, *, expected_signer=None):
    version, code = version_of(root)
    expected = {f'app-{abi}-normal-release.apk': abi for abi in ABIS}
    require({p.name for p in directory.glob('*.apk')} == set(expected), 'wrong release APK inventory')
    result = {}
    for name, abi in sorted(expected.items()):
        p = directory / name
        entries = apk_entries(p)
        output = command([sdk_tool('aapt'), 'dump', 'badging', str(p)]).stdout.decode('utf-8', 'replace')
        meta = metadata(output, version, code, abi)
        command([sdk_tool('zipalign'), '-c', '-P', '16', '4', str(p)])
        verify = command([sdk_tool('apksigner'), 'verify', '--verbose', '--print-certs', str(p)], allow_failure=True)
        if expected_signer is None:
            require(verify.returncode != 0 and not has_apk_signing_block(p), 'unsigned build unexpectedly signed or contains signing block')
            require(not any(re.match(r'META-INF/[^/]+\.(RSA|DSA|EC|SF)$', n, re.I) for n in entries), 'unexpected v1 signature')
        else:
            require(verify.returncode == 0 and has_apk_signing_block(p), 'APK signature verification failed')
            meta['certificate_sha256'] = signer(verify.stdout.decode('utf-8', 'replace'), expected_signer)
        result[name] = dict(meta, sha256=digest(p), bytes=p.stat().st_size, payload=entries)
    return result


def compare_builds(a, b, ident):
    require(a.get('schema') == b.get('schema') == 'obtainx.r12.unsigned-build.v1', 'wrong build evidence schema')
    for row in (a, b):
        require(all(row.get(k) == v for k, v in ident.items()), 'stale or wrong-run build evidence')
    require(a.get('replica') == 'a' and b.get('replica') == 'b' and all(HEX64.fullmatch(str(row.get('runner', ''))) for row in (a, b)) and a.get('runner') != b.get('runner'),
            'independent build identities required')
    for key in ('apks', 'dependencies_sha256', 'sbom_sha256', 'toolchain_sha256'):
        require(a.get(key) and a.get(key) == b.get(key), f'non-reproducible {key}')
    return a['apks']


CI_SCHEMA = 'obtainx.r12.hosted-ci.v2'
CI_EXACT = 'EXACT_MAIN_FULL_JOBS'
CI_REUSED = 'EXACT_MERGED_TREE_FULL_JOBS'


def read_ci_api(path):
    token = os.environ.get('OX_CI_READ_TOKEN', '')
    require(bool(token), 'read-only CI evidence token missing')
    allowed = (r'/actions/(?:workflows/[0-9]+/runs\?head_sha=[a-f0-9]{40}&per_page=50|'
               r'runs/[0-9]+(?:/attempts/[0-9]+/jobs\?per_page=100)?)|'
               r'/git/(?:commits/[a-f0-9]{40}|ref/heads/main)|'
               r'/commits/[a-f0-9]{40}/pulls\?per_page=50|'
               r'/environments/obtainx-release-candidate(?:/deployment-branch-policies\?per_page=100)?')
    require(re.fullmatch(allowed, path), 'unexpected CI evidence endpoint')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    request = urllib.request.Request('https://api.github.com/repos/' + REPO + path,
        headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'ObtainX-R12'})
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
        payload = response.read(8 * 1024 * 1024 + 1)
        require(len(payload) <= 8 * 1024 * 1024, 'oversized hosted CI evidence')
        return json.loads(payload)


def verify_current_main(head, tree, fetch):
    require(HEX40.fullmatch(head) and HEX40.fullmatch(tree), 'invalid CI source')
    ref = fetch('/git/ref/heads/main')
    require(ref.get('ref') == 'refs/heads/main' and ref.get('object', {}).get('type') == 'commit'
            and ref['object'].get('sha') == head, 'reviewed main moved')
    commit = fetch(f'/git/commits/{head}')
    require(commit.get('sha') == head and commit.get('tree', {}).get('sha') == tree,
            'remote main tree differs from checkout')
    return commit


def merged_tree_origin(head, tree, commit, fetch):
    """Only a direct, GitHub-verified two-parent PR merge of identical bytes.

    Squash/rebase/direct pushes, changed merge trees, ambiguous PR association,
    and inaccessible evidence require fresh full main jobs instead of reuse.
    """
    from obtainx_ci_policy import REPO_ID
    parents = commit.get('parents')
    require(commit.get('verification', {}).get('verified') is True and
            isinstance(parents, list) and len(parents) == 2 and
            all(isinstance(x, dict) and HEX40.fullmatch(str(x.get('sha', ''))) for x in parents),
            'main is not a verified two-parent merge')
    first, source = (p['sha'] for p in parents)
    require(first != source and source != head, 'invalid merge parents')
    original = fetch(f'/git/commits/{source}')
    require(original.get('sha') == source and original.get('tree', {}).get('sha') == tree,
            'merged PR tree differs from current main')
    rows = fetch(f'/commits/{head}/pulls?per_page=50')
    require(isinstance(rows, list) and 0 < len(rows) < 50, 'incomplete merged PR inventory')
    matches = [r for r in rows if isinstance(r, dict) and r.get('merge_commit_sha') == head]
    require(len(matches) == 1, 'ambiguous merge PR')
    pr = matches[0]
    require(type(pr.get('number')) is int and pr['number'] > 0 and
            pr.get('state') == 'closed' and bool(pr.get('merged_at')) and
            pr.get('head', {}).get('sha') == source and
            pr.get('head', {}).get('repo', {}).get('id') == REPO_ID and
            pr.get('base', {}).get('ref') == 'main' and
            pr.get('base', {}).get('repo', {}).get('id') == REPO_ID and
            isinstance(pr['head'].get('ref'), str) and pr['head']['ref'] != 'main' and
            'ci:development-only' not in {x.get('name') for x in pr.get('labels', [])},
            'merged PR identity or scope is not eligible for reuse')
    return {'pr': pr['number'], 'merge_sha': head, 'source_sha': source,
            'source_tree': tree, 'branch': pr['head']['ref']}


def latest_lane(fetch, lane, source, branch, events):
    from obtainx_ci_policy import FULL_PROOFS, REPO_ID, full_job_proof
    workflow, job, steps = FULL_PROOFS[lane]
    result = fetch(f'/actions/workflows/{workflow}/runs?head_sha={source}&per_page=50')
    rows = result.get('workflow_runs')
    require(isinstance(rows, list) and result.get('total_count') == len(rows),
            f'incomplete CI evidence {lane}')
    # Wrong-repository/commit/workflow rows are not eligible. A newer failed,
    # cancelled, scoped or running matching run MUST NOT be masked by an old pass.
    candidates = [r for r in rows if r.get('head_sha') == source and
                  r.get('head_branch') == branch and r.get('event') in events]
    if not candidates:
        return None
    require(all(type(r.get('id')) is int and r['id'] > 0 for r in candidates),
            f'invalid CI run identity {lane}')
    row = max(candidates, key=lambda r: r['id'])
    require(row.get('workflow_id') == workflow and row.get('status') == 'completed' and
            row.get('conclusion') == 'success' and row.get('repository', {}).get('id') == REPO_ID and
            row.get('head_repository', {}).get('id') == REPO_ID and
            type(row.get('run_attempt')) is int and row['run_attempt'] >= 1,
            f'latest matching run not successful: {lane}')
    identity_fields = ('id', 'workflow_id', 'head_sha', 'head_branch', 'event', 'run_attempt',
                       'status', 'conclusion')
    def recheck():
        current = fetch(f'/actions/runs/{row["id"]}')
        require(all(current.get(k) == row[k] for k in identity_fields) and
                current.get('repository', {}).get('id') == REPO_ID and
                current.get('head_repository', {}).get('id') == REPO_ID,
                f'run identity or attempt changed: {lane}')
    recheck()
    evidence = fetch(f'/actions/runs/{row["id"]}/attempts/{row["run_attempt"]}/jobs?per_page=100')
    jobs = evidence.get('jobs')
    require(isinstance(jobs, list) and evidence.get('total_count') == len(jobs) and
            full_job_proof(jobs, job, steps), f'full CI job proof missing: {lane}')
    actual = next(j for j in jobs if j['name'] == job)
    require(type(actual.get('id')) is int and actual['id'] > 0 and
            actual.get('head_sha') == source and actual.get('run_id') == row['id'] and
            actual.get('run_attempt') == row['run_attempt'] and actual.get('status') == 'completed' and
            all(sum(s.get('name') == step and s.get('status') == 'completed' and
                    s.get('conclusion') == 'success' for s in actual.get('steps', [])) == 1 for step in steps),
            f'wrong job, attempt or decisive step: {lane}')
    recheck()
    # Reject a replacement run scheduled while this proof was being observed.
    after = fetch(f'/actions/workflows/{workflow}/runs?head_sha={source}&per_page=50')
    later = after.get('workflow_runs')
    require(isinstance(later, list) and after.get('total_count') == len(later) and
            any(x.get('id') == row['id'] and x.get('run_attempt') == row['run_attempt'] for x in later) and
            not any(x.get('head_sha') == source and x.get('head_branch') == branch and
                    x.get('event') in events and (type(x.get('id')) is not int or x['id'] > row['id']) for x in later),
            f'newer CI run appeared during observation: {lane}')
    return {'workflow_id': workflow, 'run_id': row['id'], 'attempt': row['run_attempt'],
            'job_id': actual['id'], 'decisive_steps': list(steps), 'source_sha': source}


def hosted_ci(head, tree, fetch=None):
    from obtainx_ci_policy import FULL_PROOFS
    fetch = fetch or read_ci_api
    commit = verify_current_main(head, tree, fetch)
    proofs = {}
    origin = None
    pr_source_proof = None
    for lane in FULL_PROOFS:
        proof = latest_lane(fetch, lane, head, 'main', ('workflow_dispatch', 'push'))
        if proof is None:
            # Main source-contracts verifies commit-sensitive ancestry. It is
            # always fresh. Never replace an observed main failure by PR proof.
            require(lane != 'source', 'missing fresh exact-main source contract')
            if origin is None:
                origin = merged_tree_origin(head, tree, commit, fetch)
                pr_source_proof = latest_lane(fetch, 'source', origin['source_sha'], origin['branch'], ('pull_request',))
                require(pr_source_proof is not None, 'missing full merged PR source proof')
            proof = latest_lane(fetch, lane, origin['source_sha'], origin['branch'], ('pull_request',))
            require(proof is not None, f'missing full merged PR proof: {lane}')
            proof['evidence_mode'] = 'REUSED_EXACT_MERGED_TREE'
        else:
            proof['evidence_mode'] = 'EXECUTED_EXACT_MAIN'
        proof['source_tree'] = tree
        proofs[lane] = proof
    verify_current_main(head, tree, fetch)
    receipt = {'schema': CI_SCHEMA, 'source_sha': head, 'source_tree': tree,
               'repository': REPO, 'mode': CI_REUSED if origin else CI_EXACT, 'proofs': proofs}
    if origin:
        receipt['merge_origin'] = origin
        receipt['merged_pr_source_proof'] = dict(pr_source_proof, source_tree=tree)
    return receipt


def verify_signing_environment(fetch=None):
    """Fail closed if environment policy is inaccessible or not independently gated."""
    fetch = fetch or read_ci_api
    env = fetch('/environments/obtainx-release-candidate')
    require(env.get('name') == 'obtainx-release-candidate' and env.get('can_admins_bypass') is False,
            'signing environment administrative bypass is not demonstrably disabled')
    rules = env.get('protection_rules')
    require(isinstance(rules, list), 'signing environment rules unavailable')
    reviewers = [r for r in rules if r.get('type') == 'required_reviewers']
    require(len(reviewers) == 1 and reviewers[0].get('prevent_self_review') is True and
            isinstance(reviewers[0].get('reviewers'), list) and bool(reviewers[0]['reviewers']),
            'independent signing review is not demonstrably enforced')
    branch = env.get('deployment_branch_policy')
    require(isinstance(branch, dict), 'signing environment branch policy missing')
    if not (branch.get('protected_branches') is True and branch.get('custom_branch_policies') is False):
        require(branch.get('protected_branches') is False and branch.get('custom_branch_policies') is True,
                'signing environment must restrict deployment branches')
        allowed = fetch('/environments/obtainx-release-candidate/deployment-branch-policies?per_page=100')
        policies = allowed.get('branch_policies')
        require(isinstance(policies, list) and allowed.get('total_count') == len(policies) == 1 and
                policies[0].get('name') == 'main' and policies[0].get('type') == 'branch',
                'signing environment custom policy must allow only main')
    return True


def validate_ci_receipt(ci, ident):
    from obtainx_ci_policy import FULL_PROOFS
    require(ci.get('schema') == CI_SCHEMA and ci.get('repository') == REPO and
            ci.get('source_sha') == ident['source_sha'] and ci.get('source_tree') == ident['source_tree'] and
            ci.get('mode') in (CI_EXACT, CI_REUSED) and isinstance(ci.get('proofs'), dict) and
            set(ci['proofs']) == set(FULL_PROOFS), 'missing exact main/tree CI evidence')
    require(ci['proofs']['source'].get('evidence_mode') == 'EXECUTED_EXACT_MAIN', 'main source proof must be fresh')
    for lane, proof in ci['proofs'].items():
        workflow, _, steps = FULL_PROOFS[lane]
        require(proof.get('workflow_id') == workflow and proof.get('source_tree') == ident['source_tree'] and
                proof.get('decisive_steps') == list(steps) and
                all(type(proof.get(k)) is int and proof[k] > 0 for k in ('run_id', 'attempt', 'job_id')),
                'CI proof structure mismatch')
        mode = proof.get('evidence_mode')
        if mode == 'EXECUTED_EXACT_MAIN':
            require(proof.get('source_sha') == ident['source_sha'], 'wrong fresh CI source')
        else:
            require(mode == 'REUSED_EXACT_MERGED_TREE' and lane != 'source' and ci['mode'] == CI_REUSED and
                    ci.get('merge_origin', {}).get('merge_sha') == ident['source_sha'] and
                    ci.get('merge_origin', {}).get('source_tree') == ident['source_tree'] and
                    HEX40.fullmatch(str(ci['merge_origin'].get('source_sha', ''))) and
                    proof.get('source_sha') == ci['merge_origin']['source_sha'], 'wrong reused CI source')
    if ci['mode'] == CI_REUSED:
        origin = ci.get('merge_origin', {})
        original = ci.get('merged_pr_source_proof', {})
        workflow, _, steps = FULL_PROOFS['source']
        require(type(origin.get('pr')) is int and origin['pr'] > 0 and
                original.get('workflow_id') == workflow and original.get('source_tree') == ident['source_tree'] and
                original.get('source_sha') == origin.get('source_sha') and original.get('decisive_steps') == list(steps) and
                all(type(original.get(k)) is int and original[k] > 0 for k in ('run_id', 'attempt', 'job_id')),
                'missing original full PR source proof')
    require((ci['mode'] == CI_REUSED) == any(p['evidence_mode'] == 'REUSED_EXACT_MERGED_TREE' for p in ci['proofs'].values()), 'CI mode does not match evidence')
    return ci['mode']


def build_record(args, ident):
    directory = args.directory
    require(args.replica in ('a', 'b'), 'invalid replica')
    require(bool(os.environ.get('RUNNER_NAME')), 'runner identity unavailable')
    toolchain_path = directory / 'toolchain.json'
    flutter = json.loads(command(['flutter', '--version', '--machine'], timeout=60).stdout)
    require(flutter.get('frameworkVersion') == '3.47.6' and HEX40.fullmatch(str(flutter.get('frameworkRevision', ''))), 'wrong Flutter toolchain')
    java = command(['java', '-version']).stdout.decode('utf-8', 'replace').splitlines()[0]
    require(re.search(r'\b21(?:\.|"|$)', java), 'wrong Java toolchain')
    emit(toolchain_path, {'flutter_version': flutter['frameworkVersion'], 'flutter_revision': flutter['frameworkRevision'], 'engine_revision': flutter.get('engineRevision'), 'dart_version': flutter.get('dartSdkVersion'), 'java': java, 'gradle_wrapper_sha256': digest(ROOT / 'android/gradle/wrapper/gradle-wrapper.properties'), 'build_tools': {tool: digest(Path(sdk_tool(tool))) for tool in ('apksigner', 'aapt', 'zipalign')}})
    ci_path = directory / 'ci.json'
    ci = json.loads(ci_path.read_text())
    validate_ci_receipt(ci, ident)
    pub = dependency_inventory(ROOT)
    gradle = directory / 'gradle-dependencies.txt'
    require(gradle.is_file() and 0 < gradle.stat().st_size <= 16 * 1024 * 1024, 'missing native dependency inventory')
    with gradle.open('rb') as f:
        scan_stream(f, gradle.name)
    maven = maven_inventory(gradle.read_text(), Path(os.environ.get('GRADLE_USER_HOME', str(Path.home() / '.gradle'))))
    emit(directory / 'dependencies.json', {'schema': 'obtainx.r12.dependency-inventory.v1', 'pub': pub, 'maven': maven, 'license_review': 'PENDING_REVIEW'})
    emit(directory / 'sbom.cdx.json', sbom(ident, pub, maven))
    advisories = vulnerability_audit(pub, maven)
    emit(directory / 'advisories.json', advisories)
    require(not advisories['findings'], 'known dependency vulnerability requires repair/review before signing')
    apks = inspect_apks(ROOT, directory)
    runner = hashlib.sha256(Path('/proc/sys/kernel/random/boot_id').read_bytes()).hexdigest()
    emit(directory / 'build.json', dict(ident, schema='obtainx.r12.unsigned-build.v1', replica=args.replica,
                                       runner=runner, apks=apks, ci_sha256=digest(ci_path), toolchain_sha256=digest(toolchain_path),
                                       sbom_sha256=digest(directory / 'sbom.cdx.json'),
                                       advisories_sha256=digest(directory / 'advisories.json'),
                                       dependencies_sha256=digest(directory / 'dependencies.json'),
                                       gradle_inventory_sha256=digest(gradle)))


def validate_signing_inputs(env):
    require(all(env.get(k) for k in SECRETS), 'protected signing credentials missing')
    expected = env.get('OX_RELEASE_CERT_SHA256', '').lower()
    require(bool(HEX64.fullmatch(expected)), 'expected certificate digest missing or invalid')
    try:
        key = base64.b64decode(env[SECRETS[0]], validate=True)
    except (ValueError, TypeError):
        raise Refused('invalid protected keystore encoding') from None
    require(0 < len(key) <= 1024 * 1024, 'invalid keystore size')
    require(re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', env['OX_RELEASE_KEY_ALIAS']) is not None, 'invalid signing key alias')
    return key, expected


def sign_candidate(args, ident):
    # Verify independently downloaded files and their evidence before exposing signing inputs to apksigner.
    a, b = args.first, args.second
    files = {f'app-{abi}-normal-release.apk' for abi in ABIS} | {'build.json', 'ci.json', 'dependencies.json', 'gradle-dependencies.txt', 'sbom.cdx.json', 'advisories.json', 'toolchain.json'}
    for directory in (a, b):
        require(directory.is_dir() and not directory.is_symlink() and {p.name for p in directory.iterdir()} == files, 'unexpected unsigned evidence inventory')
        require(all(p.is_file() and not p.is_symlink() and p.stat().st_size <= (MAX_APK if p.suffix == '.apk' else 32 * 1024 * 1024) for p in directory.iterdir()), 'unsafe unsigned evidence file')
    records = [json.loads((p / 'build.json').read_text()) for p in (a, b)]
    unsigned = compare_builds(*records, ident)
    independent_ci = json.loads(args.ci.read_text())
    ci_mode = validate_ci_receipt(independent_ci, ident)
    for p, row in zip((a, b), records):
        require(digest(p / 'ci.json') == row['ci_sha256'] and json.loads((p / 'ci.json').read_text()) == independent_ci, 'exact main CI evidence changed')
        require(inspect_apks(ROOT, p) == unsigned, 'unsigned artifact changed after build')
        require(digest(p / 'dependencies.json') == row['dependencies_sha256'] and
                digest(p / 'gradle-dependencies.txt') == row['gradle_inventory_sha256'] and
                digest(p / 'sbom.cdx.json') == row['sbom_sha256'] and
                digest(p / 'advisories.json') == row['advisories_sha256'] and
                digest(p / 'toolchain.json') == row['toolchain_sha256'], 'dependency or toolchain evidence changed')
        inventory = json.loads((p / 'dependencies.json').read_text())
        audit = json.loads((p / 'advisories.json').read_text())
        require(audit.get('queries') == osv_queries(inventory['pub'], inventory['maven']) and
                audit.get('status') == 'NO_KNOWN_FINDINGS' and audit.get('findings') == [], 'advisory evidence not clear')
    # Read live protection and reobserve before decoding signing credentials.
    verify_signing_environment()
    require(hosted_ci(ident['source_sha'], ident['source_tree']) == independent_ci,
            'CI or main evidence changed before signing')
    key, expected = validate_signing_inputs(os.environ)
    require(not args.directory.exists(), 'candidate output directory already exists')
    # The key exists only in a mode-0700 temporary directory and never enters upload paths.
    with tempfile.TemporaryDirectory(prefix='ox-r12-key-', dir=os.environ['RUNNER_TEMP']) as tmp:
        ks = Path(tmp) / 'release.keystore'
        fd = os.open(ks, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'wb') as f:
            f.write(key)
        args.directory.mkdir(mode=0o700)
        clean = dict(os.environ)
        clean.pop(SECRETS[0], None)
        for name in unsigned:
            command([sdk_tool('apksigner'), 'sign', '--ks', str(ks), '--ks-key-alias',
                     clean['OX_RELEASE_KEY_ALIAS'], '--ks-pass', 'env:OX_RELEASE_STORE_PASSWORD',
                     '--key-pass', 'env:OX_RELEASE_KEY_PASSWORD', '--v1-signing-enabled', 'false',
                     '--v2-signing-enabled', 'true', '--v3-signing-enabled', 'true',
                     '--out', str(args.directory / name), str(a / name)], env=clean)
        signed = inspect_apks(ROOT, args.directory, expected_signer=expected)
        for name, row in signed.items():
            require(row['payload'] == unsigned[name]['payload'], 'signing changed APK payload')
        for name in ('dependencies.json', 'gradle-dependencies.txt', 'sbom.cdx.json', 'advisories.json', 'ci.json', 'toolchain.json'):
            (args.directory / name).write_bytes((a / name).read_bytes())
        for replica, directory in [('a', a), ('b', b)]:
            for name in ('build.json', 'advisories.json', 'gradle-dependencies.txt'):
                (args.directory / f'{replica}-{name}').write_bytes((directory / name).read_bytes())
        emit(args.directory / 'candidate.json', dict(ident, schema='obtainx.r12.signed-candidate.v1',
             unsigned_builds=[digest(p / 'build.json') for p in (a, b)],
             certificate_sha256=expected, apks=signed, dependencies_sha256=digest(a / 'dependencies.json'),
             gradle_inventory_sha256=digest(a / 'gradle-dependencies.txt'),
             sbom_sha256=digest(a / 'sbom.cdx.json'), advisories_sha256=digest(a / 'advisories.json'),
             reproducibility='UNSIGNED_EXACT_BYTES_MATCH', package_status='SIGNED_CANDIDATE_VERIFIED',
             SOURCE_PASS='PASS_BUILD_LANES', HOSTED_CI_PASS='PASS_' + ci_mode,
             ci_sha256=digest(args.ci), toolchain_sha256=digest(a / 'toolchain.json'),
             DEVICE_RUNTIME_PASS='PENDING_EXTERNAL', RELEASE_QUALIFIED=False, publication_authorized=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for name in ('preflight', 'verify-environment', 'record-ci', 'record-build', 'sign-candidate'):
        p = sub.add_parser(name)
        p.add_argument('--head', required=True)
        if name in ('record-build', 'sign-candidate'):
            p.add_argument('--directory', type=Path, required=True)
        if name == 'record-ci':
            p.add_argument('--output', type=Path, required=True)
        if name == 'record-build':
            p.add_argument('--replica', required=True)
        if name == 'sign-candidate':
            p.add_argument('--first', type=Path, required=True)
            p.add_argument('--second', type=Path, required=True)
            p.add_argument('--ci', type=Path, required=True)
    args = parser.parse_args()
    try:
        ident = dispatch_guard(ROOT, args.head, os.environ)
        if args.action == 'preflight':
            print(f'R12_SOURCE_SCAN_PASS files={source_scan(ROOT)}')
        elif args.action == 'verify-environment':
            verify_signing_environment()
            print('R12_SIGNING_ENVIRONMENT_POLICY_PASS; actual human approval separate')
        elif args.action == 'record-ci':
            emit(args.output, hosted_ci(args.head, ident['source_tree']))
        elif args.action == 'record-build':
            build_record(args, ident)
        else:
            sign_candidate(args, ident)
    except Refused as exc:
        print('R12_REFUSED:', exc)
        return 1
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError, zipfile.BadZipFile):
        # Never echo exception arguments which might contain private data.
        print('R12_REFUSED: invalid or inaccessible qualification input')
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
