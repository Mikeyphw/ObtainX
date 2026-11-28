from __future__ import annotations
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import final_acceptance_campaign as campaign
import r12_device_evidence as device
import r12_release_gate as gate
from test_obtainx_ci_optimization_opt09_dedup import Fixture

HEAD='a'*40
TREE='b'*40
CERT='c'*64
IDENT={'repository':gate.REPO,'source_sha':HEAD,'source_tree':TREE,'pubspec_lock_sha256':'d'*64}

class CampaignTests(unittest.TestCase):
    def test_actual_inventory_and_historical_ids(self):
        result=campaign.audit_inventory()
        self.assertEqual(len(result['rows']),139)
        self.assertEqual(len({x['id'] for x in result['rows']}),139)
        self.assertTrue(all(x['review_status']=='PENDING_INDEPENDENT_PROMISE_REVIEW' for x in result['rows']))
        self.assertTrue(all(len(digest)==64 for x in result['rows'] for digest in x['current_reference_digests'].values()))
        providers=campaign.provider_inventory()
        self.assertIn('GitHub',providers)
        self.assertIn('RuStore',providers)
        self.assertEqual(list(providers)[-1],'HTML')
        self.assertTrue(all(x['live_acceptance']=='PENDING_EXTERNAL' for x in providers.values()))

    def test_provider_and_promise_pending_never_accepted(self):
        candidate=dict(IDENT, certificate_sha256=CERT)
        matrix=dict(candidate,schema='obtainx.final-acceptance.providers.v1',providers={k:{'status':'PENDING_EXTERNAL','reason':'fixture unavailable'} for k in campaign.provider_inventory()})
        inventory=campaign.audit_inventory()
        review=dict(IDENT,schema='obtainx.final-acceptance.promise-review.v1',historical_audit_sha256=inventory['historical_audit_sha256'],promises={x['id']:{'status':'PENDING','reason':'needs review'} for x in inventory['rows']})
        with tempfile.TemporaryDirectory() as t:
            directory=Path(t)
            self.assertEqual(campaign.provider_review(candidate,matrix,directory)['live_provider_acceptance'],'PENDING_INDEPENDENT_REVIEW')
            bad=copy.deepcopy(matrix);bad['providers'].pop('GitHub')
            with self.assertRaises(gate.Refused):campaign.provider_review(candidate,bad,directory)
            bad=copy.deepcopy(matrix);bad['providers']['GitHub']['status']='PASS'
            with self.assertRaises(gate.Refused):campaign.provider_review(candidate,bad,directory)
            self.assertEqual(campaign.promise_review(IDENT,inventory,review,directory)['historical_acceptance'],'PENDING_INDEPENDENT_REVIEW')
            bad=copy.deepcopy(review);bad['promises'].pop(next(iter(bad['promises'])))
            with self.assertRaises(gate.Refused):campaign.promise_review(IDENT,inventory,bad,directory)
            bad=copy.deepcopy(review);bad['source_tree']='0'*40
            with self.assertRaises(gate.Refused):campaign.promise_review(IDENT,inventory,bad,directory)

    def test_receipt_exclusive_private(self):
        with tempfile.TemporaryDirectory() as t:
            directory=Path(t);p=directory/'receipt.json'
            sha=campaign.private_receipt(p,{'state':'PENDING'})
            self.assertEqual(gate.digest(p),sha)
            self.assertEqual(p.stat().st_mode & 0o777,0o600)
            with self.assertRaises(FileExistsError):campaign.private_receipt(p,{'state':'PASS'})
            directory.chmod(0o755)
            with self.assertRaises(gate.Refused):campaign.private_receipt(directory/'other.json',{})

    def test_pinned_live_route_calls_real_helpers_and_rechecks(self):
        args=SimpleNamespace(action='provider',provider_repo='a/b',branch='main',workflow='1',run_id=1,run_attempt=2,artifact_id=3,provider_head=HEAD,download_verify=True)
        proof={'zip_sha256':'a'*64,'artifact_id':3}
        with patch.object(campaign.actions,'probe',side_effect=[proof,dict(proof,artifact_id=4)]) as probe, patch.object(campaign.actions,'verify_download',return_value=dict(proof,zip_download='verified')) as download:
            with self.assertRaises(gate.Refused):campaign.execute(args,IDENT)
            self.assertEqual(probe.call_count,2);download.assert_called_once_with(proof)
        args.run_attempt=0
        with self.assertRaises(gate.Refused):campaign.execute(args,IDENT)

    def test_device_profile_consent_and_no_write(self):
        with patch.object(campaign.physical,'adb') as adb:
            with self.assertRaises(RuntimeError):campaign.physical.profile('fixture','no')
            adb.assert_not_called()
        values=['device','36','arm64-v8a','pt-BR','420']
        with patch.object(campaign.physical,'adb',side_effect=values) as adb:
            data=campaign.physical.profile('fixture','I_AUTHORIZE_READ_ONLY_DEVICE_PROBE')
            self.assertEqual(data['android_sdk'],36);self.assertFalse(data['device_writes'])
            self.assertEqual(adb.call_args_list[0].args,('fixture','get-state'))
            self.assertTrue(all(c.args[1:3]==('shell','getprop') for c in adb.call_args_list[1:]))

    def test_candidate_rechecks_all_provenance(self):
        with tempfile.TemporaryDirectory() as t:
            directory=Path(t)
            def write(name,obj):
                p=directory/name;p.write_text(json.dumps(obj,sort_keys=True));return gate.digest(p)
            ci=gate.hosted_ci(HEAD,TREE,Fixture().api)
            apks={f'app-{abi}-normal-release.apk':{'package':gate.PACKAGE,'abi':abi,'version_code':221000+i,'version_name':'2.21.0','sha256':'e'*64,'payload':{'classes.dex':'f'*64},'certificate_sha256':CERT} for abi,i in gate.ABIS.items()}
            unsigned={k:{a:b for a,b in row.items() if a!='certificate_sha256'} for k,row in apks.items()}
            inventory={'pub':[],'maven':[]}
            advisory={'queries':gate.osv_queries([],[]),'status':'NO_KNOWN_FINDINGS','findings':[]}
            hashes={'dependencies_sha256':write('dependencies.json',inventory),'gradle_inventory_sha256':write('gradle-dependencies.txt',{'fixture':True}),'sbom_sha256':write('sbom.cdx.json',{}),'advisories_sha256':write('advisories.json',advisory),'ci_sha256':write('ci.json',ci),'toolchain_sha256':write('toolchain.json',{})}
            ident=dict(IDENT,run_id='1',run_attempt='1')
            candidate=dict(ident,**hashes,schema='obtainx.r12.signed-candidate.v1',certificate_sha256=CERT,apks=apks,reproducibility='UNSIGNED_EXACT_BYTES_MATCH',package_status='SIGNED_CANDIDATE_VERIFIED',SOURCE_PASS='PASS_BUILD_LANES',HOSTED_CI_PASS='PASS_'+ci['mode'],RELEASE_QUALIFIED=False,publication_authorized=False)
            records=[]
            for replica, runner in [('a','1'*64),('b','2'*64)]:
                row=dict(ident,**hashes,schema='obtainx.r12.unsigned-build.v1',apks=unsigned,replica=replica,runner=runner)
                write(f'{replica}-advisories.json',advisory);write(f'{replica}-gradle-dependencies.txt',{'fixture':True})
                records.append(row)
            def seal():
                candidate['unsigned_builds']=[write(f'{r}-build.json',obj) for r,obj in zip(('a','b'),records)];write('candidate.json',candidate)
            seal()
            with patch.object(device,'inspect_apks',return_value=apks):
                self.assertEqual(device.verify_candidate(directory,IDENT,CERT),candidate)
                records[1]['runner']=records[0]['runner'];seal()
                with self.assertRaises(gate.Refused):device.verify_candidate(directory,IDENT,CERT)
                records[1]['runner']='2'*64;seal()
                write('b-advisories.json',dict(advisory,findings=['changed']))
                with self.assertRaises(gate.Refused):device.verify_candidate(directory,IDENT,CERT)
                write('b-advisories.json',advisory)
                ci['proofs']['source']['decisive_steps']=[]
                sha=write('ci.json',ci);candidate['ci_sha256']=sha
                for record in records:record['ci_sha256']=sha
                seal()
                with self.assertRaises(gate.Refused):device.verify_candidate(directory,IDENT,CERT)

if __name__=='__main__':unittest.main()
