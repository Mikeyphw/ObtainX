# OPT03 — exact-source normal-debug APK reuse

Scope: CI optimization only, source pinned to the PR #11 branch. The full Flutter
qualification remains mandatory; API36 runtime tests remain mandatory. No production
APK, release APK, signing keys, installer code, or physical-device state is modified.

The Flutter producer saves the exact normal-debug APK under a GitHub Actions
cache key containing the event checkout SHA and the pinned JDK21/Flutter3.47.6
profile. The consumer only restores that exact key and checks its manifest hash,
source identity, ZIP CRC, package identity, debug marker and signature.

When the cache misses, the bootstrap workflow compiles its own APK before
emulator startup. An invalid cache hit fails instead of being silently ignored.
All installed APK byte proofs and Android receipt publication remain unchanged.

The workflows are concurrent; first full CI pass may see cold misses in every
job. Benchmark same-SHA reruns to measure actual savings. No intermediate cache
output grants a release or physical Android qualification.
