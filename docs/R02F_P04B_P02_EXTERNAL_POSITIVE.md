# ObtainX P04B P02 — disposable external installer positive-path acceptance

Stacked on P04B P01 (external ACTION_VIEW receiver decline). Adds an independent
signed disposable positive target. An Android PackageInstaller session and
**actual user approval in a hosted API 36 emulator** must precede external update
qualification; a Dart bridge boolean or package-change broadcast never suffice.

Expected strict sequence: source-bound signed v1 baseline; signed disposable
installer APK installed; system REQUEST_INSTALL_PACKAGES app-op authorized on
**emulator only**; target receives the SHA-bound signed v2 APK via production
`installApkViaThirdParty`; target writes a PackageInstaller session, launches the
system approval UI, receives `STATUS_SUCCESS`; fresh PackageManager package
version and installed base APK SHA256 independently equal the signed v2 fixture.
Independent offline verifier must rehash retained v1/v2/target signed APKs and
private log; raw logs and keys cannot be uploaded. Any unexpected UI, missing
approval, stale package, changed SHA, or interrupted session is a refusal.

**NOT_QUALIFIED** until hosted API 36 workflow actually passes. **P04B P03**
will cover delayed broadcasts, spoof/mismatched versions and parallel handoffs.
Shizuku, Dhizuku and physical devices remain unqualified, as do release and
self-update. No device-owner, root, shell-privileged install or personal package
operation is authorized. This overlay does not merge or publish a release.
