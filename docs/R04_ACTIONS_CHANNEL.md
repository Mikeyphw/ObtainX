# ObtainX R04 — GitHub Actions source channel

This is the **original R04 roadmap milestone**, not a detached HF/Pxx roadmap.
R03 source prerequisite: PR #23 HEAD `1874e6a09888adcba0f12a2bbc55788c7d5c76ba`, 6/6 same-HEAD GitHub workflows PASS.

## Source-native behavior

- GitHub app source settings expose separate **Releases**, **Prereleases**, and **Actions** channels. Existing imported apps without a selected channel keep their prior `includePrereleases` behavior, avoiding migration surprises.
- Actions selection uses the canonical repository API and asks for the default branch from GitHub unless the user explicitly supplies another branch. Optional exact workflow ID/name, exact successful run ID, and an artifact-name RegEx are available.
- Workflow enumeration, successful run enumeration and per-run artifacts are paginated in bounded 100-item pages, with malformed JSON, authentication failures, throttling, missing metadata and incomplete inventories refused rather than silently truncated.
- Automatic selection considers only **completed successful** runs with valid workflow ID, branch, run attempt, 40-character commit SHA, numeric run ID and timestamp. This is run selection, **not** signed APK/build attestation.
- Candidate GitHub artifact ZIPs must be nonexpired, below the R01 archive budget, named like an Android candidate, and unambiguous. Logs, reports, coverage, source bundles, invalid filenames and multiple candidates without a narrower user filter are refused.
- `archive_download_url` is intentionally NOT trusted from response JSON. The app constructs `/repos/{owner}/{repo}/actions/artifacts/{id}/zip` from validated numeric IDs, then feeds that archive into the existing R03 download → R01 bounded archive extraction → R02 Android installer flow. The source uses the existing per-source credentials, HTTP redirect controls and install approval/malware gates. No root, Device Owner, Shizuku or Dhizuku privilege is granted.
- Evidence shown to users distinguishes workflow ID, run ID, attempt, branch, head SHA, artifact ID, archive expiration and optional GitHub **ZIP digest** from **APK signing certificate**, **APK SHA-256**, and **build attestation**. Those are separate trust claims.

## Qualification and acceptance limits

The newly added Actions source and mock API regression suite need exact-SHA hosted Flutter compilation and all six CI workflows before being called hosted-qualified. On-device GitHub API/redirect/auth downloads, ZIP digest enforcement, contained APK signing verification, workflow history browser UX, process death, expired archives under live API conditions, and physical installation still require independent source-bound observations. **NOT_QUALIFIED** for physical install, signed release or full R04 runtime acceptance.

R04 discovery and package planning must not be described as R05 transactional install completion. Existing R02 install confirmation remains authoritative; future R05 supplies persistent cross-stage operation receipts. The mock suite is not proof of archive digest or signing verification at runtime.

## Execution contract

Use only the source-pinned R04 consolidated launcher on the exact R03 feature branch SHA. No local Gradle, unattended APK installation, auto-merge, force push, signing secrets, personal device changes or privilege bypass. The launcher validates base branch/PR, source blob IDs, transactionally applies, runs Python source/mutation regressions, and can push/watch all six exact-SHA hosted workflows with their native output.

## R04 P02 ZIP SHA-256 enforcement

GitHub Actions candidates now require a valid GitHub artifact ZIP SHA-256 digest
at check time (missing or malformed digests fail closed). The selected receipt
stores the repository URL, canonical artifact URL/name, numeric workflow/run/
attempt/artifact IDs, commit SHA and expected ZIP digest. Before bounded R01
extraction or R02 install approval, ObtainX streams and hashes the actual ZIP
bytes. A mismatch deletes the downloaded cached ZIP and refuses installation;
channel changes invalidate stale Actions receipts. Releases/prereleases retain
their existing verification behavior. A ZIP hash is NOT APK signing or build
attestation, and this patch does not silently grant either status.

Hosted Flutter qualification and all six exact-HEAD Android/contract workflows
must pass again at the new source SHA. Live authenticated redirects, device
install, history-browser UI and physical release remain **NOT_QUALIFIED**.

## R04 consolidated completion overlay — no further P0X stages

The remainder of R04 is delivered together: manual Actions history browsing from
the Run ID field, workflow/branch/run/attempt/commit/artifact-ID selection,
fail-closed changed-revision detection, GitHub API JSON media negotiation and
API-version headers, HTTPS-only signed-storage redirect allowlist, and strict
cross-origin PAT/cookie stripping. GitHub Actions API metadata and private repo
credentials are never forwarded to third-party artifact storage hosts. A
successful workflow still does not prove an APK signature.

History shows unsuccessful/in-progress runs for inspection but never makes
their artifacts selectable. Expired, unverifiable, ambiguous and non-Android
artifacts remain excluded from the installable picker. A manual selection binds
to the exact workflow, branch, run ID, attempt, source SHA and artifact ID.
If a run is retried/replaced or an archive changes, a subsequent update check
refuses it instead of silently installing a different revision.

The existing R04 P02 SHA-256 gate hashes downloaded ZIP bytes BEFORE the R01
bounded extraction or R02 installation pipeline. It does not verify contained
APK signing, trusted release attestation or deployed package ownership; those
remain governed by the existing R01/R02 independent checks.

**Read-only live API acceptance:** `python3 -B scripts/ci/r04_live_acceptance.py
--repo OWNER/REPO --workflow WORKFLOW_ID --branch BRANCH --run-id RUN_ID
--artifact-id ARTIFACT_ID --download-verify`. This opt-in command uses `gh
api` with the user's connected token and streams a transient artifact ZIP
for exact SHA-256 comparison; never writes to Android, changes GitHub, or
promotes an APK as signed. Store a JSON metadata receipt only with an explicit
`--receipt PATH`. Failure, permission denial, expiry, ambiguity and digest
mismatch fail closed.

**Qualification truth:** Full source and Flutter/Android hosted workflows must
run at the *new* exact commit. Real private artifact redirects, live API
behaviors and physical Android installation are **NOT_QUALIFIED** until an
independent live/device acceptance receipt is produced. No signed release or
R05 transactional install state is claimed.

A persisted Actions source receipt also binds the artifact's `expiresAt`.
Before extraction, expired cached ZIPs are refused even when the ZIP digest
still matches, including after app process death/restart.


### Consolidated R04 reviewed delivery

Manual history selection updates both the saved source mode and the visible
source-channel dropdown. A published archive digest alone is not a verified
byte stream; the SHA-256 is checked on transfer and again before extraction.

Live acceptance supports `--run-attempt` and `--head-sha` to require an exact
revision. Its `--download-verify` path requests a 302 from the authenticated
canonical API endpoint and separately fetches the signed HTTPS object-store
URL **without** the GitHub PAT or any cookie. Redirects to other origins are
refused and ZIP bytes are streamed into an automatically deleted temporary
file. Optional private-repository receipts are written with mode 0600 and do
not claim APK signing or physical-device qualification.

The launcher also runs a real rollback regression using a synthetic local Git
repository. Any pre-commit failure restores source bytes, executable mode,
staged index and a clean worktree; a failed rollback is never reported as PASS.

R04 is hosted-qualified only after all six exact-SHA workflows pass on this
new commit. This single overlay contains the complete R04 implementation;
physical-device installation, live private-token acceptance, and a signed
release remain separate acceptance evidence, **NOT_QUALIFIED** beforehand.
