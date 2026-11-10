#!/usr/bin/env python3
"""R00 bootstrap integrity contract: read-only and fail-closed.

This is not a claim of APK or Android runtime qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_WORKFLOWS = {
    'obtainx-r00-contracts.yml',
    'obtainx-r00-flutter.yml',
}
LEGACY_WORKFLOWS = {
    'build.yml', 'release.yml', 'pr-base-guard.yml',
    'format-issue-body.yml', 'translation-validate.yaml',
}
SHA = re.compile(r'^[0-9a-f]{40}$')
ACTION = re.compile(r'^\s*-\s+uses:\s*([^\s#]+)', re.MULTILINE)
SENSITIVE_SUFFIXES = ('.jks', '.keystore', '.p12', '.pfx', '.private-key')
SENSITIVE_EXACT = {'android/key.properties'}


def check_private_material(paths: list[str]) -> list[str]:
    return [
        p for p in paths
        if p.lower() in SENSITIVE_EXACT
        or p.lower().endswith(SENSITIVE_SUFFIXES)
    ]


def check_workflows(workflow_files: dict[str, str]) -> list[str]:
    errors: list[str] = []
    names = set(workflow_files)
    unexpected = names - EXPECTED_WORKFLOWS
    missing = EXPECTED_WORKFLOWS - names
    if unexpected:
        errors.append('unreviewed workflow(s): ' + ', '.join(sorted(unexpected)))
    if missing:
        errors.append('missing workflow(s): ' + ', '.join(sorted(missing)))
    if names & LEGACY_WORKFLOWS:
        errors.append('upstream release/write workflow resurrected')
    for name, data in workflow_files.items():
        if not re.search(r'(?m)^permissions:\s*\n\s+contents:\s+read\s*$', data):
            errors.append(name + ': missing top-level read-only permissions')
        if re.search(r'(?m)^\s+(?:contents|issues|pull-requests|actions|packages|attestations|id-token):\s*write\s*$', data):
            errors.append(name + ': write access is prohibited in R00')
        for ref in ACTION.findall(data):
            if ref.startswith('./'):
                continue
            if '@' not in ref or not SHA.fullmatch(ref.rsplit('@', 1)[-1]):
                errors.append(name + ': action not pinned to a 40-hex SHA (' + ref + ')')
        if re.search(r'(?:gh\s+release\s+create|action-gh-release|github-tag-action|release-action)', data):
            errors.append(name + ': release publication not permitted in R00')
    return errors


def inspect(root: Path = ROOT, validate_git: bool = True) -> list[str]:
    errors: list[str] = []
    baseline_path = root / 'docs/R00_BASELINE.json'
    roadmap_path = root / 'docs/ROADMAP.md'
    for p in [baseline_path, roadmap_path, root / 'docs/R00_TEST_AUDIT.md',
              root / 'docs/SECURITY_RELEASE_POLICY.md', root / 'docs/DEVELOPMENT.md']:
        if not p.is_file():
            errors.append('missing required file: ' + str(p.relative_to(root)))
    baseline = {}
    if baseline_path.is_file():
        try:
            baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
            if baseline.get('schema_version') != 1:
                errors.append('invalid baseline schema_version')
            for field in ('upstream_sha', 'fork_main_sha'):
                if not SHA.fullmatch(str(baseline.get(field, ''))):
                    errors.append('invalid commit SHA: ' + field)
            if '/' not in str(baseline.get('fork_repo', '')) or '/' not in str(baseline.get('upstream_repo', '')):
                errors.append('missing repository identity')
        except (UnicodeError, ValueError, OSError) as e:
            errors.append('invalid baseline json: ' + str(e))
    if roadmap_path.is_file():
        digest = hashlib.sha256(roadmap_path.read_bytes()).hexdigest()
        if baseline.get('roadmap_sha256') != digest:
            errors.append('roadmap digest drift: update baseline receipt with roadmap edits')
    wfdir = root / '.github/workflows'
    workflows = {}
    if not wfdir.is_dir():
        errors.append('missing workflow directory')
    else:
        for p in wfdir.iterdir():
            if p.is_file() and p.suffix.lower() in {'.yaml', '.yml'}:
                try:
                    workflows[p.name] = p.read_text(encoding='utf-8')
                except (UnicodeError, OSError) as e:
                    errors.append(f'unreadable workflow {p.name}: {e}')
    errors.extend(check_workflows(workflows))
    if validate_git:
        try:
            listed = subprocess.run(['git', 'ls-files', '-z'], cwd=root, check=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
            files = [s.decode('utf-8', errors='replace') for s in listed.split(b'\0') if s]
            for secret in check_private_material(files):
                errors.append('tracked signing/private material: ' + secret)
            sha = str(baseline.get('upstream_sha', ''))
            if SHA.fullmatch(sha):
                result = subprocess.run(['git', 'merge-base', '--is-ancestor', sha, 'HEAD'],
                                        cwd=root, check=False, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)
                if result.returncode != 0:
                    errors.append('source pin is not an ancestor of HEAD: ' + sha)
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            errors.append('git inspection failed: ' + str(e))
    for p in (root / 'assets/translations').glob('*.json'):
        try:
            json.loads(p.read_text(encoding='utf-8-sig'))
        except (UnicodeError, ValueError, OSError) as e:
            errors.append('translation JSON invalid: ' + p.name + ': ' + str(e))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='perform read-only checks')
    args = parser.parse_args()
    issues = inspect()
    if issues:
        for issue in issues:
            print('OX_R00_CONTRACT_FAIL:', issue)
        return 1
    print('OX_R00_SOURCE_CONTRACT_PASS')
    print('OX_R00_RUNTIME_QUALIFICATION=NOT_PERFORMED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
