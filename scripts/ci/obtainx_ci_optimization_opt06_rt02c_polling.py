#!/usr/bin/env python3
"""OPT06: bounded RT02C app-presence probes while Flutter Gradle is compiling.

Pure scheduling only: does not skip a Dart case, installer request, Android
confirmation, package-state attestation or receipt verification. The live
host always probes immediately outside the GRADLE_BUILD phase. The host's
/prepare boundary still independently validates the installed runner.
"""
from __future__ import annotations
import math

GRADLE_PROBE_INTERVAL_SECONDS = 8.0


def should_probe_runner(now: float, last_probe: float | None, phase: str) -> bool:
    """Reduce only redundant Gradle-phase probes; never defer an install probe.

    Errors refuse instead of silently skipping a runner/package check. A
    normal phase transition out of GRADLE_BUILD restores full-frequency polls.
    """
    if type(now) not in (float, int) or not math.isfinite(now) or now < 0:
        raise ValueError('invalid monotonic timestamp')
    if type(phase) is not str or not phase:
        raise ValueError('missing Flutter runtime phase')
    if last_probe is None:
        return True
    if (type(last_probe) not in (float, int) or
            not math.isfinite(last_probe) or last_probe < 0 or now < last_probe):
        raise ValueError('invalid previous monotonic timestamp')
    return phase != 'GRADLE_BUILD' or now-last_probe >= GRADLE_PROBE_INTERVAL_SECONDS
