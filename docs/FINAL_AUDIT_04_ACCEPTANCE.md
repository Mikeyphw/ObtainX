# FINAL-AUDIT-04 — Acceptance, release safeguards and CI deduplication

## F08 accessibility and language evidence

The shared navigation/primary action widget regression covers 280×640 compact,
640×320 landscape and 1024×768 wider layouts at 200% text, visible labels,
48dp navigation controls and actual callbacks. Existing keyboard navigation,
reduced-motion, swipe, locale-inventory and all-route Flutter regressions remain.
This is shared-control coverage, not all-route physical or language acceptance.
Use the existing R12 accessibility lane with actual device evidence for TalkBack,
text scaling, contrast, keyboard/mouse/TV, and localized safety controls. Review
small/landscape/tablet/split-screen screens and consented external actions;
review the five translated locale sets with native-language reviewers and retain
English fallback for other locales. Record failures instead of approving by
screenshot alone. Do not launch or install anything on a personal device without
separate permission. No live screen-reader, contrast or native linguistic pass is
claimed by this overlay.

## F10 CI deduplication (OPT09)

All six required workflows keep their workflow/job names, actual decisive steps,
read-only permission and manual dispatch. Normal PRs, including drafts, request
full qualification immediately. Readiness changes no longer start a new run and
do not change scope. Only the explicit `ci:development-only` label selects scoped
non-accepting feedback; the same source job refuses full qualification. Removing
the label triggers fresh qualification; adding it revokes acceptance. GitHub's
pull_request label trigger cannot filter by label name at the event level. Keep
label and reopened events conservative rather than skip a required check as a
false success. Unrelated label changes can therefore still trigger work.

Post-merge keep the fresh main source-contract job for commit/ancestry checks.
For the separate manual release candidate admission, use the latest actual full
main jobs when available. If a runtime main job is absent, reuse a prior full PR
job only when the GitHub-verified direct two-parent merge, closed/merged PR,
same repository and branch, exact PR head and exact main tree all agree. The
complete tracked Git tree binds workflow definitions, lockfiles and tracked build
inputs; compare real API run/attempt/job identities and completed decisive steps,
including the full PR source proof. Never replace a failed, running, cancelled or
scoped matching run with an older success. Reject partial inventories, changed
main, altered merge trees, squash/rebase ambiguity and missing evidence. If reuse
is unavailable, independently execute the missing full main lanes; if a main
lane has failed, diagnose and repair it. Do not auto-dispatch any release job.
Receipt v2 names each original source SHA, common tree, actual workflow/run/
attempt/job and evidence mode, and distinguishes fresh-main from merged-tree
provenance. The signer reobserves the same evidence and protection configuration
before decoding key material. Reused runtime evidence is not a fresh main
execution claim; no signed candidate or physical qualification is implied.

The protected candidate workflow remains explicit manual dispatch only. It now
requires observable protection rules before builders: independent reviewer,
prevent self-review, explicit disabled administrative bypass, and protected
branches or a main-only custom branch policy. Main must be protected at dispatch
and still the current exact ref at CI recording/signing. The actual repository
protection configuration has not been independently accessible to this agent;
missing/hidden fields or access denial must block signing rather than be assumed.
Actual release-mode builds, exact formatter, dependency inventory and reviewed
licenses/advisories, independent unsigned reproducibility, isolated protected
signing, device matrix and separate publication approval remain mandatory.

## F12 historical audit and package lookup

The original R00 baseline was explicitly NOT QUALIFIED. GitHub Actions inventory
for this fork at original source `aea18592413de992e813bd063cb9ad453259582b`
returned zero runs during the audit on 2026-11-27; this does not prove no external
or expired historical evidence ever existed. Retain the historical missing
baseline, do not infer it from later green cumulative suites. The stale skipped
candidate-name test now exercises real `getInstalledInfo` on the current native
`device_apps` channel: order, absent result, first hit and unrelated-package
refusal of debug suffix. The active RT02 Android integration route and its
standalone fallback also verify the actual debug app identity and installed
fixture version. No native channel mock in those Android tests.

## Verified predecessor

PR #33 exact head `1a6eb840826d4907c308d592488a7ee7ea7c6e98` completed all six
original required workflows (RT02B attempt 2). The readiness event started six
unnecessary replacement workflows; two succeeded and four were cancelled. Do
not count those cancellations as acceptance. PR #33 merged at
`f956206348828370c339d412957b25a8ab41f697` with identical tree
`b6167f2d51724f6ad9a7e437ffc2c11ead42cee2`; main source-integrity run 46052423555
passed. The FINAL-AUDIT-04 implementation requires its own new full qualification.
Prior audited F03 and F06 unsupported capability decisions and all historical
external acceptance obligations remain unchanged. No signing, tag or publication
authorization is granted here.
