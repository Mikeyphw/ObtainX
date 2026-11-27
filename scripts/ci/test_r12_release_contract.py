from __future__ import annotations
import base64
import copy
import io
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

import r12_release_gate as gate
from r12_release_contract import ROOT, WORKFLOW, inspect_workflow
from r12_device_evidence import MATRIX, verify_matrix, load
from r00_source_contract import check_workflows, EXPECTED_WORKFLOWS
from obtainx_ci_policy import FULL_PROOFS, REPO_ID

HEAD = 'a'*40
TREE = 'b'*40
CERT = 'c'*64
DIGEST = 'd'*64
IDENT = {'repository': gate.REPO, 'source_sha': HEAD, 'source_tree': TREE, 'run_id': '123', 'run_attempt': '1'}

class ReleaseContractTests(unittest.TestCase):
    def test_manual_protected_separate_workflow(self):
        text = (ROOT / WORKFLOW).read_text()
        self.assertEqual(inspect_workflow(text), [])
        self.assertEqual(len(EXPECTED_WORKFLOWS), 6)
        files = {p.name:p.read_text() for p in (ROOT / '.github/workflows').glob('*.yml')}
        self.assertEqual(check_workflows(files), [])
        for changed in [
            text.replace('workflow_dispatch:', 'pull_request:'),
            text.replace('environment: obtainx-release-candidate', 'environment: unprotected'),
            text.replace('needs: build', 'needs: authorize'),
            text.replace('contents: read', 'contents: write'),
            text.replace('dart format --output=none --set-exit-if-changed', 'dart format'),
            text.replace('flutter test --no-pub', 'true'),
            text.replace('persist-credentials: false', 'persist-credentials: true'),
            text.replace('replica: [a, b]', 'replica: [a]'),
            text.replace('      - name: Compare independent builds and sign verified bytes only', '      - name: bypass'),
            text.replace('      - name: Retain exact unsigned build evidence', '      - name: Retain exact unsigned build evidence\n        if: false'),
        ]:
            with self.subTest(change=changed[:80]): self.assertTrue(inspect_workflow(changed))

    def test_protected_context_fail_closed(self):
        env = {'GITHUB_REPOSITORY': gate.REPO, 'GITHUB_EVENT_NAME':'workflow_dispatch', 'GITHUB_REF':'refs/heads/main',
               'GITHUB_REF_PROTECTED':'true','GITHUB_SHA':HEAD,'OX_EXPECTED_SHA':HEAD,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'}
        with patch.object(gate, 'identity', return_value={k:v for k,v in IDENT.items() if k not in ('run_id','run_attempt')}):
            self.assertEqual(gate.dispatch_guard(ROOT, HEAD, env), IDENT)
            for field, value in [('GITHUB_EVENT_NAME','pull_request'),('GITHUB_REF','refs/heads/branch'),('GITHUB_REF_PROTECTED','false'),('GITHUB_SHA',TREE),('OX_EXPECTED_SHA',TREE),('GITHUB_REPOSITORY','fork/ObtainX'),('GITHUB_RUN_ATTEMPT','')]:
                with self.subTest(field=field), self.assertRaises(gate.Refused): gate.dispatch_guard(ROOT, HEAD, dict(env, **{field:value}))

    def test_metadata_and_signer_strict(self):
        good = "package: name='dev.bikram.obtainx' versionCode='221003' versionName='2.21.0'\nsdkVersion:'26'\nnative-code: 'arm64-v8a'\n"
        self.assertEqual(gate.metadata(good, '2.21.0', 22100, 'arm64-v8a')['version_code'], 221003)
        for invalid in [good+'application-debuggable\n',good.replace('221003','221001'),good.replace('2.21.0','2.20.0'),good.replace('dev.bikram.obtainx','dev.bikram.obtainx.debug'),good.replace("'26'","'25'"),good.replace("'arm64-v8a'","'arm64-v8a' 'x86_64'")]:
            with self.assertRaises(gate.Refused):gate.metadata(invalid,'2.21.0',22100,'arm64-v8a')
        proof = 'Signer #1 certificate SHA-256 digest: '+CERT+'\n'
        self.assertEqual(gate.signer(proof,CERT),CERT)
        for invalid in ['',proof.replace(CERT,DIGEST),proof+proof.replace('#1','#2')]:
            with self.assertRaises(gate.Refused):gate.signer(invalid,CERT)

    def test_missing_credentials_and_wrong_alias(self):
        env = {k:'value' for k in gate.SECRETS}
        env.update(OX_RELEASE_KEYSTORE_B64=base64.b64encode(b'dummy fixture').decode(), OX_RELEASE_CERT_SHA256=CERT)
        self.assertEqual(gate.validate_signing_inputs(env),(b'dummy fixture',CERT))
        for k in list(gate.SECRETS)+['OX_RELEASE_CERT_SHA256']:
            with self.subTest(k=k), self.assertRaises(gate.Refused):gate.validate_signing_inputs(dict(env,**{k:''}))
        for k,v in [('OX_RELEASE_KEYSTORE_B64','not valid!!!'),('OX_RELEASE_KEY_ALIAS','--unsafe')]:
            # Aliases beginning with option syntax are still passed as one value;
            # invalid whitespace/characters must never reach subprocess.
            if k.endswith('ALIAS'):v='bad alias\n'
            with self.assertRaises(gate.Refused):gate.validate_signing_inputs(dict(env,**{k:v}))

    def test_zip_payload_scan_real_bytes_and_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'fixture.apk'
            def write(rows):
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore',UserWarning)
                    with zipfile.ZipFile(p,'w') as z:
                        for n,v in rows:z.writestr(n,v)
            base=[('AndroidManifest.xml',b'fixture'),('classes.dex',b'fixture')]
            write(base)
            self.assertEqual(set(gate.apk_entries(p)),{'AndroidManifest.xml','classes.dex'})
            self.assertFalse(gate.has_apk_signing_block(p))
            for extra in [('classes.dex',b'other'),('../escape',b'other'),('secret',b'-----BEGIN '+b'PRIVATE KEY-----')]:
                write(base+[extra])
                with self.subTest(extra=extra[0]), self.assertRaises(gate.Refused):gate.apk_entries(p)
            # Split private-key markers across reader chunk boundaries.
            with self.assertRaises(gate.Refused):gate.scan_stream(io.BytesIO(b'x'*(1024*1024-7)+b'-----BEGIN '+b'PRIVATE KEY-----'),'fixture')

    def test_maven_coordinates_and_osv(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=root/'caches/modules-2/files-2.1/g/a/2/d/a.pom';p.parent.mkdir(parents=True)
            p.write_text('<project><licenses><license><name>MIT</name></license></licenses></project>')
            graph='+--- g:a:1 -> 2\n+--- g:b -> 3 (c)\n+--- project :plugin\n\\--- g:a:2 (*)\n'
            native=gate.maven_inventory(graph,root)
            self.assertEqual([(x['name'],x['version']) for x in native],[('a','2'),('b','3')]);self.assertEqual(native[0]['licenses'][0]['name'],'MIT')
            for invalid in ['+--- g:a:1 FAILED','+--- g:a','+--- ../:a:1']:
                with self.assertRaises(gate.Refused):gate.maven_inventory(invalid,root)
        pub=[{'name':'archive','version':'4.3.0','source':'hosted','scope':'direct main','sha256':DIGEST}]
        result=gate.vulnerability_audit(pub,native,lambda batch:{'results':[{} for _ in batch]})
        self.assertEqual(result['status'],'NO_KNOWN_FINDINGS')
        self.assertEqual(gate.vulnerability_audit(pub,native,lambda batch:{'results':[{'vulns':[{'id':'TEST-1'}]} for _ in batch]})['status'],'FAIL')
        for response in [{'results':[]},{'results':[{'next_page_token':'x'}]*3}]:
            with self.assertRaises(gate.Refused):gate.vulnerability_audit(pub,native,lambda batch:response)
        sbom=gate.sbom(IDENT,pub,native);self.assertEqual(len(sbom['components']),3);self.assertEqual(sbom['bomFormat'],'CycloneDX')

    def test_reproducibility_requires_two_exact_builds(self):
        row=dict(IDENT,schema='obtainx.r12.unsigned-build.v1',replica='a',runner='a'*64,apks={'a':{'sha256':DIGEST}},dependencies_sha256=DIGEST,sbom_sha256=DIGEST,toolchain_sha256=DIGEST)
        other=dict(row,replica='b',runner='b'*64)
        self.assertEqual(gate.compare_builds(row,other,IDENT),row['apks'])
        for mutation in [dict(other,runner=row['runner']),dict(other,source_sha=TREE),dict(other,run_attempt='2'),dict(other,apks={'a':{'sha256':CERT}}),dict(other,toolchain_sha256=CERT)]:
            with self.assertRaises(gate.Refused):gate.compare_builds(row,mutation,IDENT)

    def test_exact_main_hosted_ci_and_newer_failure(self):
        by_id={v[0]:(k,v) for k,v in FULL_PROOFS.items()}
        def fetch(path, *, fail=False, stale=False, skip=False):
            if '/workflows/' in path:
                workflow=int(path.split('/')[3]);lane,(_,_,_)=by_id[workflow]
                row={'workflow_id':workflow,'head_sha':TREE if stale else HEAD,'head_branch':'main','event':'workflow_dispatch','status':'completed','conclusion':'success','repository':{'id':REPO_ID},'head_repository':{'id':REPO_ID},'id':workflow,'run_attempt':1}
                rows=[row,dict(row,id=workflow+100,conclusion='failure')] if fail else [row]
                return {'total_count':len(rows),'workflow_runs':rows}
            workflow=int(path.split('/')[3]);_,(_,job,steps)=by_id[workflow]
            return {'total_count':1,'jobs':[{'id':workflow+1000,'head_sha':HEAD,'name':job,'conclusion':'success','steps':[{'name':s,'conclusion':'skipped' if skip else 'success'} for s in steps]}]}
        self.assertEqual(len(gate.hosted_ci(HEAD,fetch)['proofs']),6)
        for flag in ('fail','stale','skip'):
            with self.subTest(flag=flag), self.assertRaises(gate.Refused):gate.hosted_ci(HEAD,lambda path:fetch(path,**{flag:True}))

    def test_device_matrix_refuses_wrong_bytes_stale_and_missing_lane(self):
        candidate=dict(IDENT,schema='obtainx.r12.signed-candidate.v1',certificate_sha256=CERT,package_status='SIGNED_CANDIDATE_VERIFIED',publication_authorized=False,SOURCE_PASS='PASS_BUILD_LANES',HOSTED_CI_PASS='PASS_EXACT_MAIN_FULL_JOBS',apks={f'app-{abi}-normal-release.apk':{'sha256':DIGEST} for abi in gate.ABIS})
        matrix=dict(IDENT,schema='obtainx.r12.device-matrix.v1',certificate_sha256=CERT,lanes={k:{'status':'PENDING_EXTERNAL','reason':'no approved fixture'} for k in MATRIX})
        with tempfile.TemporaryDirectory() as t:
            d=Path(t);self.assertEqual(len(verify_matrix(candidate,matrix,d)['pending']),len(MATRIX))
            for n in MATRIX:
                f=d/(n+'.log');f.write_text('local fixture only, not actual device evidence');matrix['lanes'][n]=dict(status='PASS',apk='app-arm64-v8a-normal-release.apk',apk_sha256=DIGEST,observed_utc='2026-11-26T00:00:00Z',reviewer='fixture',backend=n,android_sdk=36,authorized_fixture=True,evidence=[{'path':f.name,'sha256':gate.digest(f)}])
            result=verify_matrix(candidate,matrix,d);self.assertEqual(result['device_evidence_status'],'READY_FOR_INDEPENDENT_REVIEW');self.assertFalse(result['RELEASE_QUALIFIED'])
            for mutation in ('sha','lane','apk','digest','consent','reuse'):
                bad=copy.deepcopy(matrix);first=next(iter(MATRIX));second=list(MATRIX)[1]
                if mutation=='sha':bad['source_sha']=TREE
                if mutation=='lane':bad['lanes'].pop(first)
                if mutation=='apk':bad['lanes'][first]['apk_sha256']=CERT
                if mutation=='digest':bad['lanes'][first]['evidence'][0]['sha256']=CERT
                if mutation=='consent':bad['lanes'][first]['authorized_fixture']=False
                if mutation=='reuse':bad['lanes'][second]['evidence']=bad['lanes'][first]['evidence']
                with self.subTest(mutation=mutation),self.assertRaises(gate.Refused):verify_matrix(candidate,bad,d)
            f=d/'duplicate.json';f.write_text('{"schema":1,"schema":2}')
            with self.assertRaises(gate.Refused):load(f)

    def test_unsigned_build_invokes_only_reviewed_commands(self):
        import os
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'android/app').mkdir(parents=True)
            (root / 'bin').mkdir()
            shutil.copyfile(ROOT / 'build.sh', root / 'build.sh')
            for name in ('flutter', 'git'):
                binary = root / 'bin' / name
                binary.write_text('#!/bin/sh\nprintf "' + name + ' %s\\n" "$*" >> "$TRACE"\n')
                binary.chmod(0o700)
            trace = root / 'trace'
            env = dict(os.environ, PATH=str(root / 'bin') + ':' + os.environ['PATH'], TRACE=str(trace))
            result = subprocess.run(['bash', str(root / 'build.sh')], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(trace.read_text().splitlines(), ['flutter pub get --enforce-lockfile', 'git diff --exit-code -- pubspec.lock', 'flutter build apk --release --split-per-abi --flavor normal --no-pub', 'flutter build apk --release --split-per-abi --flavor fdroid -t lib/main_fdroid.dart --no-pub'])
            (root / 'android/app/key.properties').touch()
            trace.unlink()
            result = subprocess.run(['bash', str(root / 'build.sh')], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(trace.exists())

    def test_legacy_signer_and_implicit_sync_refused(self):
        result=subprocess.run(['bash',str(ROOT/'sign.sh')],capture_output=True,text=True)
        self.assertEqual(result.returncode,2)
        result=subprocess.run(['bash',str(ROOT/'build.sh'),'sync'],capture_output=True,text=True)
        self.assertEqual(result.returncode,2)
        script=(ROOT/'build.sh').read_text();self.assertNotRegex(script,r'git\s+(fetch|push|merge)|flutter\s+upgrade|gpg\s')

if __name__=='__main__':unittest.main()
