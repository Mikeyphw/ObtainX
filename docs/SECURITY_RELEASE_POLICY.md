# ObtainX fork — Security and Release Policy (R00)

**Status: NO PUBLIC RELEASE QUALIFIED.** A passing source-contract workflow or Flutter debug build does not authorize an APK release.

1. No signing keystores, private keys, passwords, bearer tokens or `.env` files may be tracked. The `wizzwuz/ObtainX` signing keystore and its hardcoded fallback password are specifically prohibited. Do not reuse its signing identity.
2. The inherited workflows capable of building or tagging releases, modifying pull-request targets, or writing issue bodies are removed from the fork's active workflow directory at R00. They are still present in upstream history for audit.
3. The bootstrap's hosted jobs use a **read-only** GitHub token and pinned actions. No release upload, tag creation, dependency mutation, or auto-merge occurs.
4. Android downloads/installs require exact artifact identity, defensible SHA-256 verification, package/signature verification, correct split selection, and Android-confirmed outcomes before they may be called qualified. These are future roadmap phases, **not done by R00**.
5. When signing is introduced at R12, use an isolated signing identity with protected GitHub secrets/environment controls. Enforce trusted release provenance and verify certificates/artifacts. Never echo private material to logs.
6. Every source/CI/test contract must be compared to actual implementation and updated or removed when stale. Do not weaken checks to obtain green status.
7. R00 CI is not a substitute for Flutter feature tests, Android 16 runtime qualification, or a security review.

See [`docs/ROADMAP.md`](ROADMAP.md) for acceptance criteria and deferred phase gates.
