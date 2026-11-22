# RT02D — Device-aware split planning and conservative OBB staging

**Stacked after:** RT02C HF04 / PR #7 exact SHA `b5d0d5f3419562ae3c80916b03ec1d75f24d86ae`. RT02C remains the proven API36
emulator-only installation benchmark (five archive formats, two refusals,
seven cases in one Flutter process). RT02D is **not full Android runtime
qualification** and does not supersede RT02C's accepted scope.

## Scope

1. Resolve matching language splits for all configured device locales,
   preferring exact language/region then language-only fallback. Refuse an
   ambiguous set without trustworthy locale information; do not install
   language variants unrelated to configured device locales.
2. Choose the closest known density split using device-reported pixel ratio
   converted to approximate Android DPI. Refuse multiple alternatives without
   display evidence, reject duplicates, and leave `anydpi`/`nodpi` neutral.
3. Preserve base APK, ABI, minSdk and package/version checks, and keep legacy
   single-candidate split behavior to avoid disrupting RT02C's verified fixture.
4. Validate lexical containment of staged OBB paths inside the extraction root,
   on top of existing owner/filename checks. Runtime extraction must still
   reject symlinks and non-regular files; lexical checks are not a filesystem
   identity proof.
5. On Android 11+ (API 30+), refuse an OBB bundle *before* invoking stock,
   Shizuku or Dhizuku APK-only installation when no verified OBB storage delivery
   path is available. Supported original-container external handoff is left
   intact; no OBB copy or installation success is fabricated.

## Acceptance and limitations

The mandatory R00 Flutter job runs both original R02 planner tests and the
new RT02D compatibility tests. The R00 source workflow runs dedicated mutation
checks and verifies the new hosted test gate. RT02C's six-workflow job remains
unchanged and must pass at the new exact commit.

This change does **not** implement reliable OBB write access for Android 11+;
that requires backend-specific SAF/OS verification and independent device
receipts. It does not prove user cancellation, Android TV, external installer
commit state, Shizuku/Dhizuku runtime, or release signing. Those remain RT02E+
acceptance tasks. No merges, releases, or physical-device claims.
