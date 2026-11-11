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

    def adb(self,*args,**kwargs):
        self.commands.append(args)
        if args[:2]==('shell','pm'):
            if args[2]=='install-create':
                self.counter+=1
                sid=str(self.counter)
                self.active.add(sid)
                return 'Success: created install session ['+sid+']'
            if args[2]=='install-write':
                if args[5] not in self.active:raise RuntimeError('bad session')
                return 'Success: streamed 300 bytes'
            if args[2]=='install-abandon':
                if self.fail_abandon:raise RuntimeError('abandon failed')
                self.active.discard(args[3])
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
        for name in ('base_v2.apk','config.x86_64.apk'):
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
        self.assertEqual(len([v for v in self.android.commands if v[:3]==('shell','pm','install-write')]),3)
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

    def test_reject_session_id_injection(self):
        self.assertEqual(M.parse_session_id('Success: created install session [18]'),'18')
        for value in ('Success: created install session [-1]',
                      'Success: created install session [1] junk',
                      'Failure [1]'):
            with self.assertRaises(M.base.Refused):
                M.parse_session_id(value)

if __name__=='__main__':unittest.main()
