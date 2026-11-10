# R01 HF04 — Stale HF02 test fixture recovery

- Fork: `Mikeyphw/ObtainX` PR #1; expected head `eba157a48aa3b9b99417a483670750625c0cddf6`.
- Hosted run 42854406591: **823 passed, one skipped, two golden tests failed**. All archive tests and static analysis passed. Golden-review artifact was blocked by an outdated reporter parser.
- HF03's strict parser was correct, but its local whole-suite preflight failed in `test_r01_hf02_contract.HF02.test_exact_golden_only_evidence` because that older test fabricated the incomplete summary `2 failed`, not a real Flutter final summary. Consequently the HF03 ZIP was refused before any push.
- This hotfix changes the **test fixture**, not the triage acceptance rules. The repaired positive cases use a complete Flutter final summary (`01:19 +823 ~1 -2: Some tests failed.`) and a complete prose summary; a new negative test explicitly rejects the old `2 failed` fragment.
- Original HF03 classifier keeps requiring exactly two named app-row failures, six explicit mismatch diagnostics, no unrelated failures, and an authoritative final test report.
- Run every existing Python mutation and contract test on the complete source-pinned Git worktree **before any commit**; do not weaken a production assertion or source validation. Then push only the three source/test corrections and this audit document to the existing R01 PR branch, without force push.
- The checksum-verified, embedded HF02 reviewer may then await hosted CI, retrieve the six new golden images **only after strict triage**, perform pixel/dimension review, commit an explicit provenance receipt, and require a fresh green full-suite hosted check.
- No automatic merge, signing, release, Android runtime qualification, or test skipping is allowed. If any new failures occur, stop and report the exact job/run evidence rather than asserting success.
