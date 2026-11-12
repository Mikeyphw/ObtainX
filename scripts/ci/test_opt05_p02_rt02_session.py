"""OPT05 P02 single-session Android source, events, and receipt regressions.

These tests do not fake or qualify Android installation; hosted API36 is
mandatory for real device evidence.
"""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import opt05_p02_rt02_session as P
import r02_rt02_contract as C
import r02_rt02_hosted as H

ROOT=Path(__file__).resolve().parents[2]

class P02EventOrdering(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ox-opt05-p02-events-')
        self.log=Path(self.tmp.name)/'flutter.private.log'
    def tearDown(self):self.tmp.cleanup()
    def write(self,*events):
        self.log.write_text(''.join('I/flutter: OX_R02_P02_EVENT='+e+'\n' for e in events))
    def test_valid_ordered_events(self):
        self.write(*[c+':'+s for c,s in P.EVENTS])
        self.assertEqual(P.events_from_log(self.log),P.EVENTS)
    def test_duplicate_event_refused(self):
        self.write('standalone:START','standalone:START')
        with self.assertRaises(P.Refused):P.events_from_log(self.log)
    def test_dart_event_order_refused(self):
        self.write('standalone:START','split:START')
        with self.assertRaises(P.Refused):P.events_from_log(self.log)
    def test_missing_return_before_ack_refused(self):
        self.write('standalone:START','standalone:INSTALL_CALL','standalone:ACKED')
        with self.assertRaises(P.Refused):P.events_from_log(self.log)
    def test_oversized_log_refused(self):
        self.log.write_bytes(b'a'*(P.MAX_LOG+1))
        with self.assertRaises(P.Refused):P.events_from_log(self.log)
    def test_empty_log_allowed_only_before_events(self):
        self.assertEqual(P.events_from_log(self.log),())

class SourceMutations(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ox-opt05-p02-mutations-')
        self.root=Path(self.tmp.name)
        for rel in C.PATHS:
            f=self.root/rel;f.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/rel,f)
    def tearDown(self):self.tmp.cleanup()
    def mutation(self,path,old,new):
        f=self.root/path
        data=f.read_text();self.assertEqual(data.count(old),1,'source anchor drift: '+old)
        f.write_text(data.replace(old,new,1))
        errors=C.inspect(self.root)
        self.assertTrue(errors, 'mutation escaped gate: '+path)
    def test_valid_single_session_contract(self):
        self.assertEqual(C.inspect(self.root),[])
    def test_two_flutter_invocations_refused(self):
        self.mutation(C.P02_HOST, "args=['flutter','test'", "args=['echo','test'")
    def test_host_ack_before_proof_refused(self):
        self.mutation(C.P02_HOST, 'state.acks[pending].set()', 'pass  # no acknowledgement')
    def test_split_missing_android_proof_refused(self):
        self.mutation(C.P02_HOST, 'base.installed_state(1 if pending', 'base.fake_installed_state(1 if pending')
    def test_production_stock_installer_required(self):
        self.mutation(C.P02_DART,'StockInstaller(SettingsProvider()).installApk(', 'FakeInstaller().installApk(')
    def test_fixture_digest_required(self):
        self.mutation(C.P02_DART, 'sha256.convert(bytes).toString()!=expected','false')
    def test_no_host_barrier_bypass(self):
        self.mutation(C.P02_DART,'await awaitHostAck(scenario)', 'await Future<void>.delayed(Duration.zero)')
    def test_one_session_receipt_requirement(self):
        self.mutation(C.HOST, "'flutter_launches']=1", "'flutter_launches']=2")
    def test_strict_emulator_source_preserved(self):
        self.mutation(C.HOST, "'host_acknowledgement_order']=list(CASES)",
                      "'host_acknowledgement_order']=[]")
    def test_no_android_fixture_adb_install(self):
        self.mutation(C.P02_DART,'result.isSuccess,isTrue','result.isError,isTrue')

class ReceiptProof(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ox-opt05-p02-receipt-')
        self.root=Path(self.tmp.name);self.sha='a'*40;self.run='123'
        self.data={'schema':2,'status':'PASS_TWO_ANDROID_SYSTEM_SESSIONS',
                   'source_sha':self.sha,'run_id':self.run,
                   'hosted_emulator_only':True,'physical_device_qualified':False,
                   'full_r02_matrix_qualified':False,'release_qualified':False,
                   'publication_allowed':False,'installer_backend':'production StockInstaller',
                   'flutter_launches':1,'host_acknowledgement_order':['standalone','split'],
                   'dart_event_order':[c+':'+s for c,s in P.EVENTS],
                   'session_log_sha256':'e'*64,
                   'scenarios':[{'scenario':'standalone','version_code':1,
                                 'installed_path_count':1,'config_x86_64_present':False,
                                 'android_confirmations':1,'approval_path':'explicit_dialog'},
                                {'scenario':'split','version_code':2,
                                 'installed_path_count':2,'config_x86_64_present':True,
                                 'android_confirmations':0,'approval_path':'platform_committed_no_dialog'}]}
    def tearDown(self):self.tmp.cleanup()
    def verify(self):
        (self.root/'rt02-receipt.json').write_text(json.dumps(self.data))
        with patch.object(H,'identity_check',return_value=(self.sha,self.run)):
            return H.verify(self.root)
    def test_valid_receipt(self):self.assertEqual(self.verify(),0)
    def test_receipt_requires_one_launch(self):
        self.data['flutter_launches']=2
        with self.assertRaises(H.Refused):self.verify()
    def test_missing_host_ack_refused(self):
        self.data['host_acknowledgement_order']=['standalone']
        with self.assertRaises(H.Refused):self.verify()
    def test_wrong_event_order_refused(self):
        self.data['dart_event_order'].reverse()
        with self.assertRaises(H.Refused):self.verify()
    def test_missing_session_log_hash_refused(self):
        self.data['session_log_sha256']='x'*64
        with self.assertRaises(H.Refused):self.verify()
    def test_split_invalid_installed_state_refused(self):
        self.data['scenarios'][1]['config_x86_64_present']=False
        with self.assertRaises(H.Refused):self.verify()
    def test_standalone_missing_approval_refused(self):
        self.data['scenarios'][0]['android_confirmations']=0
        with self.assertRaises(H.Refused):self.verify()
    def test_release_qualification_must_remain_false(self):
        self.data['release_qualified']=True
        with self.assertRaises(H.Refused):self.verify()

if __name__=='__main__':unittest.main()
