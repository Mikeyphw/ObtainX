"""RT02C HF08: fail-closed, phase-aware watchdog for one real Flutter session.

This only bounds waiting. It never retries the Flutter process, fakes install
proof, acknowledges dialogs or changes signed Android fixture state.
"""
from __future__ import annotations
import math

TOTAL_SECONDS=1200  # 20 minutes including Gradle and all seven actual cases.
BOOTSTRAP_LIMITS={
    'FLUTTER_STARTING':240,
    'GRADLE_BUILD':720,
    'TEST_APK_INSTALL':360,
    'DART_TEST_STARTED':240,
    'STOCK_INSTALLER_CALL':240,
    'STOCK_INSTALLER_RETURNED':240,
    'PREINSTALL_REFUSED':240,
    'ANDROID_V1_BASELINE_VERIFIED':240,
    'ANDROID_V2_SPLIT_VERIFIED':240,
}
ACTIVE_CASE_SECONDS=420


class RT02CWatchdog:
    """Advance only on a *real phase or completed-boundary transition*.

    Log spooling/periodic `OX_R02_RT02C_PROGRESS` prints are not progress.
    All input times are provided by time.monotonic(), making it deterministic
    under offline synthetic fault injection without sleeping or device access.
    """
    def __init__(self, start:float):
        self._time(start)
        self.start=start
        self.last_time=start
        self.phase=None
        self.phase_start=start
        self.last_completed=0

    @staticmethod
    def _time(value):
        if type(value) not in (int,float) or not math.isfinite(value) or value<0:
            raise ValueError('watchdog monotonic clock invalid')

    def tick(self, *, now:float, observed_phase:str, completed_cases:int,
             active:bool, case_elapsed:float|None)->str|None:
        self._time(now)
        if now<self.last_time or now<self.start:
            raise ValueError('watchdog clock went backwards')
        self.last_time=now
        if (observed_phase not in BOOTSTRAP_LIMITS or
            type(completed_cases) is not int or not 0<=completed_cases<=7 or
            type(active) is not bool):
            raise ValueError('watchdog boundary state invalid')
        if active:
            self._time(case_elapsed)
        elif case_elapsed is not None:
            raise ValueError('watchdog inactive case cannot have elapsed time')
        if (observed_phase!=self.phase or completed_cases!=self.last_completed):
            self.phase=observed_phase
            self.phase_start=now
            self.last_completed=completed_cases
        total=now-self.start
        if total>=TOTAL_SECONDS:
            return 'TOTAL_SESSION_DEADLINE'
        if active:
            if case_elapsed>=ACTIVE_CASE_SECONDS:
                return 'ACTIVE_CASE_DEADLINE'
        elif now-self.phase_start>=BOOTSTRAP_LIMITS[observed_phase]:
            return ('PRE_DART_APK_INSTALL_STALL' if observed_phase=='TEST_APK_INSTALL'
                    else 'PRE_DART_'+observed_phase+'_STALL')
        return None
