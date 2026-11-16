#!/usr/bin/env python3
"""Read-only live GitHub Actions source acceptance; no installation or root.

Uses already configured GitHub CLI credentials, never prints secrets, never
writes to the repository. Optional --download-verify streams a transient ZIP,
verifies its exact GitHub sha256 digest and deletes it, NOT APK signing proof.
"""
from __future__ import annotations
import argparse
import hashlib
import os
import urllib.error
import urllib.parse
import urllib.request
import json
import re
from datetime import datetime, timezone
import subprocess
import sys
import tempfile
from pathlib import Path

SHA = re.compile(r'^[0-9a-f]{40}$')
DIGEST = re.compile(r'^sha256:([0-9a-f]{64})$')
REPO = re.compile(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')
MAX_BYTES = 1024 * 1024 * 1024

class Refused(Exception):
    pass

def api(path: str) -> dict:
    try:
        run = subprocess.run(['gh', 'api', '-H', 'Accept: application/vnd.github+json',
             '-H', 'X-GitHub-Api-Version: 2026-03-10', path],
             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
             stderr=subprocess.DEVNULL, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Refused('GitHub CLI unavailable or API timeout') from exc
    if run.returncode:
        raise Refused('GitHub API unavailable, unauthorized or throttled')
    if len(run.stdout) > 8 * 1024 * 1024:
        raise Refused('Oversized GitHub API metadata')
    try:
        obj = json.loads(run.stdout)
    except (ValueError, UnicodeError) as exc:
        raise Refused('Malformed GitHub API response') from exc
    if not isinstance(obj, dict):
        raise Refused('Invalid GitHub API response type')
    return obj

def paged(path: str, field: str, pages: int) -> list[dict]:
    items = []
    seen = set()
    for page in range(1, pages + 1):
        suffix = ('&' if '?' in path else '?') + f'per_page=100&page={page}'
        batch = api(path + suffix).get(field)
        if not isinstance(batch, list) or any(not isinstance(x, dict) for x in batch):
            raise Refused(f'Invalid {field} page')
        for obj in batch:
            identifier = obj.get('id')
            if type(identifier) is not int or identifier <= 0:
                raise Refused(f'Invalid {field} identity')
            if identifier not in seen:
                seen.add(identifier)
                items.append(obj)
        if len(batch) < 100:
            return items
    raise Refused(f'Incomplete {field} pagination')

def candidate_name(name: object) -> bool:
    if not isinstance(name, str) or not 1 <= len(name) <= 140 or '..' in name or \
            '/' in name or '\\' in name or any(ord(c) < 32 for c in name):
        return False
    if re.search(r'(^|[-_. ])(?:logs?|reports?|coverage|screenshots?|source|symbols?|mapping|test-results?|lint|trace)([-_. ]|$)', name, re.I):
        return False
    return bool(re.search(r'(^|[-_. ])(?:apk|apks|xapk|android|installer|universal)([-_. ]|$)', name, re.I))

def probe(repo: str, branch: str | None, workflow: str | None, run_id: int | None,
          artifact_id: int | None, pages: int,
          run_attempt: int | None = None, head_sha: str | None = None) -> dict:
    if not REPO.fullmatch(repo) or pages < 1 or pages > 20:
        raise Refused('Invalid repository or pagination limit')
    if run_attempt is not None and run_attempt <= 0:
        raise Refused('Invalid pinned run attempt')
    if head_sha is not None and not SHA.fullmatch(head_sha.lower()):
        raise Refused('Invalid pinned source SHA')
    root = f'repos/{repo}'
    meta = api(root)
    selected_branch = branch or meta.get('default_branch')
    if not isinstance(selected_branch, str) or len(selected_branch) > 240 or \
            not selected_branch or '..' in selected_branch or any(c.isspace() for c in selected_branch):
        raise Refused('Invalid branch')
    flows = paged(root+'/actions/workflows', 'workflows', pages)
    flow_ids = {w['id']:w.get('name') for w in flows if w.get('state') == 'active' and isinstance(w.get('name'),str)}
    selection = None
    if workflow:
        matching = [id for id, name in flow_ids.items() if name == workflow or str(id) == workflow]
        if len(matching) != 1:
            raise Refused('Workflow name or ID unavailable/ambiguous')
        selection = matching[0]
    scoped_query = urllib.parse.urlencode({'branch': selected_branch, 'status': 'success'})
    runs = paged(root+'/actions/runs?'+scoped_query, 'workflow_runs', pages)
    runs = [r for r in runs if r.get('status')=='completed' and r.get('conclusion')=='success'
            and r.get('head_branch')==selected_branch and r.get('workflow_id') in flow_ids
            and (selection is None or r.get('workflow_id')==selection)
            and (run_id is None or r.get('id')==run_id)
            and (run_attempt is None or r.get('run_attempt')==run_attempt)
            and (head_sha is None or r.get('head_sha','').lower()==head_sha.lower())
            and type(r.get('run_attempt')) is int and r['run_attempt']>0
            and isinstance(r.get('head_sha'),str) and SHA.fullmatch(r['head_sha'].lower())]
    runs.sort(key=lambda r:(r.get('created_at') or '',r['id']),reverse=True)
    if not runs:
        raise Refused('No exact completed successful run in selected scope')
    selected = runs[0]
    run = selected['id']
    artifacts = paged(root+f'/actions/runs/{run}/artifacts', 'artifacts', pages)
    candidates = []
    for item in artifacts:
        checksum = item.get('digest')
        name = item.get('name')
        expiry = item.get('expires_at')
        size = item.get('size_in_bytes')
        if item.get('expired') is not False or not candidate_name(name) or \
                not isinstance(checksum,str) or not DIGEST.fullmatch(checksum.lower()) or \
                type(size) is not int or not 0 < size <= MAX_BYTES or not isinstance(expiry,str):
            continue
        try:
            expires_at = datetime.fromisoformat(expiry.replace('Z', '+00:00'))
            if expires_at.tzinfo is None or expires_at <= datetime.now(timezone.utc):
                continue
        except ValueError:
            continue
        if artifact_id is not None and artifact_id != item.get('id'):
            continue
        bound = item.get('workflow_run')
        if isinstance(bound, dict) and (bound.get('id') != run or bound.get('head_sha') != selected['head_sha']):
            continue
        candidates.append(item)
    if len(candidates) != 1:
        raise Refused(f'Artifact identity missing/ambiguous: {len(candidates)} eligible')
    a = candidates[0]
    return {
        'state':'LIVE_METADATA_CHECKED_NOT_DEVICE_QUALIFIED',
        'repository':repo,'branch':selected_branch,
        'workflow_id':selected['workflow_id'],'workflow_name':flow_ids[selected['workflow_id']],
        'run_id':run,'run_attempt':selected['run_attempt'],'head_sha':selected['head_sha'],
        'artifact_id':a['id'],'archive_name':a['name'],'zip_sha256':a['digest'].split(':',1)[1].lower(),
        'expires_at':a['expires_at'],'zip_api_url':f'https://api.github.com/{root}/actions/artifacts/{a["id"]}/zip',
        'apk_signing':'NOT_VERIFIED','physical_install':'NOT_QUALIFIED',
    }

def trusted_storage_url(url: str) -> bool:
    """Match the in-app redirect host boundaries without leaking signed URLs."""
    try:
        target=urllib.parse.urlsplit(url)
        host=(target.hostname or '').lower()
        if target.scheme!='https' or target.username is not None or target.password is not None \
                or target.port is not None or target.fragment or not host:
            return False
        return any(host==suffix or host.endswith('.'+suffix) for suffix in (
            'actions.githubusercontent.com', 'githubusercontent.com',
            'blob.core.windows.net'))
    except ValueError:
        return False

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Caller checks every Location before making a new request.


def _fetch_no_redirect(url: str, headers: dict[str,str]):
    opener=urllib.request.build_opener(_NoRedirect())
    request=urllib.request.Request(url,headers=headers,method='GET')
    try:
        return opener.open(request,timeout=30)
    except urllib.error.HTTPError as response:
        # 302 will be an HTTPError because the default redirect handler is off.
        if response.code==302:
            return response
        response.close()
        raise Refused('GitHub artifact request rejected or expired') from None
    except (OSError,TimeoutError,ValueError) as exc:
        raise Refused('Artifact transport failed; no installation') from exc


def _private_token() -> str:
    try:
        result=subprocess.run(['gh','auth','token'],stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=20,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise Refused('GitHub CLI authentication unavailable') from exc
    token=result.stdout.decode('utf-8','strict').strip()
    if result.returncode or not token or any(x in token for x in ('\n','\r',' ')):
        raise Refused('GitHub CLI authentication unavailable')
    return token  # Never print, log, write or attach to signed storage requests.


def verify_download(receipt: dict) -> dict:
    """Verified real ZIP transfer. API gets PAT; signed storage gets none."""
    api_url=receipt['zip_api_url']
    parts=urllib.parse.urlsplit(api_url)
    if parts.scheme!='https' or parts.hostname!='api.github.com' or \
            parts.username is not None or parts.password is not None or \
            parts.port is not None or parts.query or parts.fragment or \
            not re.fullmatch(r'/repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/actions/artifacts/[1-9][0-9]*/zip',parts.path):
        raise Refused('Invalid canonical artifact API endpoint')
    if not re.fullmatch(r'[0-9a-f]{64}',receipt.get('zip_sha256','')):
        raise Refused('Missing published SHA-256; cannot download')
    token=_private_token()
    api_headers={'Accept':'application/vnd.github+json',
        'X-GitHub-Api-Version':'2026-03-10',
        'Authorization': 'Bearer '+token}
    with tempfile.TemporaryDirectory(prefix='obtainx-r04-live-') as directory:
        path=Path(directory)/'artifact.zip'
        sha=hashlib.sha256()
        total=0
        current_url=api_url
        for hop in range(4):
            headers=api_headers if hop==0 else {'Accept':'application/octet-stream'}
            # All hops after the API receive no Authorization or Cookie headers.
            response=_fetch_no_redirect(current_url,headers)
            try:
                code=response.code
                if code==302:
                    location=response.headers.get('Location')
                    if hop==3 or not location or not trusted_storage_url(location):
                        raise Refused('Untrusted or excessive signed storage redirect')
                    current_url=location
                    continue
                if hop==0 or code!=200:
                    raise Refused('GitHub did not return a signed storage redirect')
                with path.open('wb') as output:
                    while True:
                        block=response.read(65536)
                        if not block:break
                        total+=len(block)
                        if total>MAX_BYTES:
                            raise Refused('Actual archive exceeds 1 GiB budget')
                        sha.update(block)
                        output.write(block)
                break
            except (OSError,TimeoutError) as exc:
                raise Refused('Artifact byte stream incomplete') from exc
            finally:
                response.close()
        else:
            raise Refused('Signed storage redirect budget exhausted')
        if total==0 or sha.hexdigest()!=receipt['zip_sha256']:
            raise Refused('Downloaded ZIP SHA-256 mismatch; no installation')
        with path.open('rb') as stream:
            if stream.read(4)!=b'PK\x03\x04':
                raise Refused('Archive ZIP signature invalid')
        receipt['zip_download']='LIVE_ZIP_BYTES_SHA256_PASS_NOT_APK_SIGNING'
        receipt['zip_bytes']=total
        receipt['transport']='API_PAT_THEN_NO_AUTH_SIGNED_STORAGE'
    return receipt

def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',required=True,help='owner/repo')
    p.add_argument('--branch')
    p.add_argument('--workflow')
    p.add_argument('--run-id',type=int)
    p.add_argument('--artifact-id',type=int)
    p.add_argument('--run-attempt',type=int,help='Require exact attempt (no implicit retry switch)')
    p.add_argument('--head-sha',help='Require exact 40-hex commit SHA')
    p.add_argument('--max-pages',type=int,default=10)
    p.add_argument('--download-verify',action='store_true',help='Explicit transient ZIP download; never installs')
    p.add_argument('--receipt',type=Path,help='Optional local JSON receipt path')
    args=p.parse_args()
    try:
        result=probe(args.repo,args.branch,args.workflow,args.run_id,args.artifact_id,args.max_pages,
                     run_attempt=args.run_attempt,head_sha=args.head_sha)
        if args.download_verify:
            result=verify_download(result)
        message=json.dumps(result,sort_keys=True,indent=2)
        if args.receipt:
            if args.receipt.exists() or args.receipt.is_symlink():
                raise Refused('Receipt already exists: no overwrite')
            args.receipt.parent.mkdir(parents=True,exist_ok=True)
            # Source/commit identities from private repos are sensitive metadata.
            # An exclusive private file also prevents a symlink race.
            flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0)
            fd=os.open(args.receipt,flags,0o600)
            with os.fdopen(fd,'w',encoding='utf-8') as out:
                out.write(message+'\n')
        print(message,flush=True)
        return 0
    except Refused as ex:
        print('OX_R04_LIVE_REFUSED '+str(ex),file=sys.stderr,flush=True)
        return 1

if __name__=='__main__':
    raise SystemExit(main())
