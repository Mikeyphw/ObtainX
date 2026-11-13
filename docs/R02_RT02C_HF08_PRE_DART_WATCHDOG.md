# ObtainX RT02C HF08 — Bounded pre-Dart startup and phase-aware CI watchdog

Source-pinned against PR #11 commit `75f8eaa303c4589402374c27fb70158eae4e2179`. This fixes an observed **RT02C APKS test-runner installation startup stall** (first scenario stuck at `TEST_APK_INSTALL`, zero approvals for >35 minutes). The captured logs do not establish why Flutter/ADB stalled; the patch **detects and refuses** this class of hang rather than claiming to repair Android itself.

- One Flutter process, all seven RT02C runtime scenarios and RT02F/R02G follow-on gates remain mandatory.
- 20 minute total RT02C Flutter session limit, 12 minute Gradle phase limit, 6 minute pre-Dart APK installation phase limit, and 7 minute active per-case limit.
- Only real phase or verified boundary changes reset the phase clock; repeated periodic progress messages do not.
- A refusal prints a bounded category, case, phase, elapsed seconds, runner-seen flag and bounded host probe count. The private Flutter log and device data remain unuploaded.
- CI job timeout reduced from 125 minutes to 40 minutes, leaving a final safety net for emulator/host stalls.
- Adds source-contract mutation tests and offline synthetic timing regression tests.

The test suite does **not** prove real Android success. The former run was cancelled; all six hosted checks (or the required exact-SHA lanes) must qualify the new commit. No release/merge or automatic behavior bypass is authorized.

## Termux/Zsh

```sh
REPO="$HOME/Code/ObtainX"
ZIP=/storage/emulated/0/Download/ObtainX_RT02C_HF08_PRE_DART_WATCHDOG.zip
python3 "$ZIP" --self-test &&
python3 "$ZIP" --check --repo "$REPO" &&
python3 "$ZIP" --repo "$REPO" &&
gh pr checks 11 -R Mikeyphw/ObtainX --watch
```

Pass `--check` for a read-only source/remote preflight. `--self-test` does not access a Git repository. The Python ZIP launcher uses only `$TMPDIR` for transient work, runs `git diff --check`, all repository Python unit tests, and source integrity checks before commit/push. No local Gradle, rebase, force-push, automatic merge, or release.
