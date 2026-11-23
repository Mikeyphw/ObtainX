#!/usr/bin/env python3
"""Mock real GitHub API identity/expiry/auth negative cases for R04 live probe."""
from __future__ import annotations
import importlib.util
import hashlib
import io
from unittest.mock import Mock
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('r04_live_acceptance',
    ROOT/'scripts/ci/r04_live_acceptance.py')
MODULE=importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

SHA='aabbccddeeff00112233445566778899aabbccdd'
CHECKSUM='sha256:'+'a'*64

def fake_api(path):
    if path == 'repos/o/r':return {'default_branch':'main'}
    if '/actions/workflows' in path:
        return {'workflows':[{'id':7,'name':'APK Build','state':'active'}]}
    if '/actions/runs/' in path and '/artifacts' in path:
        return {'artifacts':[{'id':41,'name':'android-arm64-apk',
          'digest':CHECKSUM,'expired':False,'size_in_bytes':190,
          'expires_at':'2099-01-01T00:00:00Z',
          'workflow_run':{'id':12,'head_sha':SHA}}]}
    if '/actions/runs?' in path:
        return {'workflow_runs':[{'id':12,'workflow_id':7,'run_attempt':2,
          'status':'completed','conclusion':'success','head_branch':'main',
          'head_sha':SHA,'created_at':'2026-11-15T20:00:00Z'}]}
    raise AssertionError(path)

class LiveAcceptanceTests(unittest.TestCase):
    def test_exact_live_identity_and_no_device_qualification(self):
        with patch.object(MODULE,'api',side_effect=fake_api):
            row=MODULE.probe('o/r','main','7',12,41,5)
        self.assertEqual(row['state'],'LIVE_METADATA_CHECKED_NOT_DEVICE_QUALIFIED')
        self.assertEqual(row['artifact_id'],41)
        self.assertEqual(row['head_sha'],SHA)
        self.assertEqual(row['run_attempt'],2)
        self.assertEqual(row['physical_install'],'NOT_QUALIFIED')
        self.assertEqual(row['apk_signing'],'NOT_VERIFIED')
    def test_changed_artifact_id_refused(self):
        with patch.object(MODULE,'api',side_effect=fake_api):
            with self.assertRaises(MODULE.Refused):
                MODULE.probe('o/r','main','7',12,42,5)
    def test_duplicate_installable_candidates_refused(self):
        def duplicate(path):
            obj=fake_api(path)
            if 'artifacts' in obj:
                obj['artifacts'].append({**obj['artifacts'][0], 'id':42})
            return obj
        with patch.object(MODULE,'api',side_effect=duplicate):
            with self.assertRaises(MODULE.Refused):
                MODULE.probe('o/r','main','7',12,None,5)
    def test_expired_archives_refused(self):
        def expired(path):
            obj=fake_api(path)
            if 'artifacts' in obj:
                obj['artifacts'][0]['expires_at']='2020-01-01T00:00:00Z'
            return obj
        with patch.object(MODULE,'api',side_effect=expired):
            with self.assertRaises(MODULE.Refused):
                MODULE.probe('o/r','main','7',12,None,5)
    def test_private_auth_failure_never_qualifies(self):
        with patch.object(MODULE,'api',side_effect=MODULE.Refused('401')):
            with self.assertRaises(MODULE.Refused):
                MODULE.probe('o/r','main','7',12,41,5)
    def test_no_logs_source_or_traversal_can_be_installed(self):
        for name in ['ci-logs','build-source','../android-apk',
                     'source.zip','report.apk','apk-debug-symbols']:
            self.assertFalse(MODULE.candidate_name(name),name)
    def test_run_attempt_and_commit_are_exact_pins(self):
        with patch.object(MODULE,'api',side_effect=fake_api):
            self.assertEqual(MODULE.probe('o/r','main','7',12,41,5,
                run_attempt=2,head_sha=SHA)['run_attempt'],2)
            with self.assertRaises(MODULE.Refused):
                MODULE.probe('o/r','main','7',12,41,5,run_attempt=3)
            with self.assertRaises(MODULE.Refused):
                MODULE.probe('o/r','main','7',12,41,5,head_sha='b'*40)
    def test_branch_query_parameters_are_encoded_not_injected(self):
        seen=[]
        def scoped(path):
            seen.append(path)
            if '/actions/runs?' in path:
                return {'workflow_runs': []}
            return fake_api(path)
        with patch.object(MODULE,'api',side_effect=scoped):
            with self.assertRaises(MODULE.Refused):
                MODULE.probe('o/r','feature/a&status=failure',None,None,None,5)
        query=''.join(x for x in seen if '/actions/runs?' in x)
        self.assertIn('branch=feature%2Fa%26status%3Dfailure',query)
        self.assertEqual(query.count('status='),1)
    def test_signed_redirect_never_receives_pat_or_cookies(self):
        # This is the exact transport seam: initial API has PAT, 302 storage
        # URL gets only application/octet-stream, regardless of private auth.
        blob=b'PK\x03\x04'+b'data'
        target='https://objects.githubusercontent.com/temp?sig=fake'
        calls=[]
        class FakeResponse:
            def __init__(self,code,data=b'',headers=None):
                self.code=code;self.headers=headers or {};self.data=io.BytesIO(data)
            def read(self,size=-1):return self.data.read(size)
            def close(self):pass
        def fetch(url,headers):
            calls.append((url,dict(headers)))
            if len(calls)==1:
                return FakeResponse(302,headers={'Location':target})
            return FakeResponse(200,blob)
        receipt={'zip_api_url':'https://api.github.com/repos/o/r/actions/artifacts/41/zip',
                 'zip_sha256':hashlib.sha256(blob).hexdigest()}
        with patch.object(MODULE,'_private_token',return_value='SECRET'),\
             patch.object(MODULE,'_fetch_no_redirect',side_effect=fetch):
            result=MODULE.verify_download(receipt)
        self.assertEqual(result['zip_bytes'],len(blob))
        self.assertEqual(result['transport'],'API_PAT_THEN_NO_AUTH_SIGNED_STORAGE')
        self.assertEqual(len(calls),2)
        self.assertIn('Bearer SECRET',calls[0][1]['Authorization'])
        self.assertNotIn('Authorization',calls[1][1])
        self.assertNotIn('Cookie',calls[1][1])
        self.assertNotIn('SECRET',str(calls[1]))
    def test_untrusted_storage_redirect_is_refused_before_fetch(self):
        seen=[]
        class FakeResponse:
            code=302
            headers={'Location':'https://objects.githubusercontent.com.attacker.invalid/archive'}
            def close(self):pass
        def fetch(url,headers):
            seen.append(url)
            return FakeResponse()
        receipt={'zip_api_url':'https://api.github.com/repos/o/r/actions/artifacts/41/zip',
                 'zip_sha256':'a'*64}
        with patch.object(MODULE,'_private_token',return_value='SECRET'),\
             patch.object(MODULE,'_fetch_no_redirect',side_effect=fetch):
            with self.assertRaises(MODULE.Refused):
                MODULE.verify_download(receipt)
        self.assertEqual(len(seen),1)
    def test_zip_digest_mismatch_has_no_positive_receipt(self):
        class FakeResponse:
            code=302;headers={'Location':'https://objects.githubusercontent.com/file'}
            def close(self):pass
        class ByteResponse:
            code=200;headers={}
            def __init__(self):self.value=io.BytesIO(b'PK\x03\x04mismatch')
            def read(self,size=-1):return self.value.read(size)
            def close(self):pass
        receipt={'zip_api_url':'https://api.github.com/repos/o/r/actions/artifacts/41/zip',
                 'zip_sha256':'a'*64}
        with patch.object(MODULE,'_private_token',return_value='SECRET'),\
             patch.object(MODULE,'_fetch_no_redirect',side_effect=[FakeResponse(),ByteResponse()]):
            with self.assertRaises(MODULE.Refused):
                MODULE.verify_download(receipt)
        self.assertNotIn('zip_download',receipt)
    def test_storage_rejects_cleartext_ports_and_userinfo(self):
        for url in ('http://objects.githubusercontent.com/a',
                    'https://user:pass@objects.githubusercontent.com/a',
                    'https://objects.githubusercontent.com:444/a',
                    'https://objects.githubusercontent.com.attacker.com/a'):
            self.assertFalse(MODULE.trusted_storage_url(url))

    def test_invalid_repo_refused_before_network(self):
        with patch.object(MODULE,'api',side_effect=AssertionError('network')):
            with self.assertRaises(MODULE.Refused):
                MODULE.probe('attacker.invalid/o/r',None,None,None,None,5)

if __name__=='__main__':
    unittest.main(verbosity=2)
