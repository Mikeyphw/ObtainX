#!/usr/bin/env python3
"""Fail-closed source contract for original R02 local import and preserved gates.

This proves source wiring only. Actual Android UI selection and exact byte
verification must be demonstrated in a hosted disposable runtime separately.
"""
from __future__ import annotations
import argparse
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BRIDGE='packages/obtainx_native_evidence/android/src/main/kotlin/dev/imranr/obtainium/R02LocalArchiveBridge.kt'
PLUGIN='packages/obtainx_native_evidence/android/src/main/kotlin/dev/imranr/obtainium/ObtainxNativeEvidencePlugin.kt'
SIGNATURES='packages/obtainx_native_evidence/android/src/main/kotlin/dev/imranr/obtainium/R09ApkSignatures.kt'
PLUGIN_PUB='packages/obtainx_native_evidence/pubspec.yaml'
PLUGIN_BUILD='packages/obtainx_native_evidence/android/build.gradle.kts'
APP_PUB='pubspec.yaml'
APP_LOCK='pubspec.lock'
MAIN='android/app/src/main/kotlin/dev/imranr/obtainium/MainActivity.kt'
SERVICE='lib/services/r02_local_archive_import.dart'
POLICY='lib/services/r02_local_archive_policy.dart'
PAGE='lib/pages/import_export.dart'
TEST='test/r02_local_archive_policy_test.dart'
DOC='docs/R02_FINAL_COMPLETION_ACCEPTANCE.md'
R00='.github/workflows/obtainx-r00-contracts.yml'
FLUTTER='.github/workflows/obtainx-r00-flutter.yml'
RT02C='.github/workflows/obtainx-r02-rt02c.yml'
PATHS=(BRIDGE,MAIN,PLUGIN,SIGNATURES,PLUGIN_PUB,PLUGIN_BUILD,APP_PUB,APP_LOCK,SERVICE,POLICY,PAGE,TEST,DOC,R00,FLUTTER,RT02C)

def inspect(root:Path=ROOT)->list[str]:
    issues=[];d={}
    for p in PATHS:
        f=root/p
        if not f.is_file() or f.is_symlink() or f.stat().st_size>500_000:
            issues.append('missing/symlinked/oversized '+p);d[p]=''
        else:d[p]=f.read_text(encoding='utf8')
    def check(ok,message):
        if not ok: issues.append(message)
    k=d[BRIDGE]; service=d[SERVICE]; page=d[PAGE]; p=d[POLICY]
    for anchor in ('"copy" ->', '"cancel" ->', '"dispose" ->', '"sourceEvidence" ->',
                   '"verifyInstalled" ->', 'FLAG_GRANT_', '64 * 1024', '1024L * 1024L * 1024L',
                   'MessageDigest.getInstance("SHA-256")', 'target.fd.sync()',
                   'uri.scheme == "content"', 'R02_COPY_REFUSED',
                   'PackageManager.GET_SIGNING_CERTIFICATES',
                   'val hashes = installedPaths.map { path ->', 'digestFile(apk)',
                   'observed["hashes"] == hashes.sorted()', 'observed["signers"] == signers.sorted()',
                   'after.lastUpdateTime != observed.lastUpdateTime',
                   'sources.mapIndexed { index, path ->', 'R09ApkManifest.inspect(file)', 'R09ApkSignatures.current(file, Build.VERSION.SDK_INT)', 'expectedSigners == signers', 'digestFile(file) == before', 'afterSigners != signers'):
        if anchor=='FLAG_GRANT_':
            continue  # Existing SAF picker controls its read grants.
        check(anchor in k,'Android SAF streaming/evidence contract missing '+anchor)
    check(d[PLUGIN].count('R02LocalArchiveBridge(binding.applicationContext, binding.binaryMessenger)')==1 and
          'R02LocalArchiveBridge(' not in d[MAIN] and 'R09ApkInspectionBridge(' not in d[MAIN] and
          'onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding)' in d[PLUGIN] and
          'local?.close()' in d[PLUGIN] and 'inspection?.close()' in d[PLUGIN] and
          'pluginClass: ObtainxNativeEvidencePlugin' in d[PLUGIN_PUB] and
          'path: packages/obtainx_native_evidence' in d[APP_PUB] and
          'path: packages/obtainx_native_evidence' in d[APP_LOCK],
          'native evidence channels must register exactly once per Flutter engine')
    check(k.count('getPackageInfo(target, flags)')==2 and
          'PackageManager.GET_SIGNING_CERTIFICATES' in k and 'afterSigners != signers' in k,
          'installed signing-certificate flags must be enforced')
    for anchor in ('ApkVerifier.Builder(file)', '.setMinCheckedPlatformVersion(sdk)',
                   '.setMaxCheckedPlatformVersion(sdk)', '.build().verify()',
                   'require(result.isVerified)', 'result.signerCertificates.map', 'certs.isNotEmpty()'):
        check(anchor in d[SIGNATURES], 'cryptographic member signer evidence missing '+anchor)
    check('implementation("com.android.tools.build:apksig:9.3.1")' in d[PLUGIN_BUILD],
          'pinned APK signature verifier dependency missing')
    check(k.count('reply.success(verified)')==1 and 'getOrDefault(false)' in k,
          'native verification cannot default to true')
    check('sudo ' not in service and 'Process.run(' not in service,
          'manual import must not execute privileged operations')
    for anchor in ("saf.openDocument(","persistablePermission: false",
                   "mimeType: '*/*'", "_localBridge.invokeMethod<Map<dynamic, dynamic>>('copy'",
                   'sha256FileOffIsolate(path)', 'extractZipOffIsolate(',
                   'extractTarballOffIsolate(', 'resolveInstallBundlePlan(',
                   'validateP05DeviceProfile(', 'verifyP05SdkEnvelope(',
                   'verifyR02LocalTarget(', 'targets.length != 1',
                   'showDialog<bool>(', 'barrierDismissible: false',
                   'provider.beginInstallPreparation(', 'provider.cancelInstallPreparation(',
                   'provider.installApk(', 'provider.installApkDir(',
                   "'sourceEvidence'", "'verifyInstalled'",
                   'r02LocalObservedInstallConfirmed(', 'provider.endInstallPreparation(',
                   "_localBridge.invokeMethod<bool>('dispose'", 'wasCancelled'):
        check(anchor in service,'production UI/import/reconciliation guard missing '+anchor)
    check('getDocumentContent(' not in service, 'Dart must not buffer unbounded APK bytes')
    check('InstallResult.success()' not in service and 'RootInstaller(' not in service,
          'manual import must not manufacture privileged success')
    check('Install local APK / archive' in page and 'showR02LocalArchiveImport(context, appsProvider)' in page,
          'user-facing ImportExport action missing')
    for anchor in ('r02LocalArchiveMaximumBytes', 'verifyR02LocalTarget(',
                   'sourceListingCount != 1', 'requestedVersion < installedVersion',
                   'byteEvidenceQualified', 'installerReportedSuccess && byteEvidenceQualified'):
        check(anchor in p,'local import adversarial decision missing '+anchor)
    check('throwsFormatException' in d[TEST] and 'R02 no success from callback' in d[TEST],
          'mandatory Dart local import negative tests missing')
    check('python3 -B scripts/ci/r02_final_contract.py --check' in d[R00],
          'R00 source contract invocation missing')
    check('flutter test --no-pub test/r02_local_archive_policy_test.dart' in d[FLUTTER],
          'R00 Flutter contract test invocation missing')
    for anchor in ('r02f_p04b_p03_hosted.py run --out',
                   'r02f_p04_backends_hosted.py run --out',
                   'r02f_p05_hosted.py run --out',
                   'r02f_p05_hosted.py verify --out'):
        check(anchor in d[RT02C], 'inherited signed-fixture Android gate missing '+anchor)
    for anchor in ('R02', 'SAF', 'NOT_QUALIFIED', 'Shizuku',
                   'Dhizuku', 'OBB', 'ARM64', 'historical'):
        check(anchor.lower() in d[DOC].lower(), 'acceptance ledger missing '+anchor)
    return issues

def main():
    # The precommit launcher and R00 Actions both invoke this source contract
    # with --check. Accept the flag explicitly instead of refusing argparse.
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='Validate the exact R02 source contract (read-only)')
    parser.parse_args()
    errs=inspect()
    for e in errs:print('OX_R02_FINAL_SOURCE_REFUSED '+e)
    if errs:return 2
    print('OX_R02_FINAL_SOURCE_CONTRACT_PASS; REAL_SAF_UI_AND_PHYSICAL_RUNTIME_NOT_QUALIFIED')
    return 0
if __name__=='__main__':raise SystemExit(main())
