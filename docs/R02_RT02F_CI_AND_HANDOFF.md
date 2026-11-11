# RT02F P01 — External installer evidence and targeted CI routing

**Stack parent:** PR #9, exact HEAD `112a09d4c1cc852717a9965e7e30cf2f85898546`.

## Source behavior

The third-party native handoff returns a boolean indicating a package-change
signal, not independently verified exact installed APK bytes or version. RT02F
keeps the result **handedOff** for both bridge outcomes and only allows the
existing package-state/broadcast reconciliation to produce a confirmed receipt.
A pending-operation indicator is not resurrected after a callback already
resolved its pending snapshot.

The stock installer still distinguishes Android cancellation, success,
not-installed/pending and error. No permission bypass, silent install claim,
release, private APK, or user data mutation is part of this overlay.

## AuroraStore-Standalone CI routing adaptation

AuroraStore-Standalone uses targeted PR checks and periodic or risk-triggered
full gates (five integrated master changes by default). ObtainX currently has
**stacked, unmerged PRs**, so first-parent master cadence cannot safely count
those as integrated changes. RT02F implements the immediately enforceable
subset: exact PR head/base scope classification, inexpensive source security
contracts on every PR, targeted Flutter analysis and tests for ordinary Dart
changes, and full Flutter + existing API36 runtime lanes for security, install,
Android build, integration harness, or workflow changes. Full gates remain
available for explicit workflow_dispatch when registered on default branch.
A skipped heavy workflow is **not full Android runtime qualification**. R00
source checks no longer duplicate a push on the same feature PR.

The full matrix still requires physical/device backend checks, real user
cancellation, API30+ OBB writes, Shizuku/Dhizuku and external installer result
verification. The inherited seven-case RT02C API36 suite remains the full
runtime baseline on high-risk commits, but these backend gaps remain open.

On successful scoped acceptance continue with RT02F remaining runtime matrix,
then **R03** for resumable downloads and durable queue persistence.
