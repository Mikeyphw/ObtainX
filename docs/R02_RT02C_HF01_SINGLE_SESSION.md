# RT02C HF01 — Single-session archive acceptance

This change is stacked on ObtainX PR #6 at `4ffa6203e15973b3c2efe9bf4afc1af3997814af`. It does not replace the original successful run `42955440742` or alter PR #6.

## Scope

- Exactly one `flutter test` invocation in the Android emulator acceptance job.
- Seven strictly ordered archive scenarios: APKS, APKM, XAPK, ZIP, TAR.GZ, traversal refusal and ambiguous-base refusal.
- Every scenario starts from a freshly installed, independently SHA-256-verified signed v1 fixture.
- Each positive scenario uses the real production `StockInstaller`; the Python host independently checks the installed v2 version and both exact signed APK members before allowing the Dart test to advance.
- Each negative scenario must reject before any authorized installer request; the host independently checks that signed v1 remains installed with no splits and no UI confirmation.
- Thread-safe, randomized-token-authenticated localhost control protocol over the existing ADB reverse connection. Requests are sequenced and failures stop the entire test; no scenario can be skipped, reordered or replayed.
- All fixture archives are pre-built and source-hashed once. Host hashes the private Flutter log without publishing it. Only minimized receipts/progress are uploadable.
- Installer UI inspection begins only after a real positive-case installer call. No blind taps.
- Separate per-case receipt fields include archive hash, boundary index, Flutter process launch index, installed state and log hash. Terminal verification requires a single launch and seven valid ordered boundaries.

## Remaining qualifications

This optimization is not proven until the new exact-commit hosted API36 workflow passes. Timing improvements must be measured from hosted CI, not assumed. Original PR #6 is still the baseline. This is not complete end-user archive import, physical-device acceptance, full R02 coverage, OBB qualification, a release or a merge.
