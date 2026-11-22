# ObtainX OPT04 — hosted Gradle task-output cache + measured CI cost

OPT04 does **not** reuse the Flutter/Dart integration-test APK between RT02, RT02B,
and RT02C. Those tests use distinct Dart targets and compile-time fixture
parameters; cross-target reuse without refactoring and independent acceptance
would be unsafe. RT02C already executes seven cases in one Flutter session.

Five hosted jobs now enable Gradle's local task-output build cache using
`GRADLE_OPTS: -Dorg.gradle.caching=true` at the job level: full Flutter, API36,
RT02, RT02B and RT02C. The full Flutter Java setup now also uses the same
pinned `setup-java` Gradle cache configuration as the four Android jobs.

Gradle itself determines whether task outputs have compatible inputs and whether
a task is cacheable. Its dependency cache in `~/.gradle/caches` is already
restored by `setup-java`. The new flag does **not** skip tests, build APKs on a
local Termux device, alter production logic or enable a remote execution cache.

The exact PR head, API36 emulator, Flutter version, Java version, app package
verification, signing proof, negative installs, real Android package-state and
source-bound receipts remain mandatory. These controls are protected by the
optimization source contract and negative mutation tests.

## Measuring actual performance

Baseline successful PR #11 commit:
`768fcaf8dbb4f10ecfe711c8f3a26b97b0ae4265`.

- Flutter debug APK Gradle build: 330.9 seconds
- API36 standalone debug APK Gradle build: 154.9 seconds
- API36 OPT03 cache: miss (Flutter job saved its cache later in same matrix)
- RT02 split second Flutter invocation: about 53 seconds
- RT02B downgrade second Flutter invocation: about 39 seconds
- RT02C: 1 Flutter launch, 7 archive cases

The matching OPT04 source-bound benchmark ZIP contains a read-only baseline
collector, an optional explicit GitHub Actions API36 rerun to exercise an OPT03
cache hit, and a comparison report. A cache hit or speedup is **not** claimed by
this source overlay. Compare the same scenario and runner-minute breakdowns
on a qualifying hosted commit after the change; keep rejected cases and full
runtime qualification checks intact.

All six workflows must pass on the new commit before OPT04 is hosted-qualified.
No local Gradle, merge, force-push, release, or physical-device qualification.
