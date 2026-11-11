# ObtainX RT02F CI OPT01 — Fast iteration / fail-closed qualification

This is **CI infrastructure optimization only**. It does not repair the pending P02 Android session failure or claim any new Android, backend, OBB, hardware or release qualification. The 11-PR stack remains unmerged.

## Motivation / measured baseline (PR #11, HEAD c679fd5d)

- Source-contract job: 9 seconds.
- Full Flutter + debug APK: about 9 minutes.
- Four API36 jobs: ~18–22 minutes total each, mostly parallel.
- Artifact uploads failed after 534, 632, 630 and 632 seconds. They contributed almost 40 minutes of *runner time* for the four workflows and ~9–10 minutes of wall-clock latency to the longest jobs.
- The first RT02F P02 runtime acceptance still failed. No CI optimization can turn that into a pass.

## Two explicit modes

**Development-only**, PR label `ci:development-only`:

- Source and security/mutation tests continue to execute on each code push.
- High-cost full Flutter and four Android emulator jobs defer; no emulator session is run for that push.
- **The existing source-contracts job ends with a deliberately FAILED development-only qualification guard on the SAME runner.** A skipped Android workflow is NEVER qualification or acceptance evidence. Do not merge or release from this state.
- `labeled` / `unlabeled` events are added to every involved workflow so label changes reevaluate gates.
- No second runner is allocated merely to report development-only refusal; this avoids a stuck `development-only-not-qualified` job.
- Use this only during iterative work, never when asserting a milestone complete.

**Qualification**, remove `ci:development-only`:

- The change triggers the complete mandatory Flutter and Android workflows using the existing high-risk path filters. All must pass for the exact current PR HEAD, with independent Android receipt validation and artifact publication. No stale run or cross-SHA receipt qualifies.
- `workflow_dispatch` always runs full gates, even if a PR carries the development-only label.
- A source-only green check does not upgrade a skipped Android workflow to qualified.

## Bounded evidence and diagnosis

- Each of the four pinned `actions/upload-artifact` steps now has a **three-minute step timeout** (rather than repeated ~9–10 minute hangs).
- Artifact uploads remain **mandatory** and failures still fail the job; this is not `continue-on-error` and does not replace a receipt with a job summary.
- Before each upload, a small always-on job-summary step prints safe hashes/sizes of small JSON receipts only, never APKs, full logs, signing keys, or user files. Summary helps identify source-bound evidence when upload stalls. A hash in the summary is not a standalone qualification receipt.
- Preserve the exact pinned emulator, Java, Flutter, SDK and security checks; no installer or APK bytes are modified by OPT01.

## Usage after source-pinned OPT01 launcher applies on PR #11

Create the label if it does not already exist (via GitHub UI or `gh label create`), then enable development mode **before your next iterative push**:

```sh
gh pr edit 11 -R Mikeyphw/ObtainX --add-label ci:development-only
```

For a final qualification run, remove the label; no source changes are required:

```sh
gh pr edit 11 -R Mikeyphw/ObtainX --remove-label ci:development-only
```

The label removal itself triggers new full workflows. Check exact SHA and all required CI lanes; absence of a workflow or missing evidence remains unqualified. Do not count a fast development run as qualification.

## OPT02 — Gradle dependency cache parity

- The three API36 jobs that previously lacked Gradle caching (bootstrap, RT02 and RT02B) now reuse the **same source-pinned Java 21 setup-java Gradle dependency cache** already present in RT02C.
- Cache keys are built from the Gradle wrapper and Android Gradle build configuration. Only dependency artifacts are cached, **not** signed test fixtures, runtime Android state, or acceptance receipts.
- This does **not** remove separate emulator launches, signature/rollback tests, KVM checks, independent source-bound receipts or mandatory artifact uploads.
- The cache change is a potential optimization for warm qualification runs, **not a measured speedup**. Compare hosted before/after steps and failed cache restores; keep qualification fail-closed.
- The `ci:development-only` label still skips all four Android lanes. Caches can only be evaluated during an authorized qualification run.

## Performance claims

The runtime savings from development-only runs are structural (heavy jobs are omitted) and can be verified by job lists. No warm-cache speedup is claimed. Three-minute artifact timeouts cap the upload step cost but do not cure upload service failures. Compare cold/warm builds, caches and actual CI results before claiming additional gains.
