"""RT02C source, archive fixture, and fail-closed negative runtime receipt tests."""
from __future__ import annotations
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/ci'))

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module
C=load('r02_rt02c_contract','scripts/ci/r02_rt02c_contract.py')
F=load('r02_rt02c_fixture','scripts/ci/r02_rt02c_fixture.py')
H=load('r02_rt02c_hosted','scripts/ci/r02_rt02c_hosted.py')

class SourceMutations(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(prefix='ox-rt02c-source-')
        self.root=Path(self.t.name)
        for name in C.PATHS:
            src=ROOT/name;dst=self.root/name;dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(src,dst)
    def tearDown(self):self.t.cleanup()
    def mutation(self,rel,original,changed):
        path=self.root/rel;text=path.read_text()
        self.assertIn(original,text,'stale test anchor '+original)
        path.write_text(text.replace(original,changed,1))
        self.assertNotEqual(C.inspect(self.root),[],f'mutation escaped: {rel} {original}')
    def test_valid_source(self):self.assertEqual(C.inspect(self.root),[])
    def test_new_workflow_allowlist(self):
        self.mutation(C.R00,"'obtainx-r02-rt02c.yml'","'rogue-release.yml'")
    def test_new_workflow_mandatory(self):
        self.mutation(C.WF,'permissions:\n  contents: read','permissions:\n  contents: write')
    def test_sha_checkout_required(self):
        self.mutation(C.WF,'test "$(git rev-parse HEAD)" = "$OX_EXPECTED_SHA"','true')
    def test_action_pin_required(self):
        self.mutation(C.WF,'@a421e43855164a8197daf9d8d40fe71c6996bb0d','@main')
    def test_no_older_sdk(self):
        self.mutation(C.WF,'api-level: 36','api-level: 34')
    def test_no_kvm_bypass(self):
        self.mutation(C.WF,'test -c /dev/kvm','echo skip')
    def test_prebuild_mandatory(self):
        self.mutation(C.WF,'python3 -B scripts/ci/r02_rt02c_fixture.py --out','echo fake-build --out')
    def test_independent_verification_mandatory(self):
        self.mutation(C.WF,'python3 -B scripts/ci/r02_rt02c_hosted.py verify --out','echo never-verify --out')
    def test_evidence_upload_mandatory(self):
        self.mutation(C.WF,'rt02c-progress.json','raw-test-logs.txt')
    def test_no_unaudited_source_gate(self):
        self.mutation(C.SOURCE_WF,'python3 scripts/ci/r02_rt02c_contract.py --check','echo pass')
    def test_no_mock_installer(self):
        self.mutation(C.DART,'StockInstaller(SettingsProvider()).installApk(','fakeInstaller(')
    def test_owned_foreground_gate_required(self):
        self.mutation(C.DART, 'owner.sealForHandoff(nativeCancelable: true)', 'true')
    def test_native_gate_dispatch_required(self):
        self.mutation(C.DART, "installOptions: {'r02fP03Gate': owner}", 'installOptions: {}')
    def test_terminal_listing_binding_required(self):
        self.mutation(C.DART, "expect(terminal['listingKey'], listing)", 'expect(true, true)')
    def test_signed_native_receipt_required(self):
        self.mutation(C.DART, "expect(after['splitSha256'], [splitSha])", 'expect(true, true)')
    def test_explicit_approval_gate_required(self):
        self.mutation(C.SINGLE, 'self.taps == 1', 'True')
    def test_extract_zip_required(self):
        self.mutation(C.DART,'extractZipOffIsolate(','fakeExtractor(')
    def test_extract_tar_required(self):
        self.mutation(C.DART,'extractTarballOffIsolate(','fakeExtractor(')
    def test_archive_digest_required(self):
        self.mutation(C.DART,'sha256.convert(bytes).toString() != archiveSha','false')
    def test_single_session_control_body_must_have_explicit_length(self):
        self.mutation(C.DART, 'request.contentLength = payload.length;',
                      'request.contentLength = -1;')
    def test_single_session_control_body_must_send_verified_bytes(self):
        self.mutation(C.DART, 'request.add(payload);',
                      'request.write(jsonEncode(body));')
    def test_extracted_apk_digest_required(self):
        self.mutation(C.DART,'actual.toString() != expected','false')
    def test_resolver_required(self):
        self.mutation(C.DART,'resolveInstallBundlePlan(','fakePlanner(')
    def test_split_session_required(self):
        self.mutation(C.DART,'expect(plan.sessionPaths.length, 2)','expect(plan.sessionPaths.length, 1)')
    def test_no_missing_tar_case(self):
        self.mutation(C.FIX,"POSITIVE=('apks','apkm','xapk','zip','tar.gz')","POSITIVE=('apks','apkm','xapk','zip')")
    def test_preinstall_rejects_traversal(self):
        self.mutation(C.FIX,"members['../escape.apk']=base","pass # traversal removed")
    def test_preinstall_rejects_ambiguous(self):
        self.mutation(C.FIX,"members['payload/another-base.apk']=base","pass # ambiguity removed")
    def test_no_false_full_matrix(self):
        self.mutation(C.HOST,"'full_r02_matrix_qualified':False","'full_r02_matrix_qualified':True")
    def test_no_false_user_import(self):
        self.mutation(C.HOST,"'user_facing_import_qualified':False","'user_facing_import_qualified':True")
    def test_no_false_release(self):
        self.mutation(C.HOST,"'release_qualified':False","'release_qualified':True")
    def test_no_skip_actual_installed_bytes(self):
        self.mutation(C.SINGLE, 'self.base.installed_state(2, True, self.fixtures)', 'dict()')
    def test_no_skip_negative_proof(self):
        self.mutation(C.SINGLE, 'not self.called and self.taps == 0', 'True')
    def test_stale_r00_fixture_test(self):
        self.mutation(C.R00_TEST,"'obtainx-r02-rt02c.yml'","'obtainx-r02-old.yml'")
    def test_no_unbounded_pre_dart_retry(self):
        self.mutation(C.SINGLE, 'self.launches = 1',
                      'self.launches = 1\n        for attempt in (1, 2): break')
    def test_no_bypass_single_session_installer_proof(self):
        self.mutation(C.SINGLE, 'self.base.installed_state(2, True, self.fixtures)', 'dict()')
    def test_no_bypass_single_session_negative_baseline(self):
        self.mutation(C.SINGLE, 'self.H.baseline_v1(self.fixtures)', 'dict()')
    def test_no_session_handshake_bypass(self):
        self.mutation(C.DART, "await control('prepare', name)", "await fakePrepare(name)")
    def test_watchdog_must_be_invoked_by_real_runner(self):
        self.mutation(C.SINGLE, 'watchdog.tick(', 'watchdog.noop(')

    def test_watchdog_total_limit_cannot_be_raised_to_one_hour(self):
        self.mutation(C.WATCHDOG, 'TOTAL_SECONDS=1200', 'TOTAL_SECONDS=6000')

    def test_watchdog_pre_dart_deadline_cannot_be_removed(self):
        self.mutation(C.WATCHDOG, "'TEST_APK_INSTALL':360", "'TEST_APK_INSTALL':6000")

    def test_no_second_flutter_launch(self):
        self.mutation(C.SINGLE, 'self.launches = 1', 'self.launches = 2')
    def test_no_skip_live_signed_v1_staging(self):
        self.mutation(C.SINGLE,
                      "self.base.adb('install', '-t', str(self.fixtures / 'base_v1.apk')",
                      "self.base.adb('install', '-t', str(self.fixtures / 'fake_v1.apk')")
    def test_no_skip_dart_case_evidence(self):
        self.mutation(C.DART,'OX_R02C_DART_STAGE=PREINSTALL_REFUSED','SKIPPED_VALIDATION')

class ArchiveFixtures(unittest.TestCase):
    def setUp(self):
        self.base=b'disposable-ci-base-apk-bytes'*60
        self.split=b'disposable-ci-split-apk-bytes'*60
    def test_exact_seven_archive_cases(self):
        self.assertEqual(H.CASES,('apks','apkm','xapk','zip','tar.gz','traversal','ambiguous'))
        self.assertEqual(set(F.NAMES),{H.filename(x) for x in H.CASES})
    def test_all_positive_contain_same_signed_members(self):
        for kind in F.POSITIVE:
            entries=F.archive_entries(kind,self.base,self.split)
            self.assertEqual(entries['payload/base.apk'],self.base)
            self.assertEqual(entries['payload/config.x86_64.apk'],self.split)
    def test_all_zips_roundtrip(self):
        for kind in ('apks','apkm','xapk','zip'):
            raw=F.pack_zip(F.archive_entries(kind,self.base,self.split))
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                self.assertEqual(archive.read('payload/base.apk'),self.base)
                self.assertEqual(archive.read('payload/config.x86_64.apk'),self.split)
                self.assertEqual(len(archive.namelist()),len(set(archive.namelist())))
    def test_tar_roundtrip(self):
        raw=F.pack_tar(F.archive_entries('tar.gz',self.base,self.split))
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
            self.assertEqual(archive.extractfile('payload/base.apk').read(),self.base)
            self.assertEqual(archive.extractfile('payload/config.x86_64.apk').read(),self.split)
    def test_traversal_is_genuine(self):
        raw=F.pack_zip(F.archive_entries('traversal',self.base,self.split))
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            self.assertIn('../escape.apk',z.namelist())
    def test_ambiguous_base_is_genuine(self):
        raw=F.pack_zip(F.archive_entries('ambiguous',self.base,self.split))
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            self.assertEqual(z.read('payload/base.apk'),z.read('payload/another-base.apk'))
    def test_formats_have_unique_bytes(self):
        values=[]
        for case in H.CASES:
            entries=F.archive_entries(case,self.base,self.split)
            raw=F.pack_tar(entries) if case=='tar.gz' else F.pack_zip(entries)
            values.append(hashlib.sha256(raw).hexdigest())
        self.assertEqual(len(set(values)),7)
    def test_refuse_unsupported_format(self):
        with self.assertRaises(RuntimeError):F.archive_entries('jar',self.base,self.split)
        with self.assertRaises(H.Refused):H.filename('apk')

class PreDartRetry(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(prefix='ox-rt02c-retry-');self.out=Path(self.t.name)
        self.fixtures=self.out/'fixtures';self.fixtures.mkdir()
        self.case='apks';self.log=self.out/'rt02c-apks.private.log'
        self.log.write_text('Running Gradle task assembleNormalDebug')
        (self.out/'rt02c-progress.json').write_text(json.dumps({
            'case':self.case,'android_confirmations':0}))
    def tearDown(self):self.t.cleanup()
    def eligible(self,error='Flutter RT02C case failed apks phase=GRADLE_BUILD'):
        with patch.object(H,'baseline_v1',return_value={'installed_original_intact':True}):
            return H.eligible_pre_dart_retry(self.out,self.fixtures,self.case,H.Refused(error))
    def test_pre_dart_retry_can_recover_transient_flutter(self):
        self.assertTrue(self.eligible())
    def test_no_retry_after_stock_installer(self):
        self.log.write_text('OX_R02C_DART_STAGE=INSTALL_CALL')
        self.assertFalse(self.eligible())
    def test_no_retry_after_refusal(self):
        self.log.write_text('OX_R02C_DART_STAGE=PREINSTALL_REFUSED')
        self.assertFalse(self.eligible())
    def test_no_retry_after_ui_action(self):
        (self.out/'rt02c-progress.json').write_text(json.dumps({
            'case':self.case,'android_confirmations':1}))
        self.assertFalse(self.eligible())
    def test_no_retry_for_other_failure(self):
        self.assertFalse(self.eligible('Installed split mismatch'))
    def test_no_retry_if_v1_package_changed(self):
        with patch.object(H,'baseline_v1',side_effect=H.Refused('v1 changed')):
            with self.assertRaises(H.Refused):
                H.eligible_pre_dart_retry(self.out,self.fixtures,self.case,
                   H.Refused('Flutter RT02C case failed apks phase=GRADLE_BUILD'))

class FailureDiagnostics(unittest.TestCase):
    def test_native_state_bounded_to_current_case(self):
        old='OX_R02C_NATIVE_STATE=APPROVAL TERMINAL=SUCCESS\n'
        current='OX_R02C_DART_STAGE=SCENARIO_STARTED case=apkm\n'
        self.assertEqual(H.native_session_observation(old+current),
                         {'active':'NOT_OBSERVED','terminal':'NOT_OBSERVED'})
        marker='OX_R02C_NATIVE_STATE=COMMITTING TERMINAL=NO_MATCHING_TERMINAL\n'
        self.assertEqual(H.native_session_observation(current+marker),
                         {'active':'COMMITTING','terminal':'NO_MATCHING_TERMINAL'})
        for invalid in (marker+marker,marker.replace('COMMITTING','arbitrary/private/path'),
                        marker.replace('NO_MATCHING_TERMINAL','private-token')):
            self.assertEqual(H.native_session_observation(current+invalid),
                             {'active':'NOT_OBSERVED','terminal':'NOT_OBSERVED'})
    def test_installer_timeout_is_not_gradle_failure(self):
        log = ('Running Gradle task assembleNormalDebug\n'
               'OX_R02C_DART_STAGE=SCENARIO_STARTED case=apks\n'
               'OX_R02C_DART_STAGE=INSTALL_CALL\nTimeoutException: timed out')
        self.assertEqual(H.flutter_failure(log), 'INSTALLER_TIMEOUT_NO_APPROVAL')
        self.assertEqual(H.flutter_failure(log, phase='STOCK_INSTALLER_CALL', approvals=1),
                         'INSTALLER_TIMEOUT_AFTER_APPROVAL')

    def test_explicit_gradle_failure_requires_pre_dart_phase(self):
        log = 'Gradle task assembleNormalDebug failed with exit code 1'
        self.assertEqual(H.flutter_failure(log, phase='GRADLE_BUILD'), 'GRADLE_BUILD_FAILED')
        self.assertEqual(H.flutter_failure(log, phase='STOCK_INSTALLER_CALL'),
                         'INSTALLER_INCOMPLETE_NO_APPROVAL')
        self.assertEqual(H.flutter_failure('Running Gradle task assemble\nException: later',
                                          phase='GRADLE_BUILD'), 'UNKNOWN_PRECISE_FAILURE')

    def test_previous_case_timeout_cannot_contaminate_current_case(self):
        log = ('OX_R02C_DART_STAGE=SCENARIO_STARTED case=apks\nTimeoutException\n'
               'OX_R02C_DART_STAGE=SCENARIO_STARTED case=apkm\n'
               'OX_R02C_DART_STAGE=INSTALL_CALL\nSome tests failed')
        self.assertEqual(H.flutter_failure(log), 'INSTALLER_INCOMPLETE_NO_APPROVAL')

    def _probe(self, *, dump_rc=0, xml=b'', tap_rc=0, cleanup_rc=0):
        from types import SimpleNamespace
        calls=[]; observed=[]
        def command(args, **kwargs):
            op=args[4]; calls.append(tuple(args))
            return SimpleNamespace(returncode={'uiautomator':dump_rc,'cat':0,
                                   'rm':cleanup_rc,'input':tap_rc}[op],
                                   stdout=xml if op=='cat' else b'',stderr=b'')
        with patch.object(H.base,'command',side_effect=command):
            try:
                result=H.base._tap_confirmed_install_dialog(on_observation=observed.append)
            except H.base.Refused:
                result='REFUSED'
        return result,calls,observed

    def test_failed_dump_never_reads_stale_xml_or_taps(self):
        result,calls,observed=self._probe(dump_rc=1)
        self.assertFalse(result)
        self.assertEqual([c[4] for c in calls], ['uiautomator','rm'])
        self.assertEqual(calls[0][-1],calls[1][-1])
        self.assertEqual(observed,['DUMP_FAILED'])
        _,other,_=self._probe(dump_rc=1)
        self.assertNotEqual(calls[0][-1],other[0][-1])

    def _xml(self, count=1, fixture=True):
        label=H.base.NAME if fixture else 'Different package'
        node=('<node package="com.android.packageinstaller" enabled="true" '
              'text="Update" bounds="[0,0][20,20]"/>')
        return ('<?xml version="1.0"?><hierarchy><node package="com.android.packageinstaller" text="'+label+'"/>'
                +node*count+'</hierarchy>').encode()

    def test_fresh_unique_installer_tap(self):
        result,calls,observed=self._probe(xml=self._xml())
        self.assertIs(result,True)
        self.assertEqual([c[4] for c in calls],['uiautomator','cat','rm','input'])
        self.assertEqual(calls[0][-1],calls[1][-1]);self.assertEqual(calls[1][-1],calls[2][-1])
        self.assertEqual(observed,['CONFIRMATION_TAPPED'])

    def test_ambiguous_or_wrong_fixture_never_taps(self):
        for xml,category in ((self._xml(2),'ACTION_AMBIGUOUS'),
                             (self._xml(fixture=False),'FIXTURE_NOT_VISIBLE'),
                             (self._xml(0),'ACTION_NOT_VISIBLE'),
                             (b'not xml','XML_INVALID')):
            with self.subTest(category=category):
                result,calls,observed=self._probe(xml=xml)
                self.assertFalse(result);self.assertNotIn('input',[c[4] for c in calls])
                self.assertEqual(observed,[category])

    def test_uncertain_tap_fails_closed(self):
        result,calls,observed=self._probe(xml=self._xml(),tap_rc=1)
        self.assertEqual(result,'REFUSED')
        self.assertEqual([c[4] for c in calls].count('input'),1)
        self.assertEqual(observed,['TAP_FAILED'])

    def test_cleanup_failure_prevents_tap(self):
        result,calls,observed=self._probe(xml=self._xml(),cleanup_rc=1)
        self.assertEqual(result,'REFUSED')
        self.assertNotIn('input',[c[4] for c in calls])
        self.assertEqual(observed,['CLEANUP_FAILED'])


    def test_fixture_identity_must_belong_to_installer_package(self):
        xml=self._xml().replace(b'package="com.android.packageinstaller"',
                                b'package="unrelated.app"',1)
        result,calls,observed=self._probe(xml=xml)
        self.assertFalse(result)
        self.assertNotIn('input',[c[4] for c in calls])
        self.assertEqual(observed,['FIXTURE_NOT_VISIBLE'])

    def test_action_must_belong_to_fixture_owner_ui(self):
        xml=self._xml().replace(b'package="com.android.packageinstaller" enabled=',
                                b'package="com.google.android.packageinstaller" enabled=')
        result,calls,observed=self._probe(xml=xml)
        self.assertFalse(result)
        self.assertNotIn('input',[c[4] for c in calls])
        self.assertEqual(observed,['ACTION_NOT_VISIBLE'])


class ApprovalBoundaryConcurrency(unittest.TestCase):
    def setUp(self):
        from r02_rt02c_single_session import SingleSession
        self.tmp=tempfile.TemporaryDirectory(prefix='ox-rt02c-concurrency-')
        out=Path(self.tmp.name)
        self.session=SingleSession(out,out,{}, {}, out/'receipt.json',H,H.base)
        self.session.active='apks';self.session.called=True
        self.session.phase='STOCK_INSTALLER_CALL'

    def tearDown(self):self.tmp.cleanup()

    def test_slow_dump_does_not_block_finish_and_stale_tap_refused(self):
        entered=threading.Event();release=threading.Event();transition=threading.Event()
        taps=[];results=[];errors=[]
        def mock_probe(*, on_observation, authorize_tap):
            entered.set()
            if not release.wait(3):raise AssertionError('test probe not released')
            on_observation('ACTION_NOT_VISIBLE')
            return authorize_tap(lambda: taps.append('tap') or True)
        def run():
            try:results.append(self.session.probe_approval('apks',0))
            except BaseException as exc:errors.append(exc)
        def finish_boundary():
            with self.session.lock:
                self.session.active='apkm';self.session.next_index=1
                self.session.called=True;self.session.taps=0
                transition.set()
        with patch.object(H.base,'_tap_confirmed_install_dialog',side_effect=mock_probe):
            worker=threading.Thread(target=run);worker.start()
            other=None
            try:
                self.assertTrue(entered.wait(2),'probe never started')
                other=threading.Thread(target=finish_boundary);other.start()
                self.assertTrue(transition.wait(1),'read-only UI probe blocked controller transition')
            finally:
                release.set();worker.join(4)
                if other is not None:other.join(4)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors,[]);self.assertEqual(results,[False])
            self.assertEqual(taps,[])
            self.assertEqual(self.session.approval_probe_counts,{})

    def test_current_boundary_tap_once(self):
        taps=[]
        def probe(*, on_observation, authorize_tap):
            def tap():
                taps.append(1);on_observation('CONFIRMATION_TAPPED');return True
            self.assertTrue(authorize_tap(tap))
            self.assertFalse(authorize_tap(tap))
            return True
        with patch.object(H.base,'_tap_confirmed_install_dialog',side_effect=probe) as helper:
            self.assertTrue(self.session.probe_approval('apks',0))
            self.assertFalse(self.session.probe_approval('apks',0))
            self.assertEqual(helper.call_count,1)
        self.assertEqual(taps,[1]);self.assertEqual(self.session.taps,1)
        self.assertEqual(self.session.approval_probe_counts,{'CONFIRMATION_TAPPED':1})

    def test_failed_boundary_not_probed(self):
        self.session.failure='Refused'
        with patch.object(H.base,'_tap_confirmed_install_dialog') as helper:
            self.assertFalse(self.session.probe_approval('apks',0))
            helper.assert_not_called()


class OwnedSessionBoundary(unittest.TestCase):
    def setUp(self):
        from r02_rt02c_single_session import SingleSession
        self.tmp=tempfile.TemporaryDirectory(prefix='ox-rt02c-owner-')
        self.out=Path(self.tmp.name)
        inv={'files':{H.filename(case):{'sha256':hashlib.sha256(case.encode()).hexdigest()}
                      for case in H.CASES}}
        self.s=SingleSession(self.out,self.out,inv,{'cases':[]},self.out/'receipt.json',H,H.base)
        self.s.active='apks';self.s.called=True;self.s.taps=1
        self.s.flutter_log.write_text('private source fixture')
    def tearDown(self):self.tmp.cleanup()
    def finish(self,**fields):
        return self.s.transition('/rt02c/finish',{'case':self.s.active,'result':'installed',**fields})
    def test_host_refuses_missing_or_invalid_owned_identity_before_adb(self):
        with patch.object(H.base,'installed_state') as proof:
            for fields in ({},{'owned_session_id':True},{'owned_session_id':0},
                           {'owned_session_id':2**31},{'owned_session_id':'1'}):
                with self.subTest(fields=fields),self.assertRaises(H.Refused):self.finish(**fields)
            proof.assert_not_called();self.assertEqual(self.s.receipt['cases'],[])
    def test_host_refuses_zero_approval_or_reused_session(self):
        with patch.object(H.base,'installed_state') as proof:
            self.s.taps=0
            with self.assertRaises(H.Refused):self.finish(owned_session_id=18)
            self.s.taps=1;self.s.receipt['cases']=[{'owned_session_id':18}]
            with self.assertRaises(H.Refused):self.finish(owned_session_id=18)
            proof.assert_not_called()
    def test_positive_ack_requires_independent_android_state(self):
        with patch.object(H.base,'installed_state',side_effect=H.Refused('APK mismatch')):
            with self.assertRaises(H.Refused):self.finish(owned_session_id=18)
        self.assertEqual(self.s.receipt['cases'],[]);self.assertEqual(self.s.next_index,0)
        expected={'version_code':2,'installed_path_count':2,'config_x86_64_present':True}
        with patch.object(H.base,'installed_state',return_value=expected) as proof:
            self.assertEqual(self.finish(owned_session_id=18),{'verified':True,'next_index':1})
            proof.assert_called_once_with(2,True,self.out)
        self.assertEqual(self.s.receipt['cases'][0]['owned_session_id'],18)
        self.assertEqual(self.s.receipt['cases'][0]['android_confirmations'],1)
    def test_negative_cannot_submit_session_identity(self):
        self.s.active='traversal';self.s.next_index=5;self.s.called=False;self.s.taps=0
        with patch.object(H,'baseline_v1') as proof:
            with self.assertRaises(H.Refused):self.s.transition('/rt02c/finish',{
                'case':'traversal','result':'refused','owned_session_id':18})
            proof.assert_not_called()

class RuntimeReceipts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='ox-rt02c-receipt-');self.out=Path(self.tmp.name)
        self.commit='a'*40;self.run='123456'
        cases=[]
        for index,case in enumerate(H.CASES):
            digest=hashlib.sha256(case.encode()).hexdigest()
            if case in F.POSITIVE:
                cases.append({'case':case,'archive_sha256':digest,'flutter_log_sha256':digest,
                  'installed_signed_members_verified':True,'version_code':2,'installed_path_count':2,
                  'config_x86_64_present':True,'android_confirmations':1,'owned_session_id':index+100})
            else:
                cases.append({'case':case,'archive_sha256':digest,'flutter_log_sha256':digest,
                  'preinstall_refused':True,'installed_original_intact':True,'version_code':1,
                  'installed_path_count':1,'android_confirmations':0})
        for index,item in enumerate(cases):
            item['process_launch']=1
            item['boundary_index']=index
        self.data={'schema':1,'status':'PASS_FIVE_ARCHIVES_TWO_PREINSTALL_REFUSALS',
                   'flutter_launches':1,'session_log_sha256':hashlib.sha256(b'session').hexdigest(),
                   'runner_probe_count':27,'runner_probe_skipped':180,
                   'source_sha':self.commit,'run_id':self.run,'hosted_emulator_only':True,
                   'physical_device_qualified':False,'full_r02_matrix_qualified':False,
                   'user_facing_import_qualified':False,'release_qualified':False,
                   'publication_allowed':False,'backend':'production StockInstaller',
                   'installer_route':'owned_foreground_session','cases':cases}
        self.write()
    def tearDown(self):self.tmp.cleanup()
    def write(self):(self.out/H.RECEIPT).write_text(json.dumps(self.data))
    def verify(self):
        with patch.object(H.base,'identity_check',return_value=(self.commit,self.run)):
            return H.verify(self.out)
    def test_valid_receipt(self):self.assertEqual(self.verify(),0)
    def test_opt06_missing_probe_count_refused(self):
        del self.data['runner_probe_count'];self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_opt06_missing_skipped_count_refused(self):
        del self.data['runner_probe_skipped'];self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_opt06_negative_probe_count_refused(self):
        self.data['runner_probe_count']=-1;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_opt06_boolean_probe_count_refused(self):
        self.data['runner_probe_count']=True;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_opt06_excessive_skipped_count_refused(self):
        self.data['runner_probe_skipped']=6001;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_opt06_float_skipped_count_refused(self):
        self.data['runner_probe_skipped']=0.0;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_legacy_route_receipt_refused(self):
        self.data.pop('installer_route');self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_zero_approval_positive_refused(self):
        self.data['cases'][0]['android_confirmations']=0;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_missing_or_duplicate_owned_session_refused(self):
        first=self.data['cases'][0]
        old=first.pop('owned_session_id');self.write()
        with self.assertRaises(H.Refused):self.verify()
        for value in (True,0,-1,2**31,self.data['cases'][1]['owned_session_id']):
            first['owned_session_id']=value;self.write()
            with self.assertRaises(H.Refused):self.verify()
        first['owned_session_id']=old;self.write();self.assertEqual(self.verify(),0)
    def test_negative_owned_session_refused(self):
        self.data['cases'][-1]['owned_session_id']=17;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_missing_single_process_proof(self):
        self.data['flutter_launches']=2;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_repeated_boundary_index(self):
        self.data['cases'][2]['boundary_index']=1;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_missing_case(self):
        self.data['cases'].pop();self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_reordered_case(self):
        self.data['cases'][0],self.data['cases'][1]=self.data['cases'][1],self.data['cases'][0];self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_mismatched_commit(self):
        self.data['source_sha']='b'*40;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_no_missing_split(self):
        self.data['cases'][0]['installed_path_count']=1;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_no_downgrade_positive(self):
        self.data['cases'][3]['version_code']=1;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_no_unverified_positive(self):
        self.data['cases'][0]['installed_signed_members_verified']=False;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_no_negative_wrong_version(self):
        self.data['cases'][-1]['version_code']=2;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_no_negative_unrecorded_refusal(self):
        self.data['cases'][-1]['preinstall_refused']=False;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_no_negative_installer_tap(self):
        self.data['cases'][-1]['android_confirmations']=1;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_no_false_user_import_admission(self):
        self.data['user_facing_import_qualified']=True;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_no_false_release_admission(self):
        self.data['release_qualified']=True;self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_no_reused_archive_digest(self):
        self.data['cases'][0]['archive_sha256']=self.data['cases'][1]['archive_sha256'];self.write()
        with self.assertRaises(H.Refused):self.verify()
    def test_no_missing_log_sha(self):
        self.data['cases'][0]['flutter_log_sha256']='wrong';self.write()
        with self.assertRaises(H.Refused):self.verify()

if __name__=='__main__':unittest.main()
