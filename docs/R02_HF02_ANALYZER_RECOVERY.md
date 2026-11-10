# ObtainX R02 HF02 — hosted analyzer and golden triage recovery

- Parent PR: #2, stacked on the qualified R01 branch.
- Source commit: `c57844de59642867713d23e9fad4470706642575`.
- Hosted run: `42869280795`, completed with failure during `flutter analyze lib test`.
- Source-security CI on that commit: passed (run `42869280963`).

## Verified failure and changes

1. `apps_provider_install.dart:867` emitted `unnecessary_null_comparison` after deterministic R02 archive planning promoted the local parsed path to non-null. Delete only that redundant branch condition. Keep the installed-app guard and APK icon extraction intact.
2. `install_bundle_plan.dart:209` emitted `use_null_aware_elements` on the selected ABI split list. Replace the conditional list element with Dart 3.47's null-aware `?abiMember`. The incompatible-ABI refusal remains mandatory.
3. The older R01 golden-review workflow used `if: failure()`, which also ran after analyzer errors when the full-suite log did not exist. Give the full Flutter test step an explicit ID and gate diagnostic golden generation on the outcome of that specific full-suite step. Update the matching inherited R01 HF02 source and mutation contracts in the same change.
4. Add R02 HF02 contract and mutation tests to mandatory read-only hosted source CI. All preexisting gates and existing adversarial split/ZIP tests remain required.

## Qualification boundary

- Source contracts, Flutter analyzer, R01 archive tests, R02 bundle-planning tests, full Flutter tests, and unsigned Android debug build **must all pass** at the new commit.
- NO RELEASE is authorized. NO signed artifact is produced. Android 16 device-runtime installation remains **NOT qualified**.
- A source-only or debug-build green result must never be described as a successful split-install runtime test.
