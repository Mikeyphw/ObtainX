# ObtainX Fork — Consolidated Development Roadmap

**Planning baseline:** 10 November 2026
**Recommended upstream:** `bikram-agarwal/ObtainX` (not `wizzwuz/ObtainX`)
**Upstream `main` inspected:** `aea18592413de992e813bd063cb9ad453259582b` (4 October 2026)
**Feature reference:** `wizzwuz/ObtainX@f23d202c219ed328b19edaedfff92c49bf0fd348` (24 October 2026), eight commits ahead of ObtainX `main`
**Other pending reference:** PR [#368](https://github.com/bikram-agarwal/ObtainX/pull/368), targeted at `sync/upstream_v1.6.17_20261004`, not assumed merged into `main`
**Status of everything below:** Proposed for the new fork unless explicitly described as already existing or confirmed in reviewed code. Prior audits were source/metadata reviews, not Android runtime qualification.

## 1. Product direction

Build an upstream-compatible, security-conscious Android application updater with reliable release and CI-artifact downloads, correct APK/split-package installation, explainable version decisions, first-class GitHub Actions support, and a streamlined Material 3 Expressive interface.

### Nonnegotiable product principles

1. **Correctness before convenience.** Never call a download complete, a build verified, or an install successful without qualifying evidence.
2. **Visibility of actions.** Checking, downloading, extracting, scanning, awaiting approval, installing, and confirming are different states, each with discoverable controls.
3. **Existing functionality is the baseline.** Preserve ObtainX's multi-source tracking, customizable app list, source swapping, folders, grouping, installation backends, verification settings, and adaptive UI. Audit before duplicating or refactoring them.
4. **Security must survive UI convenience.** No silent bypass of Android prompts, signature mismatches, malware checks, authentication checks, or archive validations.
5. **Upstream synchronizability.** Maintain narrow, tested changes; record divergence from ObtainX and Obtainium; never blindly import a fork's whole branch.
6. **Tests are contracts, not artifacts to preserve unchanged.** Audit every assertion, fixture, hash table, workflow, doc and migration against the actual current implementation; update or remove stale contracts without weakening legitimate checks.

## 2. Source inventory and reuse policy

| Source | Audited status | Integration policy |
|---|---|---|
| [`bikram-agarwal/ObtainX`](https://github.com/bikram-agarwal/ObtainX) | Actual baseline; itself forks Obtainium | Fork this repository; source-pin the first development branch |
| [`ImranR98/Obtainium`](https://github.com/ImranR98/Obtainium) | Original upstream ancestry | Review upstream fixes and reconcile selectively through a dedicated sync lane |
| [`wizzwuz/ObtainX`](https://github.com/wizzwuz/ObtainX) | Eight ahead-of-main commits; GitHub Actions artifacts, picker, retry changes; significant correctness/security concerns | Use as a reference/patch source only; do **not** ship its signing material or cherry-pick everything |
| [ObtainX PR #368](https://github.com/bikram-agarwal/ObtainX/pull/368) | Open deep-link decoding repair with two changed files and non-runtime tests | Rebase and port after validating actual link routing, UTF-8 handling, share intent and duplication behavior |
| [PR #337](https://github.com/bikram-agarwal/ObtainX/pull/337), [#312](https://github.com/bikram-agarwal/ObtainX/pull/312), [#308](https://github.com/bikram-agarwal/ObtainX/pull/308) | Open French, Turkish, Japanese translations | Merge selectively after locale keys/formatting and UI overflow tests |
| Previously merged PRs [#330](https://github.com/bikram-agarwal/ObtainX/pull/330), [#303](https://github.com/bikram-agarwal/ObtainX/pull/303), [#273](https://github.com/bikram-agarwal/ObtainX/pull/273), [#251](https://github.com/bikram-agarwal/ObtainX/pull/251), [#228](https://github.com/bikram-agarwal/ObtainX/pull/228), [#110](https://github.com/bikram-agarwal/ObtainX/pull/110) | Existing implementations of attention handling, multiple sources, backup/icons, installer integrations and performance | Verify current behavior; do not reimplement blindly |
| Other forks | Majority unchanged or behind; narrow translation forks; `thenedj3m`/`teich0psia` feature branches relate to #368 | Consult only for a documented capability not already in baseline |

## 3. Priority and dependency map

**P0 / release blockers:** Signing security; archive validation; APK/APKS/APKM/XAPK installation correctness; immutable download provenance; trustworthy CI; visible and accurate installation outcomes; baseline/stale-contract audit.

**P1 / first major feature release:** Persistent and resumable downloads; GitHub Actions adapter; app detail clarity; Activity Center; compatible APK picker; source/version reliability; improved releases and discovery UX.

**P2 / subsequent refinements:** Adaptive layouts, saved display presets, full history, per-app/channel workflows, Tasker/App Manager interoperability, advanced settings assistance, accessibility/TV polish.

Recommended dependency chain: **R00 → R01 → R02 → R03 → R04 → R05 → R06/R07 → R08/R09 → R10 → R11/R12**. CI and security gates run from R00 onward, not just at the end.

## 4. Engineering milestones

### R00 — Fork bootstrap, baseline and stale-contract audit (P0)

**Implement**
- Create a separately named GitHub fork from `bikram-agarwal/ObtainX` with protected `main`, signed/reviewable source pins and a dedicated upstream-sync branch.
- Inventory Flutter/Dart/Android modules, build variants, CI workflows, version comparison logic, download path, ZIP/tar handlers, install strategies, token storage and UX routes.
- Audit existing tests, fixtures, documentation, locale strings, dependency lockfiles, golden images and hash/signing contracts for staleness against both ObtainX `main` and the proposed changes.
- Record current known defects as regression tests before feature work; distinguish upstream bugs from new fork changes.
- Establish developer diagnostics with structured operation IDs and redacted authentication data.

**Acceptance:** Unmodified baseline can be built and tested in hosted CI; every known baseline failure is documented and classified; no fake green or suppressed failing assertions; source SHAs reproducible.

### R01 — Supply-chain, credentials and archive security (P0)

**Implement**
- **Do not use `wizzwuz`'s committed `android/app/obtainx_signer.jks` or its hard-coded signing password.** Treat the publicly distributed key as compromised; create a new protected signing identity and secret-based release process. Plan for the fact that different keys cannot seamlessly update already installed APKs signed with the old key.
- Remove credential leakage from workflow output; use least-privilege GitHub permissions, protected release environments and pinned third-party actions.
- Add ZIP/TAR extraction limits: maximum compressed/uncompressed bytes, entry count, path length, nesting depth, extraction time/memory, normalized destination containment, no traversal/symlink escapes, duplicate/conflicting entry detection, and cleanup/rollback.
- Use private staging directories, validate extracted content before exposing it to install flow, and preserve reliable cleanup after cancel/failure.
- Ensure GitHub authorization headers and vendor-specific API headers cannot leak on cross-host redirects; do not silently bypass TLS validation.

**Acceptance:** Malicious-archive and credential-redirection tests pass; no private keys or fixed release passwords live in Git; signed APKs have expected certificate identity; release workflow fails closed when signing credentials are unavailable.

### R02 — Package discovery and atomic install plans (P0)

**Implement**
- Replace filename-based APK selection with a structured package discovery step based on Android package metadata and archive manifest content when available.
- Distinguish standalone APK, XAPK, APKS, APKM, generic ZIP/TAR and non-installable artifacts; identify base APK, config splits, language/density/ABI splits and OBB payloads.
- Build a validated `InstallPlan` that records package ID, versionCode, signing identity, min/target SDK, supported ABIs, split requirements and selected installer capability.
- Restore complete split-package installation (the wizzwuz non-XAPK path currently passes one APK only). Never silently treat a necessary set of splits as unrelated APK choices.
- Reuse existing system, Shizuku, Dhizuku and external installer strategies; preserve container handoff where required and supported.
- Add explicit plan review when selection is ambiguous, incompatible or a downgrade; retain Android approvals and verification checks.

**Acceptance:** Device-runtime matrix covers APK, XAPK, APKS, APKM, ZIP, TAR, single/multiple ABI, base+config splits, signature mismatch, downgrade, incompatible SDK, cancellation and external handoff. No success is recorded before Android confirms the resulting package state.

### R03 — Robust download engine and operation persistence (P1, required by R04)

**Implement**
- Formalize states: `queued → checking → downloading → downloaded → verifying → extracting → ready → awaitingApproval → installing → confirming → completed`, with cancellation/failure/retry branches.
- Persist a job ID, source URL, final redirect origin, expected release/build identity, expected content length, ETag/Last-Modified, validated byte offsets, `.part` ownership and completion metadata.
- Resume with `Range`/`If-Range`; reject malformed `Content-Range`, entity changes, ignored byte ranges and incomplete transfers; restart cleanly rather than append corrupt bytes.
- Verify known digests and attestation references; never equate file existence or an unknown `Content-Length` with completion.
- Classify failures: retry transient network/socket/timeout/429/5xx with jittered exponential backoff and `Retry-After`; fail closed for invalid certificates, auth policy errors, corrupt content or invalid metadata.
- Make queue persistence, pause/resume/retry/cancel and foreground service/notification behavior reliable within Android platform restrictions; serialize installs even when downloads run concurrently.

**Acceptance:** Deterministic mock HTTP tests for 200/206/302/401/403/410/416/429/5xx, truncated streams, changed ETags, no content length, dropped connections, app restart, concurrent requests and user cancellation. No duplicated or corrupted output.

### R04 — GitHub Actions as a first-class, source-native channel (P1)

**Implement**
- Add distinct `Releases`, `Prereleases` and `Actions` source modes without hiding Actions behind a mysterious advanced toggle.
- Discover workflows, branch filters, completed/successful runs, run attempt, commit SHA, run ID, artifact ID, creation/expiry, digest and downloadable asset metadata. Filter non-installable artifacts before presenting them as APKs.
- Use GitHub API pagination, authentication, rate-limit handling, expiry and redirect logic; never rely on only the first 100 artifacts or an artifact's filename alone.
- Default to latest successful completed run; support explicit branch/workflow selection and a clearly labeled manual history browser. Unsuccessful-run artifacts should not be offered as trusted automatic updates.
- Validate exact artifact identity before installation; distinguish GitHub artifact digest, trusted APK digest, APK signing certificate and verified build attestation. These are separate claims.
- Reuse the useful fixes from `wizzwuz` for artifact ZIP retrieval/HTTP 415, but audit media types, API-version headers and redirect behavior against current documented GitHub semantics.
- Handle changing artifact inventories, expired archives, private repository tokens, API failures and duplicate filenames gracefully.

**Acceptance:** Real and mocked API tests cover multiple workflows, run attempts, pagination, expired artifacts, non-APK attachments, auth, rate limiting, branch changes, checksum mismatch and exact-revision selection. No accidental install of CI logs or source bundles.

### R05 — Transactional install lifecycle and verifiable receipts (P0/P1)

**Implement**
- Create an `OperationReceipt` for each attempt: repository/source, branch/workflow, run/commit/artifact IDs, downloaded URL origin, SHA-256, certificate identity, selected files/splits, installer backend, Android result and verification timestamp.
- Maintain `pending → handedOff/awaitingApproval → confirmed/failed/cancelled/unknown` distinctly. Do not invent success for an external installer handoff.
- Fix navigation-sensitive approval issues such as [#354](https://github.com/bikram-agarwal/ObtainX/issues/354): dialogs must survive normal route changes and app resume, or be recoverable in Activity Center.
- Replace unawaited post-import installation calls with tracked, error-reporting operations; retain retryable files safely if appropriate.
- Make approval policy explicit and configurable; default to less intrusive extra approval while never disabling confirmations mandated by Android or security policy.

**Acceptance:** An installation cannot remain indefinitely in a fake installing state; interrupted, cancelled, rejected and externally handed-off installs have distinct evidence and user-facing resolution paths.

### R06 — App details redesign and clearer version decisions (P1)

**Implement**
- Preserve Material 3 Expressive, but organize the app details header around **Status → Installed version → Available version → Primary action → What's new → Technical details**.
- Put installed and available versions in explicitly labeled comparison blocks; replace ambiguous red/white marks and color-only cues ([#373](https://github.com/bikram-agarwal/ObtainX/issues/373)).
- Add a visible **Open app** button ([#367](https://github.com/bikram-agarwal/ObtainX/issues/367)), plus History and Options without relying on tapping the app icon.
- Explain uncertain version equivalence and differing versionCode schemes ([#347](https://github.com/bikram-agarwal/ObtainX/issues/347)) using words and evidence, not just icons.
- Render safe, readable GitHub Markdown release notes with consistent typography, links and expandable sections ([#352](https://github.com/bikram-agarwal/ObtainX/issues/352)).
- Keep security status precise: signature match, digest verified, attestation verified, unverified, verification failed.

**Acceptance:** Users can correctly identify installed versus available version, verification state and next action without knowing ObtainX conventions; screen-reader and large-text tests pass.

### R07 — Activity Center and installation/download UX (P1)

**Implement**
- Introduce a persistent Activity Center summarizing checks, queued/active downloads, extraction, scanning, approvals, installation, Android confirmation and completed/failed attempts.
- Prominent `Review`, `Resume`, `Retry`, `Cancel`, `Open` and `Details` actions only when valid for the current state.
- Progress should be quantitative only when measurable; use indeterminate states otherwise. Show transfer size, current step, number of apps checked and per-source failures.
- Keep an entry accessible while awaiting user approval even after navigation to another app; retain notification links to the exact operation.
- Give errors actionable explanations, especially signature mismatch, incompatible ABI, split requirements, expired build artifacts, rate limits and invalid filters.
- Reflect the background checking concern in [#360](https://github.com/bikram-agarwal/ObtainX/issues/360), subject to actual Android background execution limits.

**Acceptance:** Each operation state is visible and recoverable after navigation, interruption and process restart; no hidden confirmation loops; no misleading success/100% indicators.

### R08 — Source reliability, version engine and issue regression fixes (P1)

**Implement**
- Correct version handling for abbreviated prereleases such as `158.0b3 → 158.0b4` ([#336](https://github.com/bikram-agarwal/ObtainX/issues/336)).
- Repair full-URL-versus-filename APK regex filtering ([#353](https://github.com/bikram-agarwal/ObtainX/issues/353)); provide testable pattern preview rather than silently filtering everything.
- Prioritize compatible ARM64 APKs when the device supports both ARMv7 and ARM64 ([#363](https://github.com/bikram-agarwal/ObtainX/issues/363)), unless metadata indicates another constraint.
- Fix the version acknowledgement problem across different package distributor versionCode schemes ([#347](https://github.com/bikram-agarwal/ObtainX/issues/347)).
- Reduce harmful source polling and repetitive HTML scraping; investigate the serious APKMirror request-volume complaint ([#339](https://github.com/bikram-agarwal/ObtainX/issues/339)), favor supported interfaces, caching and respectful rate limits.
- Review APKCombo single-variant fallback ([#333](https://github.com/bikram-agarwal/ObtainX/issues/333)), RuStore 419 ([#345](https://github.com/bikram-agarwal/ObtainX/issues/345)) and Farsroid issues ([#357](https://github.com/bikram-agarwal/ObtainX/issues/357)).
- Fix percent-encoded deep links by porting/reworking [#368](https://github.com/bikram-agarwal/ObtainX/pull/368) with actual routing tests, error isolation and duplication checks.

**Acceptance:** Every addressed issue has a named reproducer test; no regressions in multi-store listings, source swapping or update-on-demand.

### R09 — Better discovery, app list and GitHub artifact picker (P1/P2)

**Implement**
- Preserve present view sheets, folder sort/group settings, categories, badges and multi-source tracking. Refine rather than duplicate.
- Make `Check for updates` and `Update all` distinct controls ([#364](https://github.com/bikram-agarwal/ObtainX/issues/364)); retain non-touch navigation.
- Support app-list search across name, package ID, source and category, with optional Compact/Standard/Detailed presets; consider grid view ([#351](https://github.com/bikram-agarwal/ObtainX/issues/351)).
- Visually group multiple source listings for one installed package, including stable/beta/nightly views. Preserve independent listing-level tracking while avoiding multiple misleading “installed app” tiles ([#338](https://github.com/bikram-agarwal/ObtainX/issues/338)).
- Provide workflow/run browser, file size, ABI, package ID, version, split/standalone role, supported/incompatible reason, trust checks and expiry in APK choice UI. Support explicit user selection and deterministic safe defaults.
- Clearly distinguish `everything current`, `not checked yet`, `only track`, `needs attention` and `no matching source` empty states.

**Acceptance:** All core actions are discoverable without hidden gestures; wrong-ABI/split options show clear incompatibility; multiple-source rows cannot imply duplicate independent installs.

### R10 — Settings usability, accessibility and responsive layout (P1/P2)

**Implement**
- Keep all existing advanced options but group routine settings separately from expert controls; provide settings search and per-app reset.
- Add live regex previews using fetched artifact names; explain installer capabilities, tokens, certificate warnings, source override and version detection inline.
- Address clipped text ([#372](https://github.com/bikram-agarwal/ObtainX/issues/372)), broken swipe haptics ([#365](https://github.com/bikram-agarwal/ObtainX/issues/365)), discoverable homepage action ([#349](https://github.com/bikram-agarwal/ObtainX/issues/349)), screen reader labels, contrast, minimum touch targets and reduced-motion support.
- Extend existing tablet/landscape layouts to keyboard, mouse, D-pad and Android TV ([#350](https://github.com/bikram-agarwal/ObtainX/issues/350)); do not assume swipe/pull-to-refresh is available.
- Review French/Turkish/Japanese contributions (#337/#312/#308) for locale-key parity, placeholders and long-string overflow.

**Acceptance:** Small phone, large font, split-screen, landscape, tablet and TV interactions meet the same actionable UX contracts; all primary controls are accessible via keyboard/remote/screen reader.

### R11 — Integrations, policy and history (P2)

**Implement**
- Implement package-name deep links and `SHOW_APP_INFO` integration ([#371](https://github.com/bikram-agarwal/ObtainX/issues/371)) with unambiguous handling of multiple source listings and caller trust boundaries.
- Provide opt-in Tasker/automation actions: check updates, queue a download, read state, retrieve a receipt. No silent install if Android or user policy requires approval.
- Integrate with App Manager where installed: open details, inspect trackers/signatures and hand off supported install intents; fail gracefully if absent.
- Maintain per-app, per-channel history and receipts with privacy-aware retention and export; never treat an old receipt as proof of current safety.
- Add user-configurable Wi-Fi/charging/quiet-hours/rate-limit rules within Android OS restrictions; explain when system restrictions postpone work.

**Acceptance:** External intents, task triggers and export work under minimum required privileges; no token disclosure, wrong-app routing or unwanted installation.

### R12 — Full qualification, packaging and release (P0 release gate, after required features)

**Required hosted lanes**
1. Flutter formatter, analyzer and unit/widget tests; source/API fixtures.
2. HTTP interruption/redirect/rate limit and persisted download recovery integration.
3. Archive adversarial corpus, path/symlink/zip-bomb constraints, APK and split-package planning.
4. Installer strategy contracts, pending-install lifecycle and persisted receipts.
5. Accessibility/layout/golden review with actively maintained golden expectations.
6. Source-contract drift audit: validate canonical implementation, tests, docs, permission policies, dependency locks and hashes together.
7. Release signing, provenance, dependencies, secret scan, reproducible build checks where applicable and package metadata.
8. Android device/emulator runtime matrix, including API 36, system/Shizuku/Dhizuku/external backends where supported and actually accessible.

**Status reporting:** `SOURCE_PASS`, `HOSTED_CI_PASS`, `DEVICE_RUNTIME_PASS` and `RELEASE_QUALIFIED` are distinct, evidence-backed outcomes. Inconclusive is not success. Publishing requires passing all mandatory gates, or an explicit documented scoped-release exception that does not claim full qualification.

## 5. Core architecture/contracts to introduce

- **`SourceReleaseIdentity`**: source URL, package/listing key, source type, version label, build/commit ID, source timestamp and comparison evidence.
- **`ArtifactIdentity`**: provider, repository, workflow/run/attempt/artifact identifiers, original URL and final download origin, digest and expiry metadata.
- **`ArtifactInventory`**: discovery results including APKs, split bundles, non-installable attachments, sizes, ABI hints and parsed metadata.
- **`InstallPlan`**: selected standalone/split sets, package/version/certificate constraints, supported installer backend, verification policy and required approval.
- **`OperationState`**: persisted state machine with guarded transitions and abort/retry semantics.
- **`OperationReceipt`**: immutable evidence for source, selected exact file(s), verified digest, signing, selected backend and install outcome.

All models should be additive/migratable for existing ObtainX users, retain import/export compatibility where promised, and avoid writing secrets into logs or exports. Prefer isolated adapters and pure Dart logic for deterministic tests.

## 6. UI information architecture

- **Apps:** categorized library, update status, source labels, Check updates, Update all, direct row actions, search and saved view presets.
- **App details:** explicit state, Installed/Available comparison, safe changelog, Update/Download/Install/Open actions, Source & Channels, Verification, History, Options.
- **Add app:** URL import, search, installed-app discovery, bulk import, GitHub workflow/release source selection with source preview.
- **Activity:** persistent check/download/install queue, approvals, progress, retry/cancel and receipts.
- **Settings:** Everyday / Advanced, search, contextual explanations, download policies, installer behavior, security and backups.

Keep current app styling and adaptive layout concepts; prioritize clear labels, whitespace, screen-reader semantics and action visibility over more decorative chrome.

## 7. Quality matrix and test fixtures

| Area | Must-have fixtures and assertions |
|---|---|
| Source discovery | Successful/failing workflow runs, 100+ artifact pagination, expired artifacts, private repo, renamed repo, multiple branches and releases |
| Downloads | HTTP 200/206/302/401/403/410/416/429/5xx, dropped sockets, timeouts, ETags, missing content lengths, concurrent jobs, process restart |
| Archives | ZIP/TAR, path traversal, symlink, duplicate entries, excessive count/size/depth, nested archives, partial extraction rollback |
| Installation | APK, APKS, APKM, XAPK, ZIP, ABI preference, base+config split sets, signature conflict, downgrade, unknown result, cancellation |
| UI flows | Fresh install, first-time add, open existing, app return/navigation, approval dialog, bulk update, account/token problem, deep link and share intent |
| Accessibility | TalkBack semantics, long translations, scaling, reduced motion, keyboard/mouse, Android TV/D-pad |
| Trust and history | Correct distinctions among digest, certificate, attestation, CI success, scan result, installer confirmed state |

## 8. Delivery workflow and governance

- Each phase is a **source-pinned, consolidated change**, including implementation, necessary tests, documentation, locale edits, manifests and stale-contract repair; do not maintain contradictory legacy tests.
- Use feature branches and reviewed PRs; avoid unreviewed direct main changes and unintended automatic merges.
- Prefer reproducible **GitHub Actions** for Gradle/Flutter/Android qualification, with independent device-runtime evidence.
- For Devtool-based local delivery, package a Python launcher **inside** the overlay ZIP (`python3 overlay.zip`), use `rich` UI, keep Termux invocation Zsh-safe, stage temporary files under `$TMPDIR`, and fail closed if source pins or preconditions mismatch.
- Keep structured receipts with exact source and output SHA-256 and hosted run links; redact secrets and do not store signing material in the repo.
- Qualify each feature against current upstream to avoid redundant implementation, especially after Obtainium syncs.
- Follow GPL-3.0 obligations, attribution, and licensing of transplanted contributions.

## 9. Release milestones

| Milestone | Includes | Definition of done |
|---|---|---|
| **M0 — Audited fork** | R00, CI baseline, source pins, drift inventory | Reproducible baseline and issue/test traceability |
| **M1 — Secure and install-correct** | R01–R02, initial R05 contracts | No exposed signing; archive security; atomic split-package tests pass |
| **M2 — Resilient download core** | R03 plus operation persistence | Resume/retry/restart tests pass and progress is accurate |
| **M3 — GitHub Actions parity+** | R04 and artifact picker subset of R09 | Validated workflow/artifact browsing and verified ZIP/install path |
| **M4 — Cohesive daily UX** | R05–R07 plus R06 core app details | Discoverable operations, approval recovery, clear versions and receipts |
| **M5 — Reliable sources and polish** | R08–R10 | Known issue regressions fixed; accessibility/layout and localization verified |
| **M6 — Integrations and qualified release** | R11–R12 | Verified Android-runtime evidence, signed safe releases and migration notes |

## 10. Deferred / explicitly out of scope for the first release

- Claims of security based only on CI success or unknown hashes.
- Automatic installation of artifacts from unsuccessful/unverified workflow runs.
- Bundled signing keys, fixed signing passwords, or insecure auto-fallback installation.
- Universal silent-install promises on Android without backend-specific capability checks.
- Rewriting ObtainX's Material 3 interface, deleting advanced options, or reimplementing already merged multiple-source/grouping features.
- Auto-merge from Obtainium or wizzwuz without source, test and behavior audits.

## 11. Immediate first implementation slice

1. Establish the new fork and pin the inspected ObtainX baseline; inventory branch/CI/test state.
2. Introduce signing/security policy and archive adversarial fixtures.
3. Add failing tests for the non-XAPK split-install regression and expired/failed Actions artifacts.
4. Implement `ArtifactIdentity`, `InstallPlan` and basic operation-state contracts, preserving existing app storage and installer strategy behavior.
5. Deliver R01–R02 as a consolidated, CI-qualified change before user-facing Actions UI or further automation.

**Final project rule:** Features are not “done” because a source patch applied or an APK built. “Done” means reviewed semantics, current contracts, hosted tests, appropriate Android runtime evidence and release provenance are all recorded.
