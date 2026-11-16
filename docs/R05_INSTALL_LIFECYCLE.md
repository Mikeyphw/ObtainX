# R05 transactional install lifecycle and verifiable receipts

R05 introduces source-bound, per-attempt durable operation records and a recovery surface for Android installs. It retains R02 install/precommit/security checks, R03 byte verification, and R04 GitHub Actions provenance. It never equates an installer intent launch or a generic broadcast with a verified release. A successful install claim requires an independent installed package and exact source-bound pending-release check (and expected version code where available); local archive import retains its stronger signed-byte check. Build provenance, downloaded file digest, APK archive certificate and installed signer are **distinct** facts; missing evidence remains `null`.

## Transaction and recovery model

Each private application-support receipt records listing/package ID, source **host only** (never a token-bearing URL), optional workflow/branch/run/attempt/commit/artifact identity, downloaded SHA-256, archived signer when available, selected **basenames** (not absolute paths), installer backend, Android result, status and verified UTC timestamp. Revisions are monotonic. States: `pending`, `awaitingApproval`, `handedOff`, `confirmed`, `failed`, `cancelled`, `unknown`. An unobserved completion, 60-second external timeout, or process death never becomes `confirmed`. Persisted pending starts become `unknown` on restart; existing awaiting approval remains visible and recoverable. Private staging is same-directory atomic rename; partial temp entries remain intact but are not promoted into authoritative receipts.

**Confirmation authority:** matched `InstallReleaseSnapshot` and independent Android package/version reconciliation, plus installed signer fingerprint when retrievable. Installer callbacks and external third-party bridges are insufficient alone. A late verified broadcast may resolve a previous `unknown`. Exact stage transitions and source ID checks prevent unrelated package listings from confirming each other. A locally imported APK with no source snapshot is not silently granted source-bound confirmation by this journal; the separate R02 local signed-byte gate remains authoritative for import messaging.

**Approvals and UX:** Settings → Updates → **Install activity and approvals** displays receipts, pending/unknown outcomes and a review/retry action. Optional extra approval defaults to **off**; when enabled, background work refuses to silently approve and retains a reviewable operation. Platform-mandated Android prompts are never suppressed. An Android session may remain awaiting confirmation while another activity is displayed. R07 will expand this basic recovery view into the full Activity Center.

**Background operations:** The stock Android background-workaround futures now attach an explicit error-owning observer. Package-install polling timeout records `unknown` and does not synthesize success. Any retry must be explicit. No automatic file deletion or blanket repo cleanup is introduced by R05.

## CI and acceptance

- R05 state-model, persistence, restart, concurrent starts, malformed evidence and journal symlink negatives run under hosted Flutter workflow.
- Existing R00 Python contract CI covers R05 source/CI wiring and mutation negatives.
- All four API36 Android workflow path filters include R05 source, UI and tests.
- The existing six required CI workflow policy remains intact; R05 changes the *base branch* to the R04 feature branch, for a stacked R05 PR.
- No legacy HFxx/Pxx checks are deleted; existing security and regression coverage remains.

The new source and tests are not a physical Android end-to-end acceptance certificate. `release_qualification=NOT_QUALIFIED`; physical device, all external installer targets, UI large-text/accessibility and release signing require independent proof. Devtool conditional-trigger registrar may still block native CI qualification despite green hosted runs; never work around that by removing path or type filters.
