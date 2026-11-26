## GAP-03 — Durable operations and scalable history (26 November 2026)

Exact PR #30 preimage `af0303c1de5adef091e8c3516e0d0f1c5da5dd74`, tree `2c84dea6ef171176dcf9e08e1ffc3c9851329f58`: GAP-02-HF02 passed all six hosted workflows (45858825612, 45858825367, 45858825480, 45858825479, 45858825392, 45858825494). GAP-03 implements the G06/G07 remediation: durable source-bound operation queue/events, exact partial transfer resume, parent-linked retry, process-aware recovery, paginated history, separately archived terminal R03/R05 metadata and exact scoped retention. Preserve unresolved and unknown-channel records, original native approval and installer exact-byte integrity. See `docs/GAP03_DURABLE_HISTORY.md` for implementation boundaries and runtime tests. New hosted and device qualification remain pending; no release authorization. Remaining GAP-04 provider/discovery closure, GAP-05 accessibility/integration closure and R12 qualification/packaging/release; historical physical acceptance remains open.

## GAP-02-HF02 — Standards-compliant XZ fixtures and integrity regressions (26 November 2026)

Exact source PR #30 `7903b719103cd59e1b41e59454e2fca935f4c6b8`, tree `cf06cbbd285b7f04567974ca3f95d03851b8d6e7`. Source integrity, API36 bootstrap, RT02, RT02B and RT02C passed. Hosted Flutter 45845135531 (job 139996889422) passed strict analysis and named gates, then failed exactly one full-suite test (`streaming extraction handles xz and nested APKs`); 1063 passed, one skipped. Golden triage correctly refused unrelated failure. The pinned archive 4.3.0 encoder writes XZ index VLIs most-significant group first; its decoder and XZ format require least-significant group first. Reproduced independently: 2048-byte TAR and 2072-byte unpadded stored block encode index prefix `000190189000`, rather than `000198108010`. Independent liblzma accepts the canonical stream and rejects the defective one. The original XZ security fixture already passed; no production decoder, dependency, resource limit, cancellation, staging or checksum behavior is relaxed. Replace the invalid generated positive fixture with independent compressed XZ, freeze the legacy malformed index, verify CRC32/CRC64/SHA256 and >64 KiB output through the real Flutter extractor, add corrupted block-check and output-budget refusals with cleanup assertions. Independent Python fixture tests and all existing source contracts remain mandatory. Actual new strict Dart analysis, Flutter tests, APK compilation and six hosted lanes pending; physical/device and release acceptance remain separate. Earlier GAP-02-HF01-F01 native/hosted evidence is retained at its exact source, not promoted to this candidate. GAP-02 closure, GAP-03, GAP-04, GAP-05 and R12 remain outstanding.

## GAP-02-HF01-F01 — Native safe-path RT02F import and analyzer repair (26 November 2026)

Supersedes the uncommitted GAP-02-HF01 payload after native transaction `20261126T143558Z-bf6c9923c597` rolled back on RT02F P02 `test_actual_cli`: the operator sets `PYTHONSAFEPATH=1`, so direct script execution cannot resolve sibling `r02_rt02_hosted`. Bind imports to the tracked script directory and retain hardened Python execution; verify direct invocation with `-P` and competing import names. All five original analyzer corrections and all original gates retained. Native validation must run the complete Python suite in the hardened environment, with bounded failing test identities and retained private test logs. Hosted Dart analysis, six required workflows, device and release acceptance remain pending; no release authorization.

## GAP-02-HF01 — Strict Dart analyzer repair (26 November 2026)

Exact failing PR #30 source `7f3317b4dc578c8ad4d73848aa106b863368405d`, tree `3a91e168bc79db41f3f4c3dc58120ff6086b29e4`. Source integrity (45744621465) and API36 bootstrap (45744621492) passed; Flutter (45744621486), RT02 (45744621473), RT02B (45744621481) and RT02C (45744621629) all failed the same five strict Dart diagnostics before runtime tests. Remove redundant import and null-aware close only on the proven nonnull path; keep nullable acquisition-error cleanup. Add braces to the installed-evidence and guarded record-write exits; forward the BZIP input via the named superclass constructor without altering range or buffer. Keep strict analysis and all runtime gates. Exact new hosted, native and physical acceptance pending; no release authorization. Remaining GAP-02 integrity closure, GAP-03 durable operations/history, GAP-04 provider/discovery closure, GAP-05 accessibility/integration closure and R12 qualification/packaging/release; historical acceptance remains open.

## GAP-02 — Archive, installation and receipt integrity (implementation in progress)

Preimage PR #30 `6d6ee442074c3b97b42107133d107ddff9ba257b`, exact tree `dd246fc37de98513dd6eb86a4634679828b2b16f`. HF03 all six hosted workflows passed (45724553853, 45724553776, 45724553821, 45724553857, 45724553805, 45724553790). GAP-02 tracks G03–G05 from the cumulative gap audit: bounded extraction with cancellation and orphan recovery; manifest-based selected APK inventory and per-member verified current signers; actual downloaded artifact identity and exact installed-state evidence bound to each operation. Confirmation publication is guarded at the queued record write and immediately before atomic rename; timeouts settle only their captured attempt, never the latest receipt for a listing. New private native evidence plugin registers on foreground and background engines; pinned apksig verifier independently verifies each member. No Android/backend/hosted or full acceptance claim from this source candidate; no release authorization. Remaining GAP-03 durable operations/history, GAP-04 provider/discovery closure, GAP-05 accessibility/integration closure, R12 qualification/packaging/release and historical acceptance.

## GAP-01-HF03 — hosted debug runner UID readiness

Exact PR #30 preimage `79565a52b38ff675b06b6924ea684598c717cc06`, tree `3a74b8a030c259c46e87f5d38c7cc72c6a13294c`. Source integrity 45720658902, Flutter 45720658886, API36 bootstrap 45720658754, RT02 45720658823 and RT02B 45720658856 passed. RT02C 45720658890 passed real archive sessions, abandoned-session verification and incompatible-SDK rejection, then failed in P03 before cancellation proof: `adb rc=255 Error: No UID for dev.bikram.obtainx.debug in user 0`. Flutter can replace the runner between package-path query and app-op. Use a single exact user-0 readiness/eligibility boundary across the RT02 hosted pollers; clean absence and exact No UID for the fixed debug package defer to the next existing bounded poll, other errors refuse; authenticated case preparation requires actual eligibility. P03 preserves real approval, cancellation, signed-byte and independent audit gates, and reaps its isolated Flutter child on failure. No app source, credential isolation, attestation or release-policy change. New six-workflow hosted qualification remains pending. Remaining GAP-02 archive/install/receipt integrity, GAP-03 durable operations/history, GAP-04 provider/discovery closure, GAP-05 accessibility/integration closure, R12 qualification/packaging/release; historical acceptance remains open.

## GAP-01-HF02 — deterministic store-discovery widget regression

Exact PR #30 preimage `4c648523035a1551232042e71af4b80aedf6e630`, tree `78346bcca7f0de41b9535124cf125ca13d284467`. Source integrity 45708290318, API36 bootstrap 45708290386, RT02 45708290758, RT02B 45708290482 and RT02C 45708290434 passed. Hosted Flutter 45708290639 passed strict analysis but failed one widget test (`an unconfirmed store shows no chip`) with an outstanding 30-second APKMirror HTTP timeout in the fake clock; 1052 passed, one skipped. Keep the production scan service and secure transport unchanged, expose its actual page dependency, and use a controlled pending and then negative answer in the widget fixture. Assert exact listing dispatch, one scan and no speculative chips before or after completion. No skipped tests, altered golden images, changed timeout policies or weakened trust. Hosted full-suite requalification pending. Remaining GAP-02 archive/install/receipt integrity, GAP-03 durable operations/history, GAP-04 provider/discovery closure, GAP-05 accessibility/integration closure, R12 qualification/packaging/release; historical acceptance remains open.

## GAP-01-HF01 — strict GitLab header analyzer repair

Exact GAP-01 PR #30 preimage `affcb3ba6a99f8b9c5bbc7090035939d0102bc15`, tree `30b9bb2d7ae75f155b3468f150c3955dcb5dced8`. Source integrity 45704323139 and API36 bootstrap 45704322971 passed. Hosted Flutter 45704323060, RT02 45704322962, RT02B 45704322982 and RT02C 45704322976 independently failed at `lib/app_sources/gitlab.dart:149:7` (`use_null_aware_elements`). Use a null-aware map value so a missing PAT omits the header without changing exact-origin restrictions. Retain the existing nonnull-token and cross-origin tests and add an anonymous request assertion. No analyzer waiver, weakened transport policy, or attestation verification promotion. New full hosted qualification pending. Remaining GAP-02 archive/install/receipt integrity, GAP-03 durable operations/history, GAP-04 provider/discovery closure, GAP-05 accessibility/integration closure, R12 qualification/packaging/release and historical acceptance.

## GAP-01 — Transport and artifact trust

Exact R11-HF01 preimage PR #30 `8108b88c2ab505380fc5823dd58adfb813ebba09`, tree `d89bf7e56c7d4617461142c37f81181edf5aacbd`, six hosted workflows passed (45685124032, 45685124124, 45685124039, 45685123978, 45685124093, 45685123983). Cumulative audit G01/G02 require exact-origin transport and fail-closed attestation handling. Shared source and download probes enforce origin isolation, no downgrade or cross-origin body replay, preserve Actions host restrictions. GitHub API attestation presence is unverified; legacy verified values are invalidated and Enforce remains blocking until a supported cryptographic verifier exists. See GAP01_TRANSPORT_TRUST.md. Hosted/device acceptance pending; no release authorization. Remaining GAP-02 archive/install/receipt integrity, GAP-03 durable operations/history, GAP-04 provider/discovery closure, GAP-05 accessibility/integration closure, R12 qualification/packaging/release. G14 remains Devtool-owned.

## R11-HF01 — strict Dart analyzer repair

Exact failed PR #30 source `2d7fbfd16c8b5a52c8bbd530e02c88d518b68675` (tree `05c400c670f0c6400fb55c97419e62f6e24e56f1`). Source integrity 45680600644 and API36 install/launch 45680600618 passed. Flutter 45680600604, RT02 45680600615, RT02B 45680600608 and RT02C 45680600659 failed strict analysis on eight `curly_braces_in_flow_control_structures` findings across home, update provider, operation journal, automation and external request parser. Add blocks without changing guard conditions, return/continue behavior, permissions or acceptance gates; guard the eight production branches with regression tests. Full hosted qualification and historical physical-device acceptance pending. Remaining R12 — final qualification, packaging and release.

## R11 — Integrations, policy and history (consolidated)

Exact preimage PR #30 `120a6c708814f6bb35003ca20a8730cc891747fb`, tree `2aa0ea8490c5dc917e08e1bfb465a57a426da058`: R10-F03-HF02 passed all six hosted workflows (45672205209, 45672205128, 45672205119, 45672205143, 45672205449, 45672205129). Historical physical-device, release and native acceptance-state debt remain visible.

R11-F01 external navigation; R11-F02 opt-in foreground automation; R11-F03 App Manager details/inspection and existing approved external installation lane; R11-F04 listing/channel history with redacted export and terminal-receipt retention; R11-F05 automatic scheduling conditions. These five scopes form one R11 overlay; see [R11 integrations](R11_INTEGRATIONS.md) for exact limits and test matrix. New hosted and physical acceptance pending. R12 final qualification, packaging and release remains.

## R10-F03-HF02 — cancel-safe swipe and visual preservation

PR #30 HF01 head `8b1a3a2e7c2abc012e0fe767e71ea36dc7135feb` (tree `d35b6040e8c7a40b92be3a259db05a7c2509ba7a`) passed source integrity and all four API36 installer workflows (45660268750, 45660268960, 45660269352, 45660269392, 45660268623). Flutter 45660269765 passed analysis, then reported 1033 passed, one skipped and two failures: canceled threshold swipes reached pin persistence, and reduced-effects swiping differed by 192 pixels. The existing golden triage correctly refused the mixed failure. Require actual single-pointer release, never dispatch on cancellation, preserve tactile eligibility and semantic actions, restore direct drag visual proportions while still disabling timed settling in reduced motion and scaling when platform animations are disabled. Retain exact goldens and full required workflows. New source-bound hosted qualification and physical acceptance remain pending. R11 integrations, policy and history and R12 final qualification and release remain.

## R10-F03-HF01 — Flutter semantics import repair

Exact failed PR #30 source `f6e15991dd665b57754a12bcbb6a9a6d5957497a` (tree `1049a95d54f9ede50e78957bbc5f8718cf956835`). Source integrity passed; hosted Flutter, API36 bootstrap, RT02, RT02B and RT02C failed at the undefined `CustomSemanticsAction` in `lib/pages/apps.dart` (runs 45641502056, 45641501610, 45641501456, 45641501824, 45641501464). Explicitly import the Flutter semantics declaration and guard the production custom action wiring. No accessibility action, installer policy, test or qualification gate removed. Six full hosted workflows must qualify the new head; physical acceptance and historical native session-state debt remain pending. Remaining R11 integrations, policy and history; R12 final qualification and release.

## R10-F03 — responsive interaction, homepage and accessibility

Base: PR #30 `748aca044aa698648e66e7cf0feb637cee545b79`; all six full hosted workflows passed (45632972344, 45632972643, 45632972567, 45632972463, 45632972492, 45632972446). Preserve historical receipt and native acceptance-state debt. Implement swipe homepage and tactile feedback, gesture alternatives, adaptive shell/detail actions, growing dropdowns, keyboard/remote focus and reduced motion. Audit French, Turkish and Japanese keys/placeholders with explicit fallback inventory. F03 hosted analysis/runtime and physical acceptance pending. Remaining R11 (integrations, policy and history) and R12 (qualification, packaging and release).

## R10-F02 — contextual settings and regex preview

Base: PR #30 `108072be51feed1a16580a7307d35dc303cbe785`; all six hosted workflows passed, including the source-bound API36 cache retry. Reset source-specific tuning drafts; preserve identity, security, tracking and credentials; use the existing explicit save/discard path. Bounded regex sample preview uses production filter/extraction semantics. Explain installer modes, tokens/proxy, scanning, certificates, source override and version detection in context. No installer-policy changes. F02 hosted and physical-device acceptance pending. Remaining R10-F03 (broader accessibility/responsive UI, homepage, haptics, TV and locale audit), R11 and R12.

# ObtainX — R10-F01 settings navigation and accessibility (25 November 2026)

**Exact preimage:** PR #30 `43bdce31c357680844c8cb822a6b7e0cedbae341`, tree `327a4ca8d6dec418f7dc7e5dcf9a52cd9362b7e9`. All six hosted workflows passed (45614779758, 45614779765, 45614779793, 45614779913, 45614779721, 45614779728), including real RT02C archive sessions and independent package-state checks. R09 physical acceptance and historical debt remain.

**R10-F01 scope:** routine and advanced navigation shared by compact and master/detail layouts; search public localized setting labels and open their real owning section; retain all settings and existing credential discard confirmation; wrap navigation labels, visible keyboard focus, screen-reader expansion/selection state, 56dp minimum targets, collapsed content excluded from input/focus/semantics while retaining drafts; honor system disabled animations and existing reduce visual effects preference; choose single-pane layout at large font scales; localized new strings in en/fr/tr/ja/pt/pt-BR, English fallback elsewhere. Settings search is navigation, not a second form; conditional device/backend controls keep existing gates. OPT07 adds closed-world settings impact tests; changing the classifier requires one migration full run, later settings-only edits can use scoped CI. No installer behavior change or local Gradle. Hosted Flutter widget tests and device screen-reader/D-pad/large-text verification pending. Remaining R10-F02: per-app reset and regex/inline capability explanations; R10-F03: broader app-wide layout, homepage/swipe haptics, TV and full locale audit. R11 and R12 remain.

---

# ObtainX — R09-F02-HF02 signer decoding and bounded runtime diagnostics (25 November 2026)

Exact preimage PR #30 `db50bc9d36b1421b7d95a525b53fad63170c320d`, tree `ff349dcc56de9051c2a3bf8072afb8624e1850ad`. Five workflows passed; RT02C run 45607589734 stopped in first APKS scenario before installer authorization. Artifact 15018577512 retained generic DART_TEST_FAILED only. Pinned android_package_manager b5bc0365 native SigningInfo.toMap emits apkContentsSigners, Dart SigningInfoImpl reads apkContentSigners; the app's direct native decoder must normalize the wire key for both targeted and bulk queries. Current signer is never inferred from certificate history. This is a confirmed source defect explaining an empty installed-signer result, not an independently observed failing Android assertion. Preserve exact signer comparison and all seven runtime cases. Emit and retain bounded current-case checkpoint/error enums, native inspection refusal category, and independently observe exact v1 package bytes even on pre-install failures. No raw private log, token, path or stack trace publication; no local Gradle. Hosted Android rerun needed. R02/R07/R08 device/provider acceptance, R09 runtime acceptance and R10–R12 remain.

---

# ObtainX — R09-F02-HF01 strict analyzer repair (25 November 2026)

**Preimage:** PR #30 `f5148be4ff648eced81c0d8a3cd9841ecfb9cb5b`, tree `e0c7a2dd676524cdd8af177f67aac42bc00dc126`. Source integrity and API36 bootstrap passed; Flutter 45545836923, RT02 45545836720, RT02B 45545836850 and RT02C 45545836865 each stopped before their remaining tests at `prefer_const_declarations` in `test/r09_artifact_inspection_test.dart:29`.

**Repair:** declare the constant MapEntry fixture with `const`, preserving its inaccurate filename and verified-metadata selection assertion. Add a named source mutation guard for the exact previous declaration. Do not suppress any lint or alter production APK inspection, signing, digest binding or installer checks. Actual hosted analysis and signed-APK acceptance are pending. Keep incremental CI scope based on the last independently qualified full baseline; the unqualified R09-F02 native changes still require the full matrix. R02 device/backend, R07 and R08 acceptance debt, R09 hosted/device qualification and R10–R12 remain. No local Gradle.

---

# ObtainX — R09-F02 manifest-backed artifact review (25 November 2026)

**Preimage:** PR #30 `00e75b8f7510edd4b2868768b6af453522102bf0`. Six exact-head hosted runs passed: 45540847786, 45540847761, 45540847851, 45540847720, 45540847812, 45540847781. R09-F01 and incremental CI have hosted qualification on that predecessor; no transfer of acceptance to this tree.

**R09-P05 follow-up:** explicit bounded review of actual APK bytes, package/version/SDK/split/ABI and observed certificates; existing Actions identity and digest validation, private staging, HTTPS redirect isolation, bundle planner, exact selection digest before normal extraction. No automatic install or attestation claim. R09-P01–P06 implementation scope retained; actual hosted analyzer, signed-fixture manifest inspection and physical UI acceptance remain pending. This touches Android and shared transfer/install paths, requiring full impact CI. R02 device/backend, R07 persistent activity, R08 provider qualification, R09 acceptance, R10, R11 and R12 remain.

---

# R09-F01-F01 — strict Dart analyzer correction (25 November 2026)

Exact preimage `b9214fc3a1475cbcc5231dae381b94a67b1b9dfd` (PR #30).
Source integrity and API36 bootstrap passed. Flutter run 45535792958 and
installer runs 45535792769, 45535792671, 45535792819 failed before their
runtime tests on the same four analyzer infos. Use a null-aware map value
for the optional bound source URL and explicit blocks for the artifact
refusal and history selection branches. Preserve repository binding,
compatibility rejection and expiry recheck semantics; no lint suppression.
Named mutation regressions reject all four previous patterns. Strict hosted
analysis and current R09/OPT07 CI acceptance still required. No local Gradle.
CI-OPT07 retry: when a verified baseline selects full Flutter and all four
Android lanes, allow the actual full decisive proofs to establish the new
baseline without a duplicate full run. Explicit development-only and
unverified-baseline fallback still refuse full acceptance. Narrow impact
remains scoped. This policy edit requires a fresh full migration run.
R09-F02 verified metadata inspection, R10–R12 and prior device/provider
acceptance debt remain. No release authorization.

---

# CI-OPT07 — incremental development qualification (consolidated with R09-F01)

Draft PRs default to scoped qualification. The planner looks for a recent full
first-parent ancestor with all six exact-source run/job/decisive-step proofs,
falling back to the pinned verified HF13 run identities. Changes since that
full source accumulate; scoped/deferred results cannot become a full baseline.
A ready-for-review PR or `ci:full-qualification` requests every full lane;
manual dispatch also runs full lanes. `ci:development-only` always prevents
full acceptance. A commit changing the actual CI routing policy/workflows
runs the full matrix once (deterministic first-parent decision); this combined
R09/OPT07 migration therefore runs all six. Two bounded native transactions
(R09 then OPT07) produce one final PR update; no intermediate remote push. Unknown impact or unavailable
baseline evidence runs all lanes but remains scoped on draft PRs. Scope-only
checks retain the intentional RED full-qualification refusal after source tests.
Every required workflow triggers on every PR mode-change event; only expensive
jobs defer. Strict full-source Dart analysis and mapped regression suites run
for impacted Dart/UI paths. No local Gradle, no skipped runtime pass, no release
or merge approval. Full qualification remains mandatory before merge.

---

# ObtainX — R09-F01 discovery candidate (25 November 2026)

**Exact preimage:** PR #30 `e3960a6779f9139c72810748c1001198d82e8f94`, tree `b502f623e796eaf747aebff2ee4024fff2c3399e`. All six prior-head required workflows passed (45528116294, 45528116304, 45528116492, 45528116325, 45528116334, 45528116315). RT02C real five archives, two refusals and independent receipts passed. R09 does not inherit this hosted qualification.

**R09 scope:** existing view options with presets; distinct check/update review; combined app search and smart-folder persistence; opt-in package grouping and conflict-safe listing selection; bound Actions history and APK compatibility/trust preview; accurate scope state labels. See `docs/R09_DISCOVERY.md`. R09 source gates and hosted tests remain mandatory; no local Gradle. Unknown metadata remains explicitly unknown; optional grid deferred.

**Remaining:** R02 physical/backend acceptance; R07 Activity Center acceptance; R08 provider acceptance; R09-F01 hosted/device acceptance and R09-F02 verified artifact metadata/inspection; R10 settings/accessibility; R11 integrations/policy/history; R12 qualification/packaging/release. No direct main write.

---

# ObtainX — R08-F06 / RT02C-HF13 analyzer and integration scope repair (25 November 2026)

**Preimage:** PR #30 `ab089d69760468c1520765de2a6cd92e9dd0e630`.
Source/contract integrity, hosted Flutter and API36 bootstrap passed. RT02
`45519856826`, RT02B `45519857002` and RT02C `45519856767` stopped before
Android execution with `prefer_collection_literals` at HF12's list.toSet().

**Repair:** all three digest pairs must be unequal before any case is prepared;
no set or collection conversion. Source mutation checks cover both previous
lint-triggering forms, missing/duplicate/weakened or late comparisons, warning
and info suppression, and strict analysis scope in the main Flutter and all
three installer workflows. Full hosted Flutter now analyzes integration_test
alongside lib and test. Targeted Flutter already includes integration_test.
The separate workflows still run in parallel; no claim that one gates another.
Strict actual Dart analysis and all seven RT02C cases remain mandatory. No
local Gradle. R02/R07/R08 runtime acceptance remains pending; R09–R12 remain.

---

# ObtainX — R08-F05 / RT02C-HF12 analyzer regression (25 November 2026)

**Preimage:** PR #30 `a01e6dd2718880f231869d5a850f12e1222dc897`.
Source/contract integrity, hosted Flutter and API36 bootstrap passed. RT02
`45515825848`, RT02B `45515826206` and RT02C `45515826129` all stopped before
Android execution with `equal_elements_in_set` at the HF11 digest assertion.

**Repair:** use `[v1Sha, baseSha, splitSha].toSet().length` at runtime, preserving
exactly three distinct digests. The RT02C source gate rejects the original
compile-time set literal (including reordered elements), missing/weakened
assertions, duplicate inputs, and warning suppression. Mutation tests exercise
the rejected cases and permit formatting variation. Existing strict hosted
integration analysis and all seven Android cases remain mandatory. The Python
source guard is not a substitute for actual Dart analysis or hosted Android
acceptance. No Gradle runs locally. R02, R07 and R08 acceptance remain open;
R09, R10, R11 and R12 remain implementation/qualification work.

---

# ObtainX — RT02C-HF11 owned foreground session (24 November 2026)

**Preimage:** PR #30 `33a9a6fa489111f0b5f02744bdb07fb708d1e84e`.
Five of six required workflows passed (including hosted Flutter #110); RT02C
run `45512130442` failed at APKS with `INSTALLER_TIMEOUT_NO_APPROVAL`, 57
`FIXTURE_NOT_VISIBLE` observations, no approval, and exact signed v1 intact.

**Repair:** RT02C now exercises the production foreground StockInstaller route
used by AppsProvider: an exact, sealed InstallPrecommitGate selects the first-party
owned session bridge. The legacy plugin uses activity-delivered callbacks and
requests no user action; the first-party route uses a session-specific broadcast
and explicit Android approval. Each positive case must return success and a
matching native terminal journal with exact listing, Android status and v1/v2
signed member hashes. The host requires a unique native session ID, one real
installer approval and independently checks installed signed base and split
bytes before acknowledgement. The negative cases cannot supply a session ID.
Failure evidence includes only allowlisted native session and terminal states.
No change to standalone or negative legacy-plugin lanes, no synthetic approvals,
no replay, no local Gradle, no weakened seven-case coverage.

**Acceptance:** source implementation candidate; runtime resolution requires a
fresh exact-head hosted run. The absent UI in the prior legacy route is proven;
the particular Android callback failure was not observed directly. Physical
device and release acceptance remain separate. R07/R08 acceptance remains open;
R09, R10, R11 and R12 remain implementation/qualification work.

---

# ObtainX — R08-F03 / RT02C failure-repair candidate (24 November 2026)

**Preimage:** draft PR #30 `60f44d5fdfc1616e54a7d59b3b9b101b89312228`,
main `181191cc9a09c9c3053d837a3dfb24e9d98bafa0`. The previous six-workflow
batch reported four successes; Flutter run 45459045853 failed on a stale
URL-matching test and RT02C run 45459045944 stalled at the first APKS
installer call. The latter's actual tested merge SHA was
`c1289426c73ead0656ab9f7fcc2e31194fc35bea` (same source tree).

**Repair scope:** retain R08-P02 filename-only semantics and reconcile the
legacy source-provider test. Classify RT02C failures by actual phase; require
a fresh successful UI hierarchy before an explicitly identified installer tap;
retain bounded per-case approval outcomes and exact package-state observations
before cleanup. Approval observation no longer holds the controller lock across
slow hierarchy reads, and a late snapshot must reauthorize its exact active
case before any bounded tap. Fixture and action must belong to the same
recognized installer UI. All six required workflows now check out the actual
PR head (push/manual dispatch use their exact event SHA); fixture, receipt,
cache and artifact identities share OX_EXPECTED_SHA. A structural gate and
negative tests reject merge-SHA substitution and stale UI authorization.
No retries after an installer call, no synthetic approvals,
no raw private UI/Flutter logs, and no promotion of failed tests to success.
The specific prior installer stall remains unproven until a new hosted run.

**Acceptance:** source candidate only; fresh native and required hosted CI
receipts, CI24 if configured, Android device and release gates remain separate.
Remaining: R07 Activity Center acceptance; R08 Source reliability/provider and
integration acceptance; R09 Discovery, app list and picker; R10 Settings and
accessibility; R11 Integrations, policy and history; R12 Release qualification.

---

# ObtainX — R08 source reliability candidate (24 November 2026)

**Predecessor:** PR #30 R07-F02 head `e008f52b7d1f801a0f27c73dafccead3dc701f02`;
all six required GitHub-hosted workflows reported success on that exact head.
`main` remains `181191cc9a09c9c3053d837a3dfb24e9d98bafa0`. Preserve prior receipts.
R07 complete persistent check/extraction/scan history, Android process-restart
approval, background counts and physical-device UX remain unqualified.

**R08 candidate:** Mozilla prerelease aliases; filename-only APK matching and
preview; compatible ARM64 precedence with F-Droid metadata; matching manual
source acknowledgement; bounded APKMirror request pacing and optional HTML
work; APKCombo single-variant fallback; defensive RuStore/Farsroid handling;
encoded add-link routing and exact-event deduplication. See
`docs/R08_SOURCE_RELIABILITY.md` for source scope and unresolved provider proof.
No direct main write. Continue the consolidated draft PR #30 only through
native Devtool with a fresh source-bound session. CI24/device/release separate.

**Remaining:** R07 acceptance debt; R08 provider and integration acceptance;
R09 — Discovery, app list and picker; R10 — Settings and accessibility;
R11 — Integrations, policy and history; R12 — Release qualification.

---

# ObtainX — R07 Activity Center implementation candidate (24 November 2026)

**Verified source baseline:** merged PR #29 `main` at `181191cc9a09c9c3053d837a3dfb24e9d98bafa0`
(tree `2f409c11f02e1698dc5619d0555015a6e3957e0a`). This is a new, independently reviewable R07 overlay;
the historical R00–R06 sections below remain unchanged for audit.

**R07 changes:** direct Activity Center tab, Settings and app-history
routes, merged *read-only* R03/R05 journal projection, unique attempt
notifications, status-gated actions and explicit unknown/approval
resolution. No new install-success journal or source authority.

**Acceptance:** source candidate until native schema-v3 Devtool
validation, new PR source-bound required CI, CI24 and real Android
device/notification/approval tests establish their independent gates.
Release/signing remains separately unqualified. See `docs/R07_ACTIVITY_CENTER.md`.

**Next:** R08 — Source reliability; R09 — Discovery and app list;
R10 — Settings and accessibility; R11 — Integrations, policy and
history; R12 — Release qualification.

---

# ObtainX — PR #29 forward integration into main (23 November 2026)

**Exact pre-integration refs:** accepted `main` `990b3287e8a4d121be720d8684ebe255909d12b8` (PR #25), and
R06-containing R05 branch `1cd3a8701af59b165f4a0b33db480b2c6e0c624d` (PR #26 merged into R05).
**Remediation:** merge `main` into the existing PR #29 branch with an
exact-tree-preserving merge; set the committed required-CI base to `main`;
update R04/R05/R06 source and negative contracts together. The six
required workflow identities, release separation, native approval and
original Android installer baseline safeguards are unchanged.
**Acceptance:** source candidate until native Devtool validation,
non-force PR #29 update, and six *new* exact-head required CI checks
pass. CI24, physical Android device and signed release remain separate
and are **NOT ATTESTED** by this reconciliation. No direct main write.
**Remaining:** R07 — Activity Center; R08 — Source reliability;
R09 — Discovery and app list; R10 — Settings and accessibility;
R11 — Integrations, policy and history; R12 — Release qualification.

---

# ObtainX — Post-consolidation reconciliation (23 November 2026)

**Current authoritative GitHub baseline:** `main` at `bde1f1234c88a939477b988c5b5fd6fbcb6696a8`, merged through PR #28. The preceding R01–R04 stack (#15–#24) is contained in the accepted Git history; superseded PRs #16–#24 are closed, not separately merged. Existing security acceptance was source-specific and is not physical-device or release qualification.

**Pre-merge CI:** six independent workflows passed on exact integration source `bdd26247bd7c9b3a2bbd8bcb66219bb4d58d0c8c` (R00 contracts `45245822651`, Flutter `45245823008`, API36 `45245822596`, RT02 `45245822338`, RT02B `45245822529`, RT02C `45245822723`). **Post-merge:** R00 push source integrity passed for `main` at `bde1f1234` (run `45247737093`). This is not CI24 or physical/release acceptance.

**Current drafts:** R05 PR #25 (transactional installs, verifiable receipts, recovery) is rebased *logically by non-force merge* onto accepted `main`; R06 PR #26 (app details, clearer version decisions, install history) follows the updated R05 branch. Both PRs remain drafts with independent fresh exact-head six-workflow checks required. No draft was merged, no force push was used, and no Gradle was invoked locally. R06's historical 18 November snapshot below is retained for audit, but its old PR/main/CI states are superseded by this section.

**Remaining overlays:** R05 — Transactional installs; R06 — App details and history; R07 — Activity Center; R08 — Source reliability; R09 — Discovery and app list; R10 — Settings and accessibility; R11 — Integrations, policy and history; R12 — Release qualification. Each remains independently subject to full implementation, regression and acceptance gates.

---

# ObtainX — Canonical Roadmap and Qualification Snapshot

**Snapshot date:** 18 November 2026 (UTC; verified after 21:07 UTC)  
**Repository:** [Mikeyphw/ObtainX](https://github.com/Mikeyphw/ObtainX)  
**Canonical path:** `docs/ROADMAP.md`  
**Original specification:** 10 November 2026; **restored intermediate snapshot:** 11 November 2026  
**Scope:** full engineering milestones **R00–R12**, Android runtime lanes RT01–RT02F, and release milestones M0–M6.  
**Evidence status:** GitHub repository/PR/check-run metadata rechecked 18 November 2026. Evidence here is historical and SHA-specific, not an evergreen promise about future branch heads.

> **How to read this file:** This dated snapshot is the current status and execution order. The complete 10 November R00–R12 specification is preserved **unchanged** in the appendix below and remains the feature/acceptance baseline. Its original “proposed” statements, old implementation status and historical delivery example do not override this newer evidence or the current Devtool v3.2 source contract. Any later branch, CI or release claim must be reverified against its own exact SHA.

## A. Source-of-truth and merge status (18 November)

- `main` HEAD: `538a9ba5c57382ca717a87528ac269eeae7ae826` (R00 bootstrap). It **does not** yet contain the R01–R05 stacked PR implementations.
- Latest implementation: [PR #25](https://github.com/Mikeyphw/ObtainX/pull/25), branch `feature/obtainx-r05-transactional-install-20261116`, exact HEAD `e4ac28fd7bd7a45ca0df977d51bac824087ce72b`, Git tree `5afb5f2eb9a91e2a29fbcf2b47ab72501e60f1b5`. The PR base is R04 branch `feature/obtainx-r04-actions-source-native-20261115` at `86ad4d0fe16e484f355ac71c7d05fdb2505ea21b`.
- GitHub reports PR #25 **open, draft, mergeable/clean**, with 25 changed files, **no submitted reviews and no review threads** at inspection. Clean merge status and green hosted CI do **not** constitute an approval to merge.
- PRs **#1–#25** are **open and unmerged**, forming a dependency stack. Do not merge from the top, skip reviewing parents, squash away audit provenance without review, force-push, auto-merge, or claim `main` contains features that exist only in PR branches.
- A future R06 branch should depend on the reviewed R05 feature state, not on R00 `main` as if R01–R05 were merged. Keep a dedicated, clean named feature branch, with an explicitly chosen reviewed PR base, for each native delivery.

### GitHub PR inventory at the snapshot

This full list is a snapshot of every open, stacked PR head through R05, not a claim that all earlier heads were separately requalified on 18 November. Each full SHA is repository-reported.

| PR | Workstream | Exact PR HEAD | State |
|---|---|---|---|
| [#1](https://github.com/Mikeyphw/ObtainX/pull/1) | R01: archive limits and atomic extraction | `3a57cfdced5940d3cdebd2396ba9c86c21d4926c` | Open, unmerged |
| [#2](https://github.com/Mikeyphw/ObtainX/pull/2) | R02: deterministic APK/split plans | `dd297f3e0e503e1a1b59b0ce2a0b629e05808204` | Open, unmerged |
| [#3](https://github.com/Mikeyphw/ObtainX/pull/3) | RT01: API36 bootstrap/installed APK proof | `eee62aa6d0b6eadec5543d6ed0ee67e3fc57e373` | Open, unmerged |
| [#4](https://github.com/Mikeyphw/ObtainX/pull/4) | RT02A: real standalone/split install | `c1ec76cc2b34147c171a9be40c62fdc6411eefac` | Open, unmerged |
| [#5](https://github.com/Mikeyphw/ObtainX/pull/5) | RT02B: signature/downgrade rejection | `3d435792348e719a1f366c1ee44f5a2529ba0bc3` | Open, unmerged |
| [#6](https://github.com/Mikeyphw/ObtainX/pull/6) | RT02C: archive-to-installer API36 | `4ffa6203e15973b3c2efe9bf4afc1af3997814af` | Open, unmerged |
| [#7](https://github.com/Mikeyphw/ObtainX/pull/7) | RT02C: single-session optimization | `b5d0d5f3419562ae3c80916b03ec1d75f24d86ae` | Open, unmerged |
| [#8](https://github.com/Mikeyphw/ObtainX/pull/8) | RT02D: device split selection / OBB safety | `678d5a20807674c26325d29a64b27df6ec13384b` | Open, unmerged |
| [#9](https://github.com/Mikeyphw/ObtainX/pull/9) | RT02E: verified OBB handling | `112a09d4c1cc852717a9965e7e30cf2f85898546` | Open, unmerged |
| [#10](https://github.com/Mikeyphw/ObtainX/pull/10) | RT02F: external handoff and CI routing | `90888b0fcea5e89420afb48accfa8972d5f49c22` | Open, unmerged |
| [#11](https://github.com/Mikeyphw/ObtainX/pull/11) | RT02F: external session abandonment | `0dac5a2aba90118bfb6f050b86526851ae3a4e8e` | Open, unmerged |
| [#12](https://github.com/Mikeyphw/ObtainX/pull/12) | RT02F: UI cancellation/recovery | `1743ee8bbb6e63170be89563a0169c49afafeee0` | Open, unmerged |
| [#13](https://github.com/Mikeyphw/ObtainX/pull/13) | RT02F: external provenance / backend matrix | `1003037dbd0d0517b6846eb1a53a3337e294a414` | Open, unmerged |
| [#14](https://github.com/Mikeyphw/ObtainX/pull/14) | RT02F: external decline | `ffa82a8650a8f7772f1f85e98b0aa7661de05afb` | Open, unmerged |
| [#15](https://github.com/Mikeyphw/ObtainX/pull/15) | RT02F: external approval / signed bytes | `14625b01043def888127f0637bb884539d9cb0e0` | Open, unmerged |
| [#16](https://github.com/Mikeyphw/ObtainX/pull/16) | RT02F: external approval diagnostics | `50184478b9932ef725679be8151c93c9e4b55b71` | Open, unmerged |
| [#17](https://github.com/Mikeyphw/ObtainX/pull/17) | RT02F: full source/approval contracts | `3af3de8c26a2164d3cbdecd8da63c982d4517f1e` | Open, unmerged |
| [#18](https://github.com/Mikeyphw/ObtainX/pull/18) | RT02F: native approval broadcast | `498f52e1f42221d6914303aa70e3c7215af199fc` | Open, unmerged |
| [#19](https://github.com/Mikeyphw/ObtainX/pull/19) | RT02F: exact-SHA CI path gates | `5fe3639844f2c1c0f210c12acb433fd0b92472ed` | Open, unmerged |
| [#20](https://github.com/Mikeyphw/ObtainX/pull/20) | RT02F: adversarial / Shizuku-Dhizuku paths | `c3b96b8cda72f1a4b2de96b594e9cc85ad8e5dfa` | Open, unmerged |
| [#21](https://github.com/Mikeyphw/ObtainX/pull/21) | RT02F: device/OBB profile receipts | `17662996fa1295867aa43c12afb1b7f5f8820dcc` | Open, unmerged |
| [#22](https://github.com/Mikeyphw/ObtainX/pull/22) | R02: consolidated local import and install review | `65156fe19438f9a7c119cd7aaa80d9bc8ec91bf9` | Open, unmerged |
| [#23](https://github.com/Mikeyphw/ObtainX/pull/23) | R03: resumable downloads and persistence | `1874e6a09888adcba0f12a2bbc55788c7d5c76ba` | Open, unmerged |
| [#24](https://github.com/Mikeyphw/ObtainX/pull/24) | R04: GitHub Actions source channel | `86ad4d0fe16e484f355ac71c7d05fdb2505ea21b` | Open, unmerged |
| [#25](https://github.com/Mikeyphw/ObtainX/pull/25) | R05: transactional installs and receipts | `e4ac28fd7bd7a45ca0df977d51bac824087ce72b` | Open, unmerged, draft |

## B. Milestone status — evidence-limited

| Phase | Implemented / supported evidence through 18 November | Remaining acceptance or next action |
|---|---|---|
| **R00 — Baseline and contract audit** | Baseline commit on `main`; active R00 source/Flutter CI and scoped-test routing at later exact PR SHAs | Continue auditing source drift, current tests/gates and upstream; no unverified CI or stale contracts |
| **R01 — Archive security / supply chain** | Bounded atomic archive extractor, adversarial ZIP/TAR protections from PR #1; inheritance covered by later hosted tests | Protected production signing identity, redirection/credentials/release security need separate end-to-end assurance; not a release-signing pass |
| **R02 — Install plans and runtime safety** | PRs #2–#22: APK/split plan, API36 real standalone/split install and negative gates, archive-to-installer paths, ABI/locale/density and SDK selection, OBB safety, cancellation, external handoff, availability checks, local SAF import | A hosted emulator is not every physical device or installer; unsupported OBB and Shizuku/Dhizuku privilege paths remain explicitly bounded; physical-matrix evidence is separate |
| **R03 — Resumable download core** | PR #23 exact-HEAD required CI **6/6 PASS**; validator-bound HTTP Range/ETag resume, byte/hash receipts, retry and restart contracts documented | Android device/network interruption and production source/credential behavior remain independently testable; do not infer a release pass |
| **R04 — GitHub Actions source channel** | PR #24 exact-HEAD required CI **6/6 PASS**; workflow/run/attempt/artifact selection, bounded pages, optional manual history, redirects with credential isolation, ZIP digest gate | Live private-token, device installation, source-specific redirects and signed release remain separate checks; ZIP digest ≠ APK signer/attestation |
| **R05 — Transactional installs and receipts** | PR #25 exact-HEAD required CI **6/6 PASS**, including real API36 installer rerun attempt 2; journal/receipts, approval recovery surface, observed futures, unknown/cancelled/confirmed distinctions | Still **draft/unmerged**; final code review, physical-device UX/installer evidence, accessibility, signing and release tests outstanding. Do not apply another failure-repair overlay solely for already-green CI |
| **R06 — App details and version UX** | **Next implementation milestone**; not yet qualified | Full R06 scope and acceptance plan below; one consolidated native implementation, current tests/docs and verified CI |
| **R07 — Activity Center and operation UX** | **Next implementation milestone after/alongside R06 planning**; R05 supplies a *basic* Settings → Install activity and approvals screen, not the full R07 Activity Center | Unified check/download/install view, durable operation navigation and actionable recovery, no duplicate state engines; see acceptance plan below |
| **R08 — Source/version reliability** | Planned | Version/prerelease, regex, ARM64, polling, source adaptors, deep-link regressions with named reproducers |
| **R09 — Discovery, list and picker** | Planned; some Actions/manual selection primitives already exist in R04 | Distinct Check vs Update, multi-source grouping, compatible artifact picker, explicit empty states; build upon existing UI |
| **R10 — Settings, accessibility and responsive UI** | Planned; limited settings controls added during R05 | Search, clear everyday/expert settings, TalkBack, scaling, keyboard/TV, localization, layout tests |
| **R11 — Integrations, policy and history** | Planned | Safe Tasker/App Manager/deep links, receipt history/export, OS-compliant scheduling and permission boundaries |
| **R12 — Device, signing and release qualification** | **NOT QUALIFIED** | Complete real-device/backend matrix, provenance/signing, negative security, accessibility and publication evidence |

**Status vocabulary:** `SOURCE_PASS`, `HOSTED_CI_PASS`, `DEVICE_RUNTIME_PASS` and `RELEASE_QUALIFIED` are separate judgments. The six green hosted workflows establish only the named required hosted lane at the exact PR HEAD. Hosted Android emulator cases are runtime evidence **for those specific emulator scenarios**, not physical-device, external-backend, full-product or release qualification. Skipped optional checks are not passes.

## C. Exact-HEAD CI ledger through R05

The six workflow names/IDs below match the committed `config/delivery-required-ci.json` on the R05 branch. Every linked workflow run was checked via its exact SHA-associated GitHub check-run; each of the six required workflows reports **success** for all four phase heads in this table. Each phase's Hosted Flutter workflow also contains an **optional scoped-analysis job marked `skipped`** plus successful Android debug/Flutter qualification and exact-SHA classifier jobs; the skipped job is **not** included in the six passes.

| Phase / PR | Exact SHA | GitHub PR state (18 Nov) | Required workflow result |
|---|---|---|---|
| [R02 / #22](https://github.com/Mikeyphw/ObtainX/pull/22) | `65156fe19438f9a7c119cd7aaa80d9bc8ec91bf9` | Open, unmerged | 6/6 PASS |
| [R03 / #23](https://github.com/Mikeyphw/ObtainX/pull/23) | `1874e6a09888adcba0f12a2bbc55788c7d5c76ba` | Open, unmerged | 6/6 PASS |
| [R04 / #24](https://github.com/Mikeyphw/ObtainX/pull/24) | `86ad4d0fe16e484f355ac71c7d05fdb2505ea21b` | Open, unmerged | 6/6 PASS |
| [R05 / #25](https://github.com/Mikeyphw/ObtainX/pull/25) | `e4ac28fd7bd7a45ca0df977d51bac824087ce72b` | Open, **draft**, unmerged | 6/6 PASS |

| Required workflow (ID) | R02 #22 | R03 #23 | R04 #24 | R05 #25 |
|---|---|---|---|---|
| R00 Source and Contract Integrity (`413437262`) | [PASS](https://github.com/Mikeyphw/ObtainX/actions/runs/43675315960) | [PASS](https://github.com/Mikeyphw/ObtainX/actions/runs/43751711157) | [PASS](https://github.com/Mikeyphw/ObtainX/actions/runs/43884084054) | [PASS](https://github.com/Mikeyphw/ObtainX/actions/runs/44393146089) |
| R00 Hosted Flutter Qualification (`413437265`) | [PASS](https://github.com/Mikeyphw/ObtainX/actions/runs/43675316045) | [PASS](https://github.com/Mikeyphw/ObtainX/actions/runs/43751711085) | [PASS](https://github.com/Mikeyphw/ObtainX/actions/runs/43884083975) | [PASS](https://github.com/Mikeyphw/ObtainX/actions/runs/44393146029) |
| R02 API36 Emulator Bootstrap (`413666807`) | [PASS](https://github.com/Mikeyphw/ObtainX/actions/runs/43675316000) | [PASS](https://github.com/Mikeyphw/ObtainX/actions/runs/43751711112) | [PASS](https://github.com/Mikeyphw/ObtainX/actions/runs/43884083981) | [PASS](https://github.com/Mikeyphw/ObtainX/actions/runs/44393146046) |
| R02 RT02 Real System Installer (`413864665`) | [PASS](https://github.com/Mikeyphw/ObtainX/actions/runs/43675316026) | [PASS](https://github.com/Mikeyphw/ObtainX/actions/runs/43751711107) | [PASS](https://github.com/Mikeyphw/ObtainX/actions/runs/43884083729) | [PASS](https://github.com/Mikeyphw/ObtainX/actions/runs/44393146191) |
| R02 RT02B Negative Installer (`414136383`) | [PASS](https://github.com/Mikeyphw/ObtainX/actions/runs/43675316004) | [PASS](https://github.com/Mikeyphw/ObtainX/actions/runs/43751711136) | [PASS](https://github.com/Mikeyphw/ObtainX/actions/runs/43884083910) | [PASS](https://github.com/Mikeyphw/ObtainX/actions/runs/44393146012) |
| R02 RT02C Archive-to-Installer (`414158361`) | [PASS](https://github.com/Mikeyphw/ObtainX/actions/runs/43675316070) | [PASS](https://github.com/Mikeyphw/ObtainX/actions/runs/43751711113) | [PASS](https://github.com/Mikeyphw/ObtainX/actions/runs/43884083997) | [PASS](https://github.com/Mikeyphw/ObtainX/actions/runs/44393146044) |

**RT02 controlled rerun:** R05 `rt02-real-install` [run 44393146191](https://github.com/Mikeyphw/ObtainX/actions/runs/44393146191), **attempt 2**, `pull_request` event, head SHA `e4ac28fd7bd7a45ca0df977d51bac824087ce72b`, GitHub status `completed/success`, updated **18 November 2026, 21:07:16 UTC**. No source commit changed between attempts. The operator-provided installation report records one explicitly approved standalone APK installation; a split APK update confirmed by Android without an extra approval dialog; and independent package-state verification for both. The report also describes a recovered, explicitly reported pre-Dart installer-bridge failure. **Those scenario-level observations are from the operator report**; this snapshot independently verified the run's successful metadata, not the raw device logs.

**Not equivalent to full acceptance:** This R05 result does not assert that Shizuku/Dhizuku, every external installer, real private GitHub sources, physical hardware or release signing were exercised. The PR remains draft; approval and merge are future actions.

## D. Immediate next implementation: R06 — App details clarity

**Goal:** make an app's current state, trustworthy version evidence and next safe action understandable without prior ObtainX knowledge, preserving Material 3 Expressive and current multi-source/grouping/installer backends.

1. **Primary information hierarchy:** visible status → **Installed** version → **Available** version → primary action → safe Markdown **What's new** → technical/verification details. Different package-distributor versionCode schemes and unknown comparisons must show explicit uncertainty, not inferred equivalence.
2. **Direct actions:** context-aware `Check`, `Update`/`Download`/`Install`, and a clear **Open app** when installed; access to `History`/`Options` without icon-press tricks. Never show an invalid or falsely enabled action.
3. **Evidence labels:** visually and accessibly separate source listing, downloaded ZIP/hash proof, APK signer comparison, attestation, and Android-installed state. A source workflow's success is not a signed APK proof.
4. **Release notes:** safe GitHub Markdown, readable text/links/expansion, graceful missing/oversized notes. Avoid rendering active HTML or leaking auth tokens through links.
5. **Acceptance:** source/installed/available state fixtures (up-to-date, newer, prerelease, versionCode mismatch, unverified, error, no installed package, multi-source); widget/golden/screen-reader and large-text tests; regression coverage for existing navigation, settings, grouping and install states. Targeted Flutter and native overlay checks, then six required exact-HEAD hosted workflows. Physical usability evidence is separate.

**R06 exit:** one consolidated, source-pinned change with reviewed source, current tests, docs and non-obsolete gates; all required exact-HEAD hosted workflows pass, and remaining physical/a11y limitations are recorded rather than silently waived.

## E. Next implementation: R07 — Full Activity Center

**Goal:** evolve R05's minimal install activity/approval screen and R03's download persistence into **one user-visible cross-stage operation surface** without inventing a duplicate journal or another success authority.

1. **Unified activity timeline:** queued checks, downloads, verification, extraction, scanning, approval, Android handoff, confirmation, failed/cancelled/unknown and completed entries from the existing durable R03/R05 records. Preserve exact source/listing/attempt identity and correct ownership for concurrent jobs.
2. **State-correct controls:** `Review`, `Resume`, `Retry`, `Cancel`, `Details`, `Open` only when allowed; present a consistent path back to the Android-mandated approval UI when supported, and an actionable `unknown` outcome when confirmation is unavailable.
3. **Persistent/recoverable UX:** maintain correct activity across page navigation, process death and restart; surface no fabricated success from external installer intents, callbacks or timeouts. Reconcile against independent installed package/signature/version evidence.
4. **Progress/error semantics:** accurate verified bytes and totals, indeterminate status for unknown totals, clear per-app failures (signature, ABI, SDK, split, expired artifact, rate-limit), notifications linked to the exact operation, and no UI showing 100% until verified completion.
5. **Acceptance:** unit, widget, interruption/restart, concurrency, cancellation, approval-denial, stale receipt, cross-listing attribution, external handoff and notification-route tests; legacy R02 recovery hook retained after R05 journal recovery. Hosted API36 real-install/negative/archive paths stay required. Real-device notification/approval behavior and Android OS background limits separately recorded.

**R07 exit:** one consolidated native overlay for the complete milestone, with updated existing test contracts rather than historical HF/Pxx scaffolding. All required hosted workflows must pass at the resulting exact HEAD; device and release evidence are not inferred.

## F. Delivery order, review and safety

1. **Finish R05 PR #25 review:** ensure exact-HEAD tests and source semantics still match. Resolve legitimate comments; when review-complete, mark ready for review, then consider a separately approved merge in dependency order. A green hosted check is not review approval, physical release permission or authorization to auto-merge.
2. **Implement R06** on a clean named source-bound feature worktree. Review current upstream app-details implementation first; preserve existing Material 3 Expressive and backend behavior. Deliver all R06 functionality/tests/docs in one consolidated native Devtool overlay.
3. **Implement R07** building on R03 download state, R05 install receipts and the R06 details UX, with a single Activity Center state authority and no duplicated operations. Keep R06 and R07 independently reviewable milestones; run cross-milestone integration tests.
4. **Then R08–R09**, version/source regression fixes, discovery and compatible picker; **R10**, settings/accessibility and locales; **R11**, integrations/history; **R12**, complete device signing/security/release acceptance. R01/R02 security and physical-device gaps stay visible throughout; release-critical gaps cannot be postponed silently.
5. **Stack cleanup:** PRs #1–#25 are still open. Plan reviewed bottom-up consolidation without resetting, rebasing, force-pushing, auto-merging or overwriting unrelated work. Retain exact provenance, user worktree safety and GitHub dependency review.

**Native delivery contract current at this snapshot:** Devtool source `Mikeyphw/devtool` `main` HEAD `cd10dbe2e6dfa85ce30e12fa869a8c0313a78d40`; committed `LAUNCHER_CONTRACT_VERSION = '3.2.0'`. Discover/verify latest compatible v3.1+ again **at each delivery**, rather than treating this snapshot as a future runtime pin. Native launcher must source-bind origin, target branch, HEAD/tree, preimage blobs and payload digest; use native validation, atomic commit and durable session; no manual file patch/copy as a substitute. Use native terminal (`DEVTOOL_EXECUTION_PRESENTATION=plain`, `DEVTOOL_JOB_UI=plain`, `DEVTOOL_TEXTUAL_APPLY_HOST=0`, `DEVTOOL_TEXTUAL_EXECUTION_HOST=0`) and `--no-clipboard` as documented in the current contract; honor `NO_COLOR`, `CLICOLOR=0`, `TERM=dumb`. A committed package must be resumed using session commands instead of reapplied. Validate actual PR HEAD and hosted checks, and never equate skipped tests with PASS. If the runtime contract evolves, re-evaluate, not silently repin immutable packages.

**Historical specification handling:** Section G below reproduces the entire 10 November plan, including its then-current implementation assumptions and launcher example, for traceability. The dated sections above take precedence for current status and delivery behavior. No original acceptance criteria are waived. This document is a roadmap status update, **not** evidence of a new native apply, CI run, device install, signing operation or merge.

## G. Complete original R00–R12 specification (10 November 2026; preserved verbatim)

---

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
