# ObtainX RT02C HF09 — atomic watchdog clock snapshot

## Observed failure
Hosted run [43336826213](https://github.com/Mikeyphw/ObtainX/actions/runs/43336826213)
reached `DART_TEST_STARTED` then refused with `watchdog monotonic clock invalid`.
The host sampled `time.monotonic()` before reading the thread-protected case
state. The control-server thread could set a later `case_started_at`, causing
an invalid negative elapsed duration even when the monotonic clock was valid.

## Fix
The host now samples monotonic time, active case and case-start elapsed as one
atomic observation inside the **existing** case-state lock. Its watchdog uses
only that consistent snapshot. Normal phase deadlines, real Android install
approval, seven archive scenarios, signature/bytes receipts, RT02F abandonment,
and R02G incompatible-SDK gates remain unchanged. No retries or fake PASS.

## Qualification boundaries
HF09 adds synthetic race and mutation tests and tightens the RT02C source
contract. Local Python tests are not Android qualification. All six hosted
check suites must pass at the final commit; the real RT02C/R02G device receipts
remain mandatory. No release, merge, local Gradle build or physical-device
qualification is claimed.
