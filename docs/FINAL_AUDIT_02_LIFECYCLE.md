# FINAL-AUDIT-02 — lifecycle and scalability

## F04 — operations

The Activity Center offers Pause only to the current live transfer owner after at least one durable verified block, a known total length and an accepted entity validator. Pause is distinct from cancellation, failure and completion. On interruption the engine rereads the checkpoint, verifies all committed block digests, truncates trailing bytes, persists paused state and reports the transfer ID. Resume still requires the exact listing, release, URL, validator, expected range and byte identity. No automatic install follows pause. The SAF archive operation is created after document selection and before private copy, with unknown package/channel until validated manifest inspection and explicit exact listing selection. Binding is one-time. Android installation confirmation remains the R05 receipt's responsibility.

## F05 — artifact integrity and bounds

GitHub release and Actions assets, F-Droid repository XML SHA-256 and explicitly labeled Uptodown SHA-256 rows supply asset byte digests where present. Codeberg and IzzyOnDroid reuse their respective source paths. Exact name, URL, source, override and version bind evidence; malformed or conflicting advertised SHA-256 refuses use. Other providers without a consumed, reliably scoped digest remain unverified by advertised checksum, not falsely attested. The expected digest is part of the release/cache identity and reaches the final byte verifier through review, public and normal download paths. It does not establish signer trust or cryptographic attestation.

The existing four-GiB transfer maximum, 1 MiB committed blocks and 45-second idle timeout remain. Add a two-hour transfer deadline and storage admission/periodic checks with 16 MiB reserve. Archive work retains 1 GiB compressed input, 1.5 GiB expanded output, per-entry/count/path limits, bounded decoder structures, five-minute worker deadline and sampled 192 MiB process RSS growth refusal. Native SAF copy keeps 64 KiB streaming and checks private free space and elapsed time. These are cooperative/admission bounds, not an Android kernel memory quota; blocked provider reads and measured peak/forced-death behavior still require actual device testing. No release readiness claim.

## F09 — history

SQLite migration is additive. Explicit reviewed retention compacts at most 256 eligible terminal timelines per pass, preserving the operation row and first/final event. Unknown, paused, linked, unresolved and referenced parent records are protected. Exact revision and event-content fingerprint must match the preview. Exports page the timeline by keyset and stream validated R05/R03 receipts into a private exclusive staging file, cap output at 256 MiB and publish only after completion. Failed or interrupted exports remove staging. Each journal retains its own authority; the export is historical, not a cross-journal atomic snapshot or installation proof. Old history scans remain linear; device-scale performance and memory profiling remain external acceptance.

## Qualification

Retain every required workflow and previous assertion. New runtime regressions cover explicit pause and resume with expected digest, missing total, capacity refusal, exact asset binding and stale evidence, local archive identity and retention, multi-page scoped export and failure cleanup. Native Flutter/Dart and Android/device qualification must establish behavior of the candidate; source-only checks are not substitutes. No release authorization.
