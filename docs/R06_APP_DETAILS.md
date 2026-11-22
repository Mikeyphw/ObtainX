# R06 — App details, installed/available versions, and visible actions

**Milestone:** R06, source-pinned on R05. **State:** implementation candidate, not CI- or device-qualified until the resulting commit passes the exact-HEAD required gates.

**Qualification marker:** `NOT_QUALIFIED` — the R06 source is not yet committed or hosted-qualified, and physical-device, accessibility and release-signing acceptance remain pending.

The November 18 canonical snapshot is incorporated in this same R06 overlay at `docs/ROADMAP.md`; the complete November 10 engineering specification remains embedded unchanged. The roadmap is a dated record and does not imply R01–R05 have merged into main.

## Changes

- Retain ObtainX's established source/version-decision engine, `AppVersionDisplayVerdict`, ambiguity/variant warnings, installer gating, skip semantics, editing and settings preferences. No cosmetic comparison overrides source-bound facts.
- Replace only the old cramped Installed/Latest rows with labeled, wrap-safe Material version tiles; preserve badges for pseudo/OS version codes, skipped releases, filtering and unknown values. The status strip remains first and explicit; the tiles carry proper screen-reader labels instead of color-only meaning.
- Make **Open app** a visible action only when the OS reports the exact same installed package ID. A tracked/pseudo version or handoff never manufactures installed-app evidence.
- Expose **Install history** from app details and filter the existing R05 operation receipts by that exact package ID. R07 will extend the recovery surface to a full Activity Center; this scoped history does not prove any install's success.
- Keep the existing options control, update/downgrade safety, and user preference for action buttons at top/bottom. Put release notes in their own **Changelog** section, using the existing source-selected dialog and Markdown parser, between the version/action overview and technical details. If no source data exists, do not invent notes.
- Preserve independent security cards: reproducible build evidence, GitHub attestation, malware scanning and installed signing certificate remain distinct signals. Unknown/unverified conditions are not coerced into `verified`.

## Checks and regressions

- New widget tests cover installed vs latest, long version/OS uncertainty, skipped/filtered badges. Existing app-page tests gain positive/negative real-package gating for the Open action.
- Retain the existing full Flutter analyzer, unit/widget suite and Android API36 installer gates. New UI/contract paths explicitly trigger the same six required workflows and source-bound CI scope classification.
- R00 roadmap SHA-256 receipt is updated to the new content. The stacked-PR base policy and R04 contract negatives are advanced from R05-on-R04 to R06-on-R05 **without** deleting the six exact workflow IDs, the event gate or signature/source evidence checks.
- Native Devtool 3.2+ validation performs only relevant Python source/negative tests locally; the hosted Flutter and Android workflows remain mandatory at the *resulting new commit*. No skipped gate is called a pass.

## Exclusions and next milestone

R07 remains the next milestone: persistent cross-stage Activity Center, actionable progress, cancel/retry/review/resume controls, notification deep links and restart-safe queue reconciliation. R06 does not claim complete accessibility sign-off (TalkBack, large-text and TV need actual runtime review), physical-device installation, release signing, attested APK production or R12 release qualification.
