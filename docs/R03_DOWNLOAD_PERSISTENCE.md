# ObtainX R03 — download recovery, integrity and operation persistence

This is the **single consolidated original R03 milestone**. Original phases R00–R12 are preserved; no Pxx subdivisions are created.

## Implementation

- Production `downloadFile` / `downloadFileWithRetry` delegates through `R03DownloadEngine`; existing app source headers, HTTP/redirect client policy, cancellation tokens, notifications, installer stages, asset format inference and private Android storage remain in place.
- Atomic private JSON receipt per source identity (request URL, destination, secret header **fingerprint**, never raw credential/header/query), with job ID, final redirect origin, strong ETag / Last-Modified, total bytes, SHA-256-block-validated .part offsets, and locally verified final file hash.
- Restart from app re-invocation validates existing complete-file digest, or every previously committed 1MiB block of the partial, truncating any uncommitted tail. No duplicate output and no length-only cache acceptance.
- Resume requires matching final origin and stable validator. Sends Range and If-Range; exact Content-Range starting offset, end, total length and encoding are required. Changed ETags, ignored 200 responses, malformed 206, changed origin and unsupported 416 safely restart from zero instead of combining entities.
- For unknown lengths, a clean HTTP response EOF and exact local SHA-256 are required, not an assumed Content-Length. Known expected SHA256 inputs (when R04 supplies them) fail closed.
- Transient socket/timeout/408/429/5xx retry with jittered exponential backoff and Retry-After; authentication failures, invalid entities and user cancellation are not retried.
- Download stage enum defines queued, checking, downloading, downloaded, verifying, extracting, ready, awaitingApproval, installing, confirming, completed, paused, cancelled, retrying, failed. R03 persists download lifecycle; installation confirmation/approval orchestration remains under R02 and future R05/R07.
- Existing native foreground progress notifications remain intact; user cancellation interrupts retry waits, and Android service ownership is unchanged.

## Hosted qualification

The Python source/mutation contract and deterministic `HttpServer` unit tests are routed through exact-HEAD six-workflow hosted CI, including the full Flutter analyzer and Android suites. A local synthetic source test cannot qualify Dart compilation.

## Security/acceptance boundary

- `finalDigest` is a hash of local bytes, **not trusted upstream provenance**. External digest and attestation assurance remains **R04**. Source URLs and authentication headers are not saved in the journal; re-lookup is required on restart.
- A killed foreground operation remains safely checkpointed but isn't automatically restarted by the OS. The existing source request must be reissued; automatic queue replay, persistent Activity Center UX, and system-managed pause/resume belong to R07 and are **NOT_QUALIFIED** here.
- Real device network sleep, cellular handover, background process death, native foreground notification controls, production redirect-auth combinations, API36 Android integration and every install backend require actual hosted/physical observations. They are **NOT_QUALIFIED** by offline tests or an unpushed overlay.
- No local Gradle, auto-merge, release signing, root access, device writes, forced Git history, or privileged install tests are executed by the overlay.
