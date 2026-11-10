# ObtainX Fork — R00 Bootstrap

The canonical roadmap is [`docs/ROADMAP.md`](ROADMAP.md). The R00 bootstrap creates a **real GitHub fork**, checks the fork and upstream identities, clones it, establishes a reproducible source baseline, and pushes a dedicated feature branch. On a brand-new fork, it also fast-forwards `main` to the validated R00 commit, immediately replacing inherited release/write workflows, and attempts to protect `main` with PR and CI requirements. It never copies release signing credentials from another fork.

## Run on Termux / Zsh

Requirements: Python 3.10+, Git, GitHub CLI `gh` authenticated as the owner, and preferably `rich` (`python3 -m pip install rich`). No shell installer is needed.

```sh
python3 /storage/emulated/0/Download/ObtainX_R00_Fork_Bootstrap.zip --self-test
python3 /storage/emulated/0/Download/ObtainX_R00_Fork_Bootstrap.zip --audit-only
python3 /storage/emulated/0/Download/ObtainX_R00_Fork_Bootstrap.zip
```

Default fork: `Mikeyphw/ObtainX`, from `bikram-agarwal/ObtainX`. Default local directory: `~/Code/ObtainX`. Default branch: `feature/obtainx-r00-bootstrap`.

The source tip is pinned to `aea18592413de992e813bd063cb9ad453259582b`. If upstream moves, explicitly acknowledge this with `--accept-current-source` to use the **then-current** upstream commit and record it in `docs/R00_BASELINE.json`. This does not allow the fork to silently diverge from upstream or modify an existing dirty repository.

Options:

- `--no-push`: create local commits without pushing the bootstrap branch.
- `--branch-only`: leave R00 on a feature branch even for a new fork; the inherited main workflows remain until the PR is merged.
- `--integrate-main`: on an existing recognized fork, non-force fast-forward `main` to the R00 baseline.
- `--open-pr`: create a draft PR against the fork's own `main` if the bootstrap is not already integrated.
- `--skip-remote-permissions`: skip the GitHub API operation setting the default Actions token to read-only; the new workflows themselves still have `contents: read`.
- `--skip-main-protection`: skip the default attempt to protect main on newly created forks.
- `--require-main-protection`: refuse a completed setup if GitHub denies protection (e.g., plan or permissions). By default such failures are explicitly reported as `MAIN_PROTECTION_PENDING` without claiming protection passed.
- `--owner`, `--repo`, `--source`, `--path`, `--branch`: override defaults. The owner must match the account authenticated in `gh`.
- `--dry-run`: display intended actions but do not create a fork or change files.
- `--self-test`: validate the embedded archive and its local tests without GitHub/network access.

The bootstrap refuses to modify an existing local checkout with uncommitted changes, unexpected remotes, a different source lineage, diverged `main`, or a non-bootstrap working branch. No force push, hard reset, credential import, or release publishing is used. Only the initial, preflight-validated R00 commit may fast-forward `main`, and the operation refuses divergent commits.

## What R00 changes

- Adds the canonical roadmap, baseline source receipt and test inventory, and development/security documentation.
- Adds `scripts/ci/r00_source_contract.py`, its regression tests, and read-only hosted CI.
- Replaces inherited workflow automation (`build.yml`, `release.yml`, `pr-base-guard.yml`, `format-issue-body.yml`, and the old translation validator). All remain recoverable from the upstream Git history; no release job is enabled in R00.
- Ignores release signing keys and local secret configuration.
- Establishes `origin` as the personal fork and `upstream` as `bikram-agarwal/ObtainX`.

**R00 does not compile, sign or publish an APK on the local Android device.** The hosted Flutter CI runs analysis, Flutter tests, and a debug APK build. The existing golden-test failures may initially cause a red CI result; that is evidence to investigate, not something to disable or claim passed. Runtime qualification and release signing remain gated by later phases.

After bootstrap:

```sh
cd ~/Code/ObtainX
git remote -v
git status --short --branch
gh pr list --repo Mikeyphw/ObtainX
```

To sync upstream in a future phase, use a separate branch and an explicit merge/rebase with test-contract updates. Never copy wizzwuz signing files, and never assume passing hosted compilation proves Android runtime compatibility.
