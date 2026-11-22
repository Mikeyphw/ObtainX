"""Offline RT02F P02 host acceptance tests with fake Android boundary only.

These tests do NOT claim real emulator execution; the hosted CI runner does.
"""
from __future__ import annotations
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('r02f_p02_session_abandon',ROOT/'scripts/ci/r02f_p02_session_abandon.py')
assert SPEC and SPEC.loader
M=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)

class FakeAndroid:
    def __init__(self):
        self.paths={}
        self.commands=[]
        self.active=set()
        self.counter=110
        self.wrong_digest=False
        self.fail_abandon=False
        self.fail_create=False
        self.fail_write=False

    def adb(self,*args,**kwargs):
        self.commands.append(args)
        if args[:3]==('shell','cmd','package'):
            if args[3]=='install-create':
                if self.fail_create:raise M.base.Refused('command failed adb rc=1')
                self.counter+=1
                sid=str(self.counter)
                self.active.add(sid)
                return 'Success: created install session ['+sid+']'
            if args[3]=='install-write':
                if self.fail_write:raise M.base.Refused('command failed adb rc=1')
                if args[6] not in self.active:raise RuntimeError('bad session')
                return 'Success: streamed 300 bytes'
            if args[3]=='install-abandon':
                if self.fail_abandon:raise M.base.Refused('command failed adb rc=1')
                self.active.discard(args[4])
                return 'Success'
        if args[0]=='push':
            self.paths[args[2]]=Path(args[1]).read_bytes()
            return '300 bytes'
        if args[:2]==('shell','sha256sum'):
            path=args[2]
            digest=hashlib.sha256(self.paths[path]).hexdigest()
            return ('0'*64 if self.wrong_digest else digest)+'  '+path
        if args[:2]==('shell','rm'):
            self.paths.pop(args[3],None)
            return ''
        raise AssertionError('unexpected shell call '+repr(args))

class RT02FP02Runtime(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ox-p02-fake-')
        self.addCleanup(self.temp.cleanup)
        self.fixtures=Path(self.temp.name)
        for name in ('base_v1.apk','base_v2.apk','config.x86_64.apk'):
            (self.fixtures/name).write_bytes(b'SIGNED-DISPOSABLE-FIXTURE'*15)
        self.android=FakeAndroid()
        self.probes=[]
        self.baseline={'installed_original_intact':True,'version_code':1,'installed_path_count':1,
                       'base_sha256':'a'*64}
        self.p1=patch.object(M.base,'adb',self.android.adb)
        self.p2=patch.object(M.rt02c,'baseline_v1',self._baseline)
        self.p1.start(); self.p2.start()
        self.addCleanup(self.p1.stop);self.addCleanup(self.p2.stop)

    def _baseline(self,fixtures):
        self.probes.append(fixtures)
        return dict(self.baseline)

    def test_single_and_split_abandon_no_commit_or_leftovers(self):
        for kind,names in M.CASES:
            result=M.run_case(self.fixtures,kind,names,'123456')
            self.assertTrue(result['installer_session_abandoned'])
            self.assertTrue(result['original_installed_state_intact'])
            self.assertFalse(result['install_commit_called'])
            self.assertEqual(result['installer_confirmation_count'],0)
        self.assertEqual(self.android.active,set())
        self.assertEqual(self.android.paths,{})
        self.assertEqual(len(self.probes),4)
        self.assertEqual(len([v for v in self.android.commands if v[:4]==('shell','cmd','package','install-write')]),3)
        self.assertFalse(any('install-commit' in v for args in self.android.commands for v in args))

    def test_wrong_staged_digest_abandons_and_cleans(self):
        self.android.wrong_digest=True
        with self.assertRaises(M.base.Refused):
            M.run_case(self.fixtures,'standalone',M.CASES[0][1],'123456')
        self.assertEqual(self.android.active,set())
        self.assertEqual(self.android.paths,{})

    def test_abandon_failure_refuses_not_passes(self):
        self.android.fail_abandon=True
        with self.assertRaises(M.base.Refused):
            M.run_case(self.fixtures,'standalone',M.CASES[0][1],'123456')

    def test_create_failure_reveals_phase_without_retry(self):
        self.android.fail_create=True
        with self.assertRaisesRegex(M.base.Refused,'phase=CREATE_STANDALONE'):
            M.run_case(self.fixtures,'standalone',M.CASES[0][1],'123456')
        self.assertEqual(self.android.active,set())
        self.assertEqual(len([v for v in self.android.commands if
            v[:4]==('shell','cmd','package','install-create')]),1)

    def test_write_failure_abandons_and_reveals_phase(self):
        self.android.fail_write=True
        with self.assertRaisesRegex(M.base.Refused,'phase=WRITE_STANDALONE_base_v2.apk'):
            M.run_case(self.fixtures,'standalone',M.CASES[0][1],'123456')
        self.assertEqual(self.android.active,set())
        self.assertEqual(self.android.paths,{})

    def _fake_run_host(self, *, stale=False, stage_failure=False, cleanup_failure=False, case_failure=False, install_stdout='Performing Streamed Install\nSuccess', pretend_install=False):
        inv={'schema':1,'source_sha':'a'*40,'fixture_package':M.base.FIXTURE,
             'signed_with_ephemeral_ci_key':True,'never_released':True,
             'files':{'base_v1.apk':{'sha256':M.sha(self.fixtures/'base_v1.apk'),
                                    'size':(self.fixtures/'base_v1.apk').stat().st_size,
                                    'version_code':1}}}
        import json
        (self.fixtures/'fixtures').mkdir(exist_ok=True)
        (self.fixtures/'fixtures'/'base_v1.apk').write_bytes((self.fixtures/'base_v1.apk').read_bytes())
        (self.fixtures/'fixtures'/'fixture_inventory.json').write_text(json.dumps(inv))
        calls=[]
        state={'installed':stale}
        def absent():
            calls.append('CHECK_ABSENT')
            if state['installed']:raise M.base.Refused('package unexpectedly present')
            return True
        def stage(phase,*args,**kwargs):
            calls.append(phase)
            if phase=='STAGE_FRESH_V1_BASELINE':
                if stage_failure:raise M.base.Refused('adb install error')
                if not pretend_install:state['installed']=True
                return install_stdout
            if phase=='CLEANUP_FRESH_V1_BASELINE':
                if cleanup_failure:raise M.base.Refused('adb uninstall error')
                state['installed']=False
                return 'Success'
            raise AssertionError('unexpected ADB phase '+phase)
        def case(*args):
            calls.append('ABANDON_CASE')
            if case_failure:raise M.base.Refused('abandon refused')
            return {'scenario':args[1],'original_version_code':1}
        saved=[]
        def receipt(path,body):saved.append(body)
        from contextlib import ExitStack
        # Fake Android proof is deliberately stricter than an ADB return code:
        # an installation that did not happen must never pass the acceptance test.
        def installed_state(fixtures):
            if not state['installed']:
                raise M.base.Refused('installed v1 baseline absent after ADB returned 0')
            return self._baseline(fixtures)
        with ExitStack() as stack:
            stack.enter_context(patch.object(M.rt02c,'baseline_v1',side_effect=installed_state))
            stack.enter_context(patch.object(M.base,'host_check',return_value=('a'*40,'1234')))
            stack.enter_context(patch.object(M.base,'empty_or_expected_package',side_effect=absent))
            stack.enter_context(patch.object(M.rt02c,'verify',return_value=0))
            stack.enter_context(patch.object(M,'artifact_inventory',return_value=inv))
            stack.enter_context(patch.object(M,'adb_phase',side_effect=stage))
            stack.enter_context(patch.object(M,'run_case',side_effect=case))
            stack.enter_context(patch.object(M,'write_receipt',side_effect=receipt))
            M.run(self.fixtures)
        return calls,saved,state

    def test_restage_exact_v1_after_rt02c_cleanup(self):
        calls,saved,state=self._fake_run_host()
        self.assertEqual(calls.count('STAGE_FRESH_V1_BASELINE'),1)
        self.assertEqual(calls.count('CLEANUP_FRESH_V1_BASELINE'),1)
        self.assertEqual(calls.count('ABANDON_CASE'),2)
        self.assertFalse(state['installed'])
        self.assertEqual(saved[-1]['status'],'PASS_TWO_ABANDONED_ANDROID_SESSIONS')

    def test_rc0_empty_stdout_still_checks_exact_installed_state(self):
        calls,saved,state=self._fake_run_host(install_stdout='')
        self.assertIn('STAGE_FRESH_V1_BASELINE',calls)
        self.assertFalse(state['installed'])
        self.assertEqual(saved[-1]['status'],'PASS_TWO_ABANDONED_ANDROID_SESSIONS')

    def test_rc0_nonstandard_stdout_still_checks_real_state(self):
        calls,saved,state=self._fake_run_host(install_stdout='Performing Streamed Install')
        self.assertEqual(calls.count('ABANDON_CASE'),2)
        self.assertFalse(state['installed'])

    def test_rc0_without_installed_package_never_passes(self):
        with self.assertRaises(M.base.Refused):
            self._fake_run_host(install_stdout='Success',pretend_install=True)

    def test_stale_fixture_refused_before_restage(self):
        with self.assertRaises(M.base.Refused):self._fake_run_host(stale=True)

    def test_failed_stage_cleans_and_refuses(self):
        with self.assertRaises(M.base.Refused):self._fake_run_host(stage_failure=True)

    def test_failed_abandon_cleans_and_refuses(self):
        with self.assertRaises(M.base.Refused):self._fake_run_host(case_failure=True)

    def test_unproven_cleanup_refuses(self):
        with self.assertRaises(M.base.Refused):self._fake_run_host(cleanup_failure=True)

    def test_reject_session_id_injection(self):
        self.assertEqual(M.parse_session_id('Success: created install session [18]'),'18')
        for value in ('Success: created install session [-1]',
                      'Success: created install session [1] junk',
                      'Failure [1]'):
            with self.assertRaises(M.base.Refused):
                M.parse_session_id(value)

if __name__=='__main__':unittest.main()
