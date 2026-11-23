# ObtainX R02F P04 — Shizuku/Dhizuku backend availability and consented testing

**NOT_QUALIFIED** for real Shizuku/Dhizuku installation. This stage checks the
availability and permission boundary; it never provisions device owner or
Shizuku services and never installs with privileged identity. A read-only
backend check is not a receipt proving a signed APK installed successfully.

P04B P03 adversarial external handoffs must run after the P02 signed positive
case and before the backend probe. The default hosted API36 Google APIs emulator
must have neither `moe.shizuku.privileged.api` nor `com.rosan.dhizuku` installed.
The real, existing plugin's `checkShizukuPluginPermission` (serialized across
both backends) must report `services_not_found` for each, and two exact Flutter
markers must be observed. If either service appears unexpectedly, CI refuses.

The classifier treats Shizuku `granted_adb` and `granted_root` and Dhizuku
`granted_owner` as **authorized but not qualified**. Wrong-backend grants,
unsupported versions, unavailable binder, denied permission, unknown or empty
results cannot authorize a disposable test. No silent fallback from one mode to
the other is accepted. A status/permission check cannot request installation.

An optional `authorized-read-only` probe requires: a pre-provisioned disposable
hosted API36 emulator, exact source and signed fixture SHA pins, a preinstalled
selected service, an explicit **user-initiated** consent acknowledgement, and
an actual native plugin permission result for that selected backend. This
reads only backend availability; it does not install, elevate, activate device
owner, or modify a physical device. It is not automatically dispatched by the
ordinary CI. Do not run it against a personal phone, or invent a successful
result when a service is absent. If granted, a separate future signed-APK
installation acceptance still needs independent Android package/version/bytes
proof and rollback evidence before claiming Shizuku or Dhizuku qualification.

R02F P05: OBB, ABI, density, locale and Android compatibility plus physical
read-only preflight. P06: user-facing import and cancellation. PR integration:
review open stacked PRs before any merge. R03: resumable downloads. R04:
GitHub Actions artifact source. R05: persistent installation receipts. R06:
app-details UX. R07: Activity Center. R08: source reliability. R09:
compatible picker. R10: settings/accessibility. R11: integrations/history.
R12: full physical, signing and release qualification. No automatic merge.
