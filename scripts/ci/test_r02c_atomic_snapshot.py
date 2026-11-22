"""RT02C HF09: assert host/control case clock is atomically observed.

Source-only tests do NOT qualify real Android sessions.
"""
from __future__ import annotations
import pathlib
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

import r02_rt02c_single_session as single
import r02_rt02c_contract as contract
from r02c_watchdog import RT02CWatchdog


class AtomicClockSnapshotTests(unittest.TestCase):
    def session(self):
        s=single.SingleSession.__new__(single.SingleSession)
        s.lock=threading.RLock()
        s.active='apks'
        s.phase='DART_TEST_STARTED'
        s.called=False
        s.taps=0
        s.call_at=None
        s.next_index=0
        s.failure=None
        s.case_started_at=1001.
        return s

    def test_real_race_sequence_cannot_use_stale_host_clock(self):
        s=self.session()
        # Previous implementation sampled 1000 just BEFORE the control
        # thread set case_started_at=1001, then subtracted: -1s => refused.
        self.assertLess(1000.-s.case_started_at,0.)
        with patch.object(single.time,'monotonic',return_value=1001.2):
            snapshot=s.snapshot()
        now,active,phase,called,taps,call_at,idx,failure,elapsed=snapshot
        self.assertEqual((active,phase,idx),('apks','DART_TEST_STARTED',0))
        self.assertAlmostEqual(elapsed,0.2)
        w=RT02CWatchdog(990.)
        self.assertIsNone(w.tick(now=now,observed_phase=phase,
            completed_cases=idx,active=True,case_elapsed=elapsed))

    def test_clock_sample_occurs_inside_existing_thread_lock(self):
        s=self.session()
        original=s.lock
        class RecordingLock:
            held=False
            def __enter__(self):
                self.held=True
                return self
            def __exit__(self,*_):
                self.held=False
        s.lock=RecordingLock()
        def sampled_time():
            self.assertTrue(s.lock.held,'monotonic clock read outside case-state lock')
            return 1001.5
        with patch.object(single.time,'monotonic',side_effect=sampled_time):
            self.assertEqual(s.snapshot()[-1],0.5)
        self.assertFalse(s.lock.held)
        s.lock=original

    def test_idle_state_has_no_fake_active_elapsed(self):
        s=self.session()
        s.active=None
        with patch.object(single.time,'monotonic',return_value=1015.):
            snapshot=s.snapshot()
        self.assertIsNone(snapshot[-1])
        self.assertEqual(snapshot[1],None)
        self.assertEqual(snapshot[0],1015.)

    def test_next_scenario_remains_fresh_clock_bound(self):
        s=self.session()
        w=RT02CWatchdog(990.)
        with patch.object(single.time,'monotonic',return_value=1002.):
            first=s.snapshot()
        self.assertIsNone(w.tick(now=first[0],observed_phase=first[2],
            completed_cases=first[6],active=True,case_elapsed=first[-1]))
        with s.lock:
            s.active=None;s.next_index=1;s.phase='ANDROID_V2_SPLIT_VERIFIED'
        with patch.object(single.time,'monotonic',return_value=1003.):
            finished=s.snapshot()
        self.assertIsNone(w.tick(now=finished[0],observed_phase=finished[2],
            completed_cases=finished[6],active=False,case_elapsed=finished[-1]))
        with s.lock:
            s.active='apkm';s.next_index=1;s.phase='DART_TEST_STARTED';s.case_started_at=1004.
        with patch.object(single.time,'monotonic',return_value=1004.3):
            next_case=s.snapshot()
        self.assertIsNone(w.tick(now=next_case[0],observed_phase=next_case[2],
            completed_cases=next_case[6],active=True,case_elapsed=next_case[-1]))

    def test_old_unlocked_clock_path_is_rejected_by_source_contract(self):
        with tempfile.TemporaryDirectory(prefix='ox-hf09-source-') as td:
            root=pathlib.Path(td)
            for name in contract.PATHS:
                src=contract.ROOT/name
                dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(src,dest)
            self.assertEqual(contract.inspect(root),[])
            path=root/contract.SINGLE
            source=path.read_text()
            self.assertIn('case_elapsed=case_elapsed)',source)
            path.write_text(source.replace('case_elapsed=case_elapsed)',
                'case_elapsed=(now-self.case_started_at if active else None))',1))
            self.assertNotEqual(contract.inspect(root),[])

    def test_clock_sample_outside_lock_refused_by_source_contract(self):
        with tempfile.TemporaryDirectory(prefix='ox-hf09-mut-') as td:
            root=pathlib.Path(td)
            for name in contract.PATHS:
                src=contract.ROOT/name
                dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(src,dest)
            path=root/contract.SINGLE
            source=path.read_text()
            self.assertIn('            now = time.monotonic()\n',source)
            path.write_text(source.replace('            now = time.monotonic()\n',
                '            now = float(0)\n',1))
            self.assertNotEqual(contract.inspect(root),[])

if __name__=='__main__':unittest.main()
