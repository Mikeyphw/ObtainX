# R02G P01 — Real Android incompatible-SDK refusal

This work closes ONE specific coverage gap identified in the restored R02 roadmap:
**real Android 16 / API36 PackageManager rejection of an ephemeral, signed APK
that declares Android 37 as its minimum SDK.** It is **not full R02** acceptance.

## Runtime requirements

- The existing seven RT02C archive cases and RT02F P02's two abandoned Android
  sessions must pass first in the **same disposable API36 emulator**.
- Before emulator boot, generate a new test-only APK with package
  `dev.bikram.obtainx.rt02g.future_sdk`, version 1, minSdkVersion 37, from
  API36 SDK tools and an **ephemeral keystore**; attest its manifest via `aapt`,
  its signature via `apksigner`, and its SHA-256 in the exact-source inventory.
- Prove both the new fixture and the old RT02 package are absent before the
  attempt. `adb install -t -r` must exit nonzero with exactly the real Android
  `INSTALL_FAILED_OLDER_SDK` package error. The new package must remain absent
  and the old RT02 package must remain absent afterwards.
- The independent verifier binds the receipt to the GitHub commit, CI run,
  signed APK digest, exact Android rejection category, device SDK, and explicitly
  FALSE physical-device, UI cancellation, OBB, external backend, user-facing
  import, publication and release claims.
- An unexpected install fails closed and is cleaned up; do not suppress Android
  failures, mock the installer, upload the temporary signing key, or produce a
  release artifact. Existing mandatory source/Flutter/Android checks remain.

## R02 completion ledger (not all complete)

| R02 case | Evidence and remaining scope |
| --- | --- |
| Standalone & base+split install | Existing RT02 real API36 Android proof, keep |
| Five archive types | Existing RT02C real API36 seven-case session, keep |
| Signature mismatch & downgrade | Existing RT02B real API36 rejection, keep |
| Android session abandonment | Existing RT02F P02 real API36 proof, keep; app-UI cancellation is distinct |
| Incompatible newer SDK | **R02G P01 new real API36 negative test**; needs hosted acceptance |
| ABI/language/density split selection | RT02D planner source and Flutter tests; full on-device multi-variant matrix still pending |
| OBB | RT02E transactional copy tests; Android 11+ stock OBB refusal; real supported-device and third-party handoff not qualified |
| External/Shizuku/Dhizuku | RT02F unverified external handoff contract; independent package-state/permission/device acceptance pending |
| Genuine user-facing import and UI cancellation | Not qualified by hosted fixture-only tests |
| Physical devices and release | Not qualified; no automatic merges or releases |

Future R02G parts should close these gaps in evidence-backed slices, preserving
upstream-compatible behavior and the existing RT02 gates. R03 persisted/resumable
download operations begin only after a transparent R02 scope decision. No
physical-device or release status is implied by a green source-only check.
