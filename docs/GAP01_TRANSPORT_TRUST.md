# GAP-01 — transport and artifact trust

## G01

The shared `HttpService` validates HTTP(S) destinations without userinfo, compares scheme/host/effective port on every redirect, rejects HTTPS downgrades and cross-origin non-read requests, and never restores source headers or cookies once a chain leaves its initial origin. Byte-range controls remain for resumable downloads; the special R04 signed-storage allowlist remains stricter. Metadata, partial hash, ETag and size probes use the same streamed transport. GitHub credentials are restricted to the source API or explicit configured proxy/API path. VirusTotal authenticated GET and multipart upload do not auto-follow redirects; upload URLs are limited to HTTPS www.virustotal.com. Explicit insecure TLS permission cannot cross origins. HTML intermediate pages and asset headers are scoped to the tracked origin; GitLab no longer adds private tokens to URLs, CoolAPK tokens stay on its API origin, Itch.io cookie-bearing requests stay on the original origin, and direct authenticated API calls do not auto-follow redirects. No claim of historical credential disclosure.

## G02

API lookup is discovery, not signature verification. Malformed or missing evidence, a wrong digest format, and HTTP errors do not become trust. Legacy `verified` and boolean `true` are downgraded on read. Legacy claims are downgraded to unknown/error, not even to presence. The UI shows newly discovered presence as unverified. Existing settings and user consent survive missing credentials; both native handoff sites and verification-skip routes independently enforce the policy. New explanatory labels use the documented English fallback where untranslated. A configured Enforce policy blocks installation independently of PAT validation or any stored status. Audit mode reports only presence/absence/error. A cryptographic Sigstore verifier with trust roots, timestamp and signer/workflow policy is not bundled; the explicit fail-closed alternative is used. No valid signed fixture can be promoted by this implementation; positive-looking bundles remain unverified. GitHub documents cryptographic verification at https://docs.github.com/en/rest/repos/attestations and https://cli.github.com/manual/gh_attestation_verify.

Local source-contract tests and source-bound hosted Flutter/Android gates are separate. Live authenticated provider, external verifier integration, device and release acceptance are not claimed.

## HF02 — deterministic store-discovery regression

The widget test previously invoked the actual APKMirror network path under Flutter's fake clock. The new shared transport has a real 30-second timeout, which remained pending after widget disposal. The details page now accepts its store-lookup dependency, defaulting to the existing production service. The regression asserts an exact-listing lookup occurs once and both pending and negative answers produce no unconfirmed chip; the separate GAP-01 HTTP fixtures continue to exercise the real secure transport. Neither the network timeout nor production trust policy is changed.

## HF03 — hosted Android runner readiness

After HF02 all full Flutter tests passed. The RT02C P03 runner instead failed while Flutter was replacing its debug APK: package path is not an atomic UID reservation. The shared host helper polls only the fixed debug package in Android user 0, treats clean absent responses and exact No UID as pending, and refuses all other failures. Existing bounded pollers use the same helper; the real RT02C authenticated case start requires eligibility. P03 retains successful eligibility, real UI cancellation and independent unchanged signed bytes, and stops its own Flutter process group on failure. No application-source security policy or device receipt is weakened. The local tests reproduce the exact exit/error race and fatal alternatives; real hosted device acceptance remains mandatory.

## FINAL-AUDIT-03 — approved F03 limit

The operator explicitly approved retaining fail-closed attestation enforcement until a supported cryptographic verifier exists. No stored receipt, provider presence, certificate digest or API response becomes cryptographic verification. See `FINAL_AUDIT_03_TRUST.md`.
