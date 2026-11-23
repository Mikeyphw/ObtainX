#!/usr/bin/env python3
"""R05 source and regression wiring, exact file evidence, no device claims.

This does not replace Dart tests or the native Devtool overlay validator.
"""
from __future__ import annotations
import argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
FILES={
    'lib/services/r05_operation_receipt.dart':(
        'enum R05InstallStage {','pending, awaitingApproval, handedOff, confirmed, failed, cancelled, unknown',
        'R05AndroidEvidence','exactAttemptMatches','evidence.packageName != packageId',
        'expectedVersionCode != null','verifiedUtc','if (time.isBefore(updatedUtc))',
        'downloadSha256','archiveSignerSha256','installedSignerSha256',
        'sourceHost','workflow','runAttempt','artifactId','fileNames'),
    'lib/services/r05_operation_journal.dart':(
        'getApplicationSupportDirectory()', 'r05-install-operations',
        'followLinks: false','maxReceiptBytes','maxOperations',
        'writeAsBytes(bytes, flush: true)', 'stage.rename(target.path)',
        'recoverInterruptedOnce()', 'settleIfOpen(', 'uniqueUnresolved(', 'R05InstallStage.unknown',
        'R05InstallStage.awaitingApproval','Random.secure()'),
    'lib/widgets/r05_install_activity_page.dart':(
        'class R05InstallActivityPage','class R05ExtraApprovalTile',
        'R05OperationJournal.instance.list()', 'reconcileR05OperationReceipts()',
        'Review / retry','not independently verified','r05ExtraApprovalPreference'),
    'lib/providers/apps_provider_install.dart':(
        '_r05BeginAttempt(', 'sha256FileOffIsolate(primary.path)',
        '_r05AdditionalApproval(', '_r05CloseAttempt(',
        'Future<void> _r05TrackBackgroundInstall(', '_r05MarkUnknownIfStillPending(',
        'R05InstallStage.handedOff','R05InstallStage.confirmed',
        'p04PendingMatchesInstalledPackage(',
        'R05OperationJournal.instance.uniqueUnresolved(listingKey)',
        'expectedRelease != null', 'result.isCancelled',
        'result.isAlreadyInstalled','result.isHandedOff','result.isError'),
    'lib/services/r02_local_archive_import.dart':(
        'if (confirmed)', 'r02LocalObservedInstallConfirmed(',
        'R05OperationJournal.instance.uniqueUnresolved(listing)',
        'R05InstallStage.confirmed', 'exactAttemptMatches: true'),
    'lib/providers/apps_provider_lifecycle.dart':(
        'R05OperationJournal.instance.recoverInterruptedOnce()',),
    'lib/pages/settings.dart':(
        'R05InstallActivityPage()', 'R05ExtraApprovalTile()',
        "ValueKey('r05-install-activity')"),
    'test/r05_operation_receipt_test.dart':(
        'installer success and timer are never independent Android proof',
        'pending, approval, handoff and unknown are distinct durable states',
        'reject malformed JSON'),
    'test/r05_operation_journal_test.dart':(
        'parallel starts are serialized', 'startup converts interrupted pending into unknown',
        'approval remains recoverable', 'symlink are refused'),
    '.github/workflows/obtainx-r00-contracts.yml':(
        'scripts/ci/r05_contract.py --check',),
    '.github/workflows/obtainx-r00-flutter.yml':(
        'flutter test --no-pub test/r05_operation_receipt_test.dart',
        'flutter test --no-pub test/r05_operation_journal_test.dart'),
    'scripts/ci/obtainx_ci_policy.py':(
        "'lib/services/r05_*'", "'test/r05_*'",
        "'scripts/ci/r05_*'", "'lib/widgets/r05_*'"),
    'config/delivery-required-ci.json':(
        'feature/obtainx-r04-actions-source-native-20261115',),
    'docs/R05_INSTALL_LIFECYCLE.md':(
        'R05 transactional install lifecycle','Android','NOT_QUALIFIED',
        'durable','approval','R07'),
}
ANDROID_CI=(
    '.github/workflows/obtainx-r02-api36.yml',
    '.github/workflows/obtainx-r02-rt02.yml',
    '.github/workflows/obtainx-r02-rt02b.yml',
    '.github/workflows/obtainx-r02-rt02c.yml',
)

def verify(root:Path=ROOT)->int:
    errors=[]
    for path, markers in FILES.items():
        try: content=(root/path).read_text(encoding='utf8')
        except (OSError, UnicodeError) as e:
            errors.append(f'{path}: missing/unreadable ({type(e).__name__})');continue
        for marker in markers:
            if marker not in content:errors.append(f'{path}: marker missing: {marker}')
    for path in ANDROID_CI:
        try: content=(root/path).read_text(encoding='utf8')
        except (OSError, UnicodeError):errors.append(f'{path}: missing/unreadable');continue
        for marker in ("- 'lib/services/r05_*'", "- 'lib/widgets/r05_*'", "- 'test/r05_*'"):
            if marker not in content:errors.append(f'{path}: R05 risk path missing {marker}')
    try:
        code=(root/'lib/providers/apps_provider_install.dart').read_text(encoding='utf8')
        first=code.index('final r05 = await _r05BeginAttempt(')
        native=code.index('result = await activeInstaller.installApk(')
        if first>native:errors.append('R05 intent must be durable before native handoff')
        if 'unawaited(\n            installApk(' in code or 'unawaited(\n            installApkDir(' in code:
            errors.append('Raw untracked background install future survives')
    except (OSError,ValueError): errors.append('Cannot prove R05 pre-handoff journal ordering')
    if errors:
        for e in errors:print('OX_R05_CONTRACT_REFUSED '+e)
        return 1
    print('OX_R05_CONTRACT_PASS: expected source and CI wiring; device NOT_QUALIFIED')
    return 0

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--root',type=Path,default=ROOT)
    opt=parser.parse_args()
    raise SystemExit(verify(opt.root))
