# R09-F01 — Discovery, app lists and safe artifact selection

Source candidate built from exact PR #30 HF13 `e3960a6779f9139c72810748c1001198d82e8f94`. HF13's six required workflows passed; RT02C run 45528116315 confirmed five real archive updates, two archive rejections and independent Android package-state checks. This is prior-source evidence, not R09 acceptance.

| Promise | Production path and scope |
|---|---|
| R09-P01 | Existing view sheet, folder settings and badges retained; three presets use existing switches. Existing source listings retain identity. |
| R09-P02 | Visible Check for updates on listed scope, distinct Update all (review) with installable existing updates only, existing bulk selection. Keyboard/remote standard buttons. |
| R09-P03 | Case-insensitive token search across name, package ID, source host/type and category; saved smart-folder criteria round trip. URL query/userinfo not searched. Compact/Standard/Detailed presets. Grid optional and deferred. |
| R09-P04 | Opt-in package grouping retains all listing keys and existing row actions; installed observation only from OS package info. Bulk review refuses automatic conflicting listings; selecting one replaces the competing selection; provider refuses conflicting package batches. |
| R09-P05 | Existing GitHub Actions history bound to current form repository, branch/workflow/run/attempt/commit/artifact, size, expiry, advertised digest and selection recheck. Existing APK picker displays filename ABI hints, archive/split role, known size, tracked package/source version and pending actual APK metadata. Known incompatible standalone choices disabled; real manifest/ABI/signer verification remains downstream. Advertised ZIP SHA is not APK signer proof. |
| R09-P06 | Scope summary distinguishes not checked, only track, attention, no source, actionable update and current-at-last-check; empty filter results show matching scope state or normal clear-filter path. |

R09-A01 requires actual hosted Dart tests and physical-device/keyboard/accessibility checks. Python source guards and native commit are not proof of runtime behavior. Unknown APK metadata is never presented as inspected metadata. No local Gradle. CI24 is not applicable. Full scope must be requalified on the resulting exact source.

R09-P05 is partial at the milestone level: a pre-download manifest-backed comparison of all candidate APKs (actual package IDs, version codes, signer, ABI and split membership) is not implemented by this overlay. R09-F02 remains the verified artifact metadata/inspection work, not an assertion that a filename is proof. R09-F01 owns the completed source-list, safe selector, exact history and known-metadata presentation changes.
