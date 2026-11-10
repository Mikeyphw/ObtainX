# Development guide — ObtainX fork

- `origin`: the fork owner, e.g. `Mikeyphw/ObtainX`; `upstream`: `bikram-agarwal/ObtainX`.
- `main`: import/update baseline; feature work belongs on `feature/...` branches, reviewed through hosted CI.
- `docs/R00_BASELINE.json`: exact upstream/fork commit identity at bootstrap. It is a provenance receipt, not a promise that future upstream syncs are automatically safe.
- `docs/R00_TEST_AUDIT.md`: initial inventory and explicit known-unqualified areas.
- `scripts/ci/r00_source_contract.py`: fail-closed checks for legacy workflow resurrection, secret material, workflow permissions/action pinning, roadmap integrity, and baseline ancestor.
- `.github/workflows/obtainx-r00-contracts.yml`: always-on source/contract lane.
- `.github/workflows/obtainx-r00-flutter.yml`: hosted Flutter analyzer, unit/widget suite, and Android debug compile. No release publication.

## Development principles

Audit source, tests, documentation and workflows for stale contracts **before** changes. Prefer consolidating fixes with their tests in the same commit or overlay. Include positive, negative, and recovery-path tests. A golden test must be repaired or intentionally updated to match current functionality, not skipped without reason.

Use the canonical R00 ZIP bootstrap only for repository setup. Future Devtool work should provide consolidated source-pinned Python ZIP launchers runnable as `python3 overlay.zip` with `rich`, Termux Zsh-safe commands, and temporary extraction under `$TMPDIR`. Do not invent a `.devtool.toml` schema: integrate Devtool only after validating its actual contract.

## R00 status vs qualification

R00 source protection: scaffolded, requires hosted run results.
R00 Flutter analyzer/tests/debug build: scheduled by PR/manual hosted CI, requires hosted run results.
R01 security and archive review: pending.
R02 split APK installation acceptance: pending.
R03+ roadmap: pending.
Android 16 runtime: pending.

No APK is released from this branch.
