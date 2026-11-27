# FINAL-AUDIT-01 — credential and device evidence repair

The exact base is merged main `fdc3bf615fb138aed65d0a1aeaeb1a4732391718`. Scope: F01, F02 and F11 from the 139-promise historical audit. This is a source repair, not release authorization.

## Linked metadata (F01)

The production changelog planner rejects non-HTTPS, userinfo and credential-bearing query destinations before reading credentials. GitLab release and file API requests use exact configured origin and exact tracked project; other same-origin GitLab URLs are public-only. GitHub release conversion binds the exact canonical tracked repository. Request headers are obtained only after planning; `HttpService.request` performs the exact URI directly with verified TLS and redirects disabled. No query injection, borrowed token or configured proxy rewrite. Navigation refuses unsafe links. A provider refusal is not bypassed. Private GitLab file links with ambiguous branch names may require explicit supported API metadata; no speculative token replay.

## Diagnostic integrity (F02)

Persisted log records, app-managed debug output, error dialogs, error notifications and exported diagnostics use bounded redaction and typed exception categories; raw server reason phrases and exception stacks are not logged. URLs (including opaque path values), credential-labelled records and recognizable token formats are withheld. Legacy rows retain timestamps, IDs and levels but text is withheld on read: they are not proven sanitized. Existing clear-log control can remove rows; this does not guarantee flash-storage erasure or remove existing external copies. Native crash import records category only. Android's own default crash handler, external apps, third-party SDK logs and malicious unlabeled opaque strings are outside the app-owned log-redaction guarantee. Never put secrets into diagnostic inputs. No live credential was used during testing.

## Device evidence (F11)

The R12 reviewer accepts only device-matrix v2 with the complete fixed lane/check vocabulary, exact signed candidate metadata, explicit consent, valid UTC timestamps, matching backend/API/ABI, distinct content hashes and actual per-check structured observations with receipt/log attachments. Positive installation requires observed target package identity; relevant refusal/cancellation requires identical before/after state and no owned session. The verifier refuses ambiguous or duplicate evidence; it does not authenticate human observation or authorize release. Device review and exact-main release qualification remain external.

## Verification and next work

Run the source contract suite and hosted Flutter tests including `test/final_audit_01_security_test.dart` and device evidence mutation tests. Verify all six decisive hosted jobs for the exact new head. Physical tests must use authorized disposable fixtures and synthetic secrets. Review the new protected-main candidate only after all outstanding audit blockers are repaired. FINAL-AUDIT-02: lifecycle and scalability; FINAL-AUDIT-03: provider and artifact trust; FINAL-AUDIT-04: acceptance and release. The remaining historical gaps are not claimed complete.
