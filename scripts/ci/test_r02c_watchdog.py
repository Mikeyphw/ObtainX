"""Synthetic RT02C phase-stall regressions; no Android/device claims."""
from __future__ import annotations
from pathlib import Path
import math
import unittest

from r02c_watchdog import (RT02CWatchdog,TOTAL_SECONDS,BOOTSTRAP_LIMITS,
                           ACTIVE_CASE_SECONDS)


class PhaseAwareWatchdogTests(unittest.TestCase):
    def test_healthy_all_seven_cases_unaffected(self):
        w=RT02CWatchdog(1.)
        self.assertIsNone(w.tick(now=2.,observed_phase='FLUTTER_STARTING',completed_cases=0,active=False,case_elapsed=None))
        self.assertIsNone(w.tick(now=90.,observed_phase='GRADLE_BUILD',completed_cases=0,active=False,case_elapsed=None))
        self.assertIsNone(w.tick(now=190.,observed_phase='TEST_APK_INSTALL',completed_cases=0,active=False,case_elapsed=None))
        for n in range(7):
            at=200.+30*n
            self.assertIsNone(w.tick(now=at,observed_phase='DART_TEST_STARTED',completed_cases=n,active=True,case_elapsed=0.))
            self.assertIsNone(w.tick(now=at+20,observed_phase='ANDROID_V2_SPLIT_VERIFIED',completed_cases=n+1,active=False,case_elapsed=None))

    def test_first_apks_install_stall_refused(self):
        w=RT02CWatchdog(0.)
        w.tick(now=0.,observed_phase='GRADLE_BUILD',completed_cases=0,active=False,case_elapsed=None)
        w.tick(now=200.,observed_phase='TEST_APK_INSTALL',completed_cases=0,active=False,case_elapsed=None)
        for t in (225.,250.,300.,550.):
            self.assertIsNone(w.tick(now=t,observed_phase='TEST_APK_INSTALL',completed_cases=0,active=False,case_elapsed=None))
        self.assertEqual(w.tick(now=560.,observed_phase='TEST_APK_INSTALL',completed_cases=0,active=False,case_elapsed=None),'PRE_DART_APK_INSTALL_STALL')

    def test_gradle_timeout_preserves_slow_compilation(self):
        w=RT02CWatchdog(0.)
        w.tick(now=5.,observed_phase='GRADLE_BUILD',completed_cases=0,active=False,case_elapsed=None)
        self.assertIsNone(w.tick(now=724.9,observed_phase='GRADLE_BUILD',completed_cases=0,active=False,case_elapsed=None))
        self.assertEqual(w.tick(now=725.,observed_phase='GRADLE_BUILD',completed_cases=0,active=False,case_elapsed=None),'PRE_DART_GRADLE_BUILD_STALL')

    def test_real_phase_change_resets_only_phase_clock(self):
        w=RT02CWatchdog(0.)
        w.tick(now=0.,observed_phase='TEST_APK_INSTALL',completed_cases=0,active=False,case_elapsed=None)
        self.assertIsNone(w.tick(now=300.,observed_phase='DART_TEST_STARTED',completed_cases=0,active=False,case_elapsed=None))
        self.assertIsNone(w.tick(now=400.,observed_phase='DART_TEST_STARTED',completed_cases=0,active=False,case_elapsed=None))
        self.assertEqual(w.tick(now=540.,observed_phase='DART_TEST_STARTED',completed_cases=0,active=False,case_elapsed=None),'PRE_DART_DART_TEST_STARTED_STALL')

    def test_active_installer_case_timeout(self):
        w=RT02CWatchdog(0.)
        w.tick(now=1.,observed_phase='DART_TEST_STARTED',completed_cases=2,active=True,case_elapsed=0.)
        self.assertIsNone(w.tick(now=420.,observed_phase='STOCK_INSTALLER_CALL',completed_cases=2,active=True,case_elapsed=419.))
        self.assertEqual(w.tick(now=421.,observed_phase='STOCK_INSTALLER_CALL',completed_cases=2,active=True,case_elapsed=420.),'ACTIVE_CASE_DEADLINE')

    def test_total_cap_cannot_be_evaded_by_log_phase_churn(self):
        w=RT02CWatchdog(0.)
        for t in range(0,TOTAL_SECONDS,10):
            self.assertIsNone(w.tick(now=float(t),observed_phase='GRADLE_BUILD' if t%20 else 'FLUTTER_STARTING',completed_cases=0,active=False,case_elapsed=None))
        self.assertEqual(w.tick(now=float(TOTAL_SECONDS),observed_phase='TEST_APK_INSTALL',completed_cases=0,active=False,case_elapsed=None),'TOTAL_SESSION_DEADLINE')

    def test_phase_progress_is_not_periodic_log_messages(self):
        w=RT02CWatchdog(0.)
        w.tick(now=5.,observed_phase='TEST_APK_INSTALL',completed_cases=0,active=False,case_elapsed=None)
        for sec in range(30,360,25):
            self.assertIsNone(w.tick(now=float(sec),observed_phase='TEST_APK_INSTALL',completed_cases=0,active=False,case_elapsed=None))
        self.assertEqual(w.tick(now=365.,observed_phase='TEST_APK_INSTALL',completed_cases=0,active=False,case_elapsed=None),'PRE_DART_APK_INSTALL_STALL')

    def test_invalid_clock_and_state_refused(self):
        w=RT02CWatchdog(10.)
        for kwargs in [dict(now=9.,observed_phase='GRADLE_BUILD',completed_cases=0,active=False,case_elapsed=None),
                       dict(now=float('nan'),observed_phase='GRADLE_BUILD',completed_cases=0,active=False,case_elapsed=None),
                       dict(now=11.,observed_phase='UNKNOWN',completed_cases=0,active=False,case_elapsed=None),
                       dict(now=11.,observed_phase='GRADLE_BUILD',completed_cases=True,active=False,case_elapsed=None),
                       dict(now=11.,observed_phase='GRADLE_BUILD',completed_cases=8,active=False,case_elapsed=None),
                       dict(now=11.,observed_phase='GRADLE_BUILD',completed_cases=0,active=True,case_elapsed=None),
                       dict(now=11.,observed_phase='GRADLE_BUILD',completed_cases=0,active=False,case_elapsed=10.)]:
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                RT02CWatchdog(10.).tick(**kwargs)

    def test_runner_contains_real_time_check_not_noop(self):
        runner=Path(__file__).with_name('r02_rt02c_single_session.py')
        if not runner.exists():self.skipTest('applied source needed')
        s=runner.read_text()
        for required in ('watchdog.tick(',"'OX_RT02C_WATCHDOG_REFUSED '",
                         'RT02CWatchdog(started)', 'self.H.progress(',
                         'self.base.installed_state(2, True, self.fixtures)',
                         'self.next_index += 1'):
            self.assertIn(required,s)
        self.assertNotIn('started + 6000',s)

if __name__=='__main__':unittest.main()
