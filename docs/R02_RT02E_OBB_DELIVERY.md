# RT02E — Verified OBB delivery and hosted Gradle-cache optimization

**Parent:** PR #8 exact `678d5a20807674c26325d29a64b27df6ec13384b`.

## Scope

- Android 11+ (API 30+) continues to refuse direct APK-only installation of bundles requiring OBB files, *before* calling any APK installer. This remains unsupported until a verified backend-specific storage route is qualified. External original-container handoff is retained.
- For lower API devices, OBB storage permission is requested *before* starting an APK install. Denial refuses instead of installing the APK alone.
- After a confirmed APK install, each OBB is copied to a temporary sibling. A streaming SHA-256 check of the source and copied bytes, exact byte length, symlink checks, cancellation checks before commit and atomic rename prevent false positive copy receipts. Existing destination files are kept in a rollback backup until a replacement succeeds. Errors propagate rather than being silently logged as success.
- An optional cancellation callback is exercised in tests; application-wide user cancellation UX and activity-level persistence remain R05/R07 work. A completed APK install is **not rolled back** by a later OBB-copy error. Batch OBB replacement is **not transactionally atomic across power loss**.
- The RT02C hosted API36 job enables pinned setup-java Gradle dependency caching. Earlier PR #8 run `43051035546` spent around 460s in initial Gradle startup/build versus roughly 28s across seven Android scenarios. Caching is a prospective optimization; **no new runtime reduction is claimed until a comparable next run measures it**. Cache misses/runner contention may dominate.

## Qualification

New hosted unit tests check copied bytes, digests, overwrite, cancellation before/after copying, invalid names, size limits and symlink refusals. Python mutation tests ensure that security and CI gates remain mandatory. All inherited RT02C API36 runs must continue to pass on the exact source SHA.

**Not qualified:** real OBB write success on devices; interrupted APK/OBB rollback; API30+ scoped-storage OBB; Shizuku/Dhizuku/external installer success; physical device; release. No merges/releases. Build and tests are evidence, not a production qualification claim.
