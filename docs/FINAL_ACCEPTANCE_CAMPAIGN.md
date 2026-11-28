# FINAL-ACCEPTANCE-01

The `scripts/ci/final_acceptance_campaign.py` command is a read-only evidence collector. Use a clean checkout of the exact committed overlay and a private, owned mode-0700 receipt directory. Pass `--head` and `--receipt` before the action. The receipt is mode 0600 and exclusive. The Ordenator exposes the same route and prints only a bounded receipt digest/status.

| Action | Evidence | Does not prove |
|---|---|---|
| plan | Registered source factories, eleven device lanes and original promise count | Provider support or qualification |
| observe-ci | Current main and exact-tree full hosted proofs | Signed release or physical acceptance |
| provider | Exact GitHub Actions workflow/run/attempt/head/artifact, optional real ZIP SHA-256 | APK signature or app-side source behavior |
| device-profile | Explicitly consented ADB read-only SDK/ABI/locale/density | Runtime installation or other device lanes |
| readiness | Current CI, signing environment policy, tracked source scan | Protected-main dispatch, reproducibility, licenses, signing |
| review | Actual signed APK signature/payload, both unsigned builder records, fresh CI, eleven-lane candidate-bound evidence | Human independent review or publication authorization |
| audit | All 139 historical rows and current digest-bound reference inventory | A new per-promise semantic verdict |

`provider` requires an explicit repository, branch, workflow, run ID, run attempt, provider commit SHA and artifact ID. `--download-verify` streams a bounded temporary archive and checks its digest and unchanged selection; no file is installed. All other registered providers still require authorized live app-side fixture observations, including private authentication, rate-limit refusal and artifact binding. Do not infer those from a host probe.

`device-profile` requires `--serial` and `--ack I_AUTHORIZE_READ_ONLY_DEVICE_PROBE`. `review` requires `--candidate`, `--expected-cert`, `--matrix`, `--evidence-dir`. A candidate review rejects inconsistent CI provenance regardless of reuse mode, stale CI, inconsistent unsigned records, changed replica advisories, or signed payload/identity drift. It cannot reconstruct unsigned APKs from the signed artifact, so the independent builder receipts remain evidence of hosted execution rather than local reproduction.

The historical inventory preserves historical findings without promotion. R05-P04 and P05 now have concrete reviewed source references: `r02_local_archive_import.dart` awaits both installer routes and settles preparation in `finally`; `R05_INSTALL_LIFECYCLE.md` records separate optional approval and platform confirmation. This establishes a source subset, not end-to-end proof of every caller and backend. UX-03, GOV-06 and GOV-07 still need independent route/upstream/license review. Cryptographic attestation verification and RuStore live support remain unqualified. All 139 rows require new semantic review; the inventory does not mark them completed.

No local Gradle, signing, release dispatch, install or publication occurs in these actions. Use the protected R12 workflow only under independent explicit authorization; no credential values should appear in receipts or logs.

Optional detailed review inputs: `review --provider-matrix FILE --provider-evidence-dir DIR` checks exact coverage of every registered factory, candidate APK binding, distinct machine-evidence files for discovery, metadata, digest binding, authentication and rate-limit refusal or reviewed non-applicability. PASS-shaped records are labeled ready for independent review only. `audit --review-file FILE --evidence-dir DIR` checks all historical IDs, source/tree, historical audit digest, current reference hashes, reviewer, timestamp and distinct evidence files. Neither command grants release authorization. Unavailable provider capabilities remain explicit rather than presumed accepted.
