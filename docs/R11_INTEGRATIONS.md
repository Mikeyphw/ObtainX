# R11 — Integrations, policy and history

Source-bound consolidated overlay. Hosted Flutter and Android, actual Tasker/App Manager installations, device constraints and release acceptance remain separate gates.

## F01: external navigation
`obtainium://open?id=com.example.app` and Android `android.intent.action.SHOW_APP_INFO` with `android.intent.extra.PACKAGE_NAME` navigate to an already tracked package only. Multiple sources require an explicit listing choice; no fallback by package after the selection changes. Opening a details page does not check for updates or install. Incoming SHOW_APP_INFO extras are discarded; ordinary external links remain untrusted.

## F02: opt-in Tasker integration
Enable automation locally in Settings. In Tasker, use Send Intent with action `android.intent.action.VIEW`, target Activity, the installed ObtainX package, and data `obtainium://automation?id=com.example.app&action=check&request=my_request_1`. Allowed actions: `check`, `download`, `state`, `receipt`. Every request requires foreground confirmation; no background exported command service, no caller identity claim, no install action. Exact selected release and listing are revalidated before transfer; cancellation and opt-out prevent dispatch. Check returns a fresh discovery comparison without persistence; download uses the existing R03 transfer/cache engine and never installs. Read state reflects the library observation, not independent current package verification. Receipt is historical. Results are broadcast only to `net.dinglisch.android.taskerm` with action `dev.bikram.obtainx.AUTOMATION_RESULT`, string extras `request` (correlation) and `result` (redacted JSON). A request ID is not an authentication secret. The user must explicitly consent to sending results to Tasker, not to the arbitrary app which sent the URI. No guaranteed broadcast delivery or unattended automation. Missing Tasker, malformed requests and ambiguous selection fail closed. Local opt-in is never exported or imported.

## F03: App Manager
The details button and existing app-info route use explicit package-scoped `SHOW_APP_INFO` to `io.github.muntashirakon.AppManager`. Tracker/signature inspection is performed by App Manager's own details UI; ObtainX does not assert tracker findings or certificate safety. App Manager's supported APK installation handoff continues through the existing explicit external-installer policy and user approval; no new install permission. Missing App Manager reports unavailable or falls back to system app details for the app-info route.

## F04: history and receipts
New R03 and R05 records bind the exact listing/package and source channel fingerprint; older records retain unknown channel, never retroactively acquire verified ownership. Filter the existing Activity Center by listing/channel. Export an allowlisted historical JSON snapshot through the existing share mechanism: listing hashes, package, state, channel hash, bounded receipt metadata; no filenames, raw source URLs, bearer tokens, private branch, path or exception. Prune only explicitly selected old terminal install receipts after confirmation. Interrupted/unknown/external handoffs and R03 resume evidence are not removed by history retention. History is not proof of present safety or an install authorization.

## F05: automatic policies
Existing background worker honors Wi-Fi and charging constraints for automatic work, local quiet hours (including midnight wrap; equal start/end disables quiet hours), and a transactional SQLite minimum interval claim. Android may defer/deny background work; no exact-alarm or battery-exemption escalation. Manual user requests bypass the quiet/rate gate only; install restrictions remain authoritative. Recheck conditions before automatic install. Existing background-update enablement and update interval still apply.

## Acceptance matrix
- Strict URI parsing, exact package/listing identity, changed listing and duplicate routing; cold/warm SHOW_APP_INFO, malicious extras, Activity lifecycle.
- Opt-in/default-off/import refusal, foreground confirmation/cancellation, package-scoped Tasker response, source check/read/download/receipt; no install and no caller token disclosure.
- Installed and absent App Manager; exact package and tracker/signature UI; approved external APK handoff and negative installer paths.
- R03/R05 journal migration and channel separation, historical export redaction, terminal-only retention, interrupted recovery.
- Quiet-hour boundaries, clock rollback, persistent rate claim, Wi-Fi/charging and Android background restrictions; existing six workflows plus physical-device verification.

## R11-HF01
Eight strict analyzer block-style violations repaired without changing external consent, exact-listing guards, retention rules or parser rejection. Full hosted qualification of the repaired source remains pending.
