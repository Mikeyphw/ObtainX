# R10-F01 — Settings navigation

- The SettingsPage builds the same existing `_SettingsCategory` widgets for compact and wide layouts, separating everyday and advanced groups. No preference values or source credentials are copied into search.
- A localized search entry opens its owning section. Phone navigation expands and scrolls to the header; wide navigation uses the existing credential discard confirmation before selecting another detail pane. Conditional controls remain in their original owning section and keep their platform/installer availability rules.
- The navigation tile shares wrap-capable text, focus feedback, expanded/selected semantics and a minimum 56 logical-pixel height across both layouts. Collapsing preserves the subtree but excludes hidden focus, taps and semantics. Animation duration is zero with platform disabled animations or the existing reduce-visual-effects preference. Large text increases the master/detail breakpoint, and unsaved compact forms cannot be dropped by widening the viewport.
- New navigation strings have en/fr/tr/ja/pt/pt-BR parity; other supported languages use the existing fallback. Full existing translation parity is not asserted.
- `test/r10_settings_navigation_test.dart` drives the actual search and navigation widgets. `scripts/ci/test_r10_settings_contract.py` checks production wiring, retained controls, labels, translations, and safe scoped CI impact. Physical TV/screen-reader/IME qualification remains separate.
- R10-F02 (per-app reset, live regex preview and inline explanations) and R10-F03 (other layout clipping, swipe haptics, homepage, wider keyboard/remote coverage and locale audit) are not claimed by F01.

## R10-F02 — Contextual settings and preview

- Reset stages the source defaults for an explicit tuning allowlist. Confirmation precedes the draft change; the existing save/discard route retains credential, source binding, tracking, trust and unknown fields. Disabled controls stay disabled.
- Existing regex assist for add and edit offers editable expressions and group selection, filename-only APK matching with inversion, release-title and version samples, and version extraction using the production evaluator. Samples are capped and evaluated in a cancelable isolate with a one-second result deadline. No new source request is implied.
- Inline help describes selected installer capabilities, credential/proxy and VirusTotal handling, source override, version detection and signer evidence without changing install or trust policy. Six existing localization sets updated.
- Hosted Flutter and physical-device acceptance remain pending for F02. R10-F03, R11 and R12 remain.

## R10-F03 — Responsive interaction and locale review

- Source homepage is the original tracked listing URL, not an APK or a sibling listing. Both swipe preferences expose the new action; historical integer indices stay stable and names are authoritative. HTTP(S) only; embedded credentials rejected; external browser failure is reported without URL disclosure. App details offers a non-gesture equivalent.
- Swipe threshold feedback uses the existing tactile preference in both directions, resets on retreat/cancel, and re-checks action eligibility on release. Remote navigation exposes configured actions via a focusable menu and TalkBack custom actions. No change to install, delete or trust policy.
- Compact shell navigation has scrollable, keyboard-activatable 48dp targets, with selected labels in wider compact viewports and semantic labels at all sizes. Inactive tabs cannot receive focus or semantics; TV rail scrolls and wraps labels. Existing explicit phone layout preference is retained. System reduced motion and app visual-effects preference govern the shell and swipe transitions. Platform text scaling is no longer clamped at 120%; detail actions and dropdown menus grow rather than shrink labels.
- `R10_LOCALE_REVIEW.json` enumerates every English/French/Turkish/Japanese missing, extra, blank and placeholder mismatch. New action labels translated in en/fr/tr/ja/pt/pt-BR. Existing untranslated keys (90 French, 101 Turkish, 101 Japanese) remain explicit English fallback, not translated parity. Long label and large-text fixtures cover new shared controls. Independent device and language-review acceptance remain pending.
- Hosted Flutter analyzer, actual phone/split-screen/TV navigation, screen reader, platform haptic and contrast checks are separate acceptance gates. R11 and R12 remain.

## R10-F03-HF01 - Analyzer repair

Explicit Flutter semantics import supplies `CustomSemanticsAction` to the existing swipe row. The source-contract test requires the import and production action wiring. This addresses the shared compiler failure on all five failed workflows; hosted analyzer, widget and Android runtime verification remain pending on the new exact commit.
