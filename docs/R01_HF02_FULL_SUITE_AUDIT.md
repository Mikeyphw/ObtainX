# R01 HF02 — Hosted Full-Suite Failure Audit

Source head before hotfix: `215faea403e1a894bd34c706a8e656042c5820a7`.
Failed hosted workflow: [42850485515](https://github.com/Mikeyphw/ObtainX/actions/runs/42850485515).

**Observed (2026-11-10)**: Flutter analyzer and R01 archive adversarial tests PASS; full suite 810 passed / 15 failed / 1 skipped. Debug APK build skipped. R01 must remain unmerged.

## Root cause A: obsolete device-info test fixtures

The lockfile resolves `device_info_plus 13.3.0`. Its `AndroidDeviceInfo.fromMap` now requires the integer Android Build.TIME, while the `BaseDeviceInfo` fixtures in `source_provider_test.dart`, `version_order_test.dart` and `multi_source_app_actions_test.dart` omitted it. This triggers `type 'Null' is not a subtype of type 'int'` and cascades into F-Droid ABI, GitHub, GitLab, URL list and multi-source update tests. Add deterministic `time: 0` **to the test doubles only**; do not weaken production ABI, installer or networking behavior.

## Root cause B: preexisting golden reference drift

Six strict bitmap comparisons (`test/apps_scroll_work_test.dart` two tests × three states) show 1.30%–1.49% mismatch. R01 does not change the app-list UI. Preserve `matchesGoldenFile` strict comparisons. A failure-only CI diagnostic may generate fresh reference PNGs, but *the full-suite job remains failed* until the exact new references have been audited and committed. Only a reviewed, Linux/Flutter 3.47.6 generated set with all six files, unchanged dimensions, small pixel diffs, and immutable CI run/commit provenance can be accepted.

## Release and merge gates

- All R00/R01 source mutation and adversarial archive tests must pass.
- Full Flutter suite must pass **against committed goldens** (not automatically refreshed during the passing test).
- Unsigned Android debug APK build must pass; this is not runtime qualification.
- No bypass, skipped test, signing key import, force-push, merge or release is authorized by this change.
