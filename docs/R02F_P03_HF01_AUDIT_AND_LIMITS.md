# R02F P03 HF01 — promise-by-promise audit

| Promise | Earlier P03 flaw | HF01 repair | Qualification |
|---|---|---|---|
| Actual ObtainX UI cancel | Mounted only a synthetic Cancel button and called `StockInstaller` directly | Hosted test mounts the real `AppPage`, calls `AppsProvider.installApk`, taps that page's production Cancel | CI pending; NOT_QUALIFIED |
| Cancel at Android approval | Owned native session bridge existed, but no real app-page/provider traversal | Same native session, P03 stage/commit/cancel through provider with explicit pending-approval assertion | CI pending; NOT_QUALIFIED |
| Original base+split bytes | Native `fingerprint()` could store empty or unreadable hashes | Reject absent hashes on installed baselines, require matching base/splits, recheck after abandon | Native source guarded; initial single-base v1 runtime pending; original-split coverage NOT_QUALIFIED |
| Route changes | Prior test never navigated | Integration test pushes a route and returns, asserts original owner and AppPage | CI pending |
| Restart callback races | `orphanStatus` was saved but not read | Matching orphan callbacks are consumed, terminal remains UNKNOWN pending independent package reconciliation | Source fixed; process-death acceptance NOT_QUALIFIED |
| Unknown post-commit result | Stock unknown misclassified as third-party handoff with a 60s spinner | Separate native recovery marker; user-visible unverified warning, no false cancel or success | Source fixed; native runtime pending |
| Multiple listings | Registry keyed on listing, but API code still uses package id in parts | Exact owner registered/guarded; no substitution in installOptions; mutation test | Underlying multi-source end-to-end runtime NOT_QUALIFIED |
| Failure/backoff | No timed failure/timeout integration acceptance | No auto-retry/false success introduced; UNKNOWN stays unverified | NOT_QUALIFIED |
| 7/7 RT02C, 2/2 P02, R02G, six workflows | Only prior SHA had green evidence | Original jobs unchanged; P03 appended to same emulator, new exact-SHA gated receipt | Prior SHA qualified; HF01 CI pending |
| Launcher/rollback | Synthetic tests did not run mutation suite | Self-test runs all 15 mutation tests, precise file allowlist, staged diff/source test; precommit rollback | Local self-test can be run |

**Safety:** no local Gradle/Flutter builds, no ADB operations on personal devices, no unauthorized merges/releases, no `git reset`, no `git clean`, no force-push. Use a new branch on PR #11. Explicit PASS requires all six hosted runs and new P03 Android receipt at exact new SHA.
