#!/usr/bin/env python3
"""Source-only R07 Activity Center contract; native/Flutter/device proof is separate."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
TOKENS={
 'lib/services/r07_activity_catalog.dart':(
   'class R07ActivityCatalog', 'R05OperationJournal.instance',
   'R03DownloadRecord.fromJson(decoded)', 'r07UniqueListingForFile(',
   'r07AllowedActions(', 'R07ActivityAction', 'transfer.finalDigest',
   'followLinks: false', 'maxDownloadReceiptBytes',
   'Never guess', 'sourceFingerprint != transfer.jobId'),
 'lib/widgets/r07_activity_center_page.dart':(
   'class R07ActivityCenterPage', 'WidgetsBindingObserver',
   'reconcileR05OperationReceipts()', 'provider.cancelDownload(key)',
   'provider.cancelInstallPreparation(key)',
   'provider.downloadAndInstallLatestApps(', 'packageManager.openApp(',
   'operationId', 'R07ActivityAction.review', 'R07ActivityAction.resume',
   'R07ActivityAction.retry', 'R07ActivityAction.cancel',
   'R07ActivityAction.details', 'R07ActivityAction.open',
   'LinearProgressIndicator', 'Activity receipts could not be read',
   'RefreshIndicator', 'Review', 'Stage'),
 'lib/widgets/r05_install_activity_page.dart':('class R05ExtraApprovalTile',),
 'lib/pages/home.dart':('R07ActivityCenterPage()', 'activityCenter'),
 'lib/pages/settings.dart':("ValueKey('r07-activity-center')", 'R05ExtraApprovalTile()', 'R07ActivityCenterPage()'),
 'lib/pages/app.dart':("ValueKey('r06-install-history')", 'R07ActivityCenterPage(', 'packageId: app.app.id'),
 'lib/providers/apps_provider_install.dart':('notifyR07Attention(', '_r05BeginAttempt(', 'reconcileR05OperationReceipts()'),
 'lib/providers/notifications_provider.dart':('r07AttemptNotificationId(', "payload: 'r07:$attemptId'", "payload.startsWith('r07:')", "R07ActivityCenterPage(operationId: operationId)"),
 'test/r07_activity_center_test.dart':(
   'interruption becomes unknown', 'concurrent attempts have distinct durable IDs',
   'approval remains reviewable after restart', 'handoff does not provide Open',
   'two overlapping listing IDs prevent cross-source attribution',
   'only digest-finalized download can display 100%',
   'symlink or oversized journal is refused',
   'opening Activity Center does not convert a live pending install',
   'await tester.runAsync(', 'await initial!.timeout(',
   'super.load(trackedPackages: trackedPackages)',
   'Activity Center renders only the requested durable attempt'),
 'docs/R07_ACTIVITY_CENTER.md':('R07', 'R03', 'R05', 'R02', 'CI24', 'NOT_QUALIFIED'),
 '.github/workflows/obtainx-r00-contracts.yml':('scripts/ci/r07_contract.py --check',),
 '.github/workflows/obtainx-r00-flutter.yml':('flutter test --no-pub test/r07_activity_center_test.dart',),
 'scripts/ci/obtainx_ci_policy.py':("'lib/widgets/r07_*'", "'lib/services/r07_*'", "'test/r07_*'", "'scripts/ci/r07_*'"),
}
R02_WORKFLOWS=(
 '.github/workflows/obtainx-r02-api36.yml',
 '.github/workflows/obtainx-r02-rt02.yml',
 '.github/workflows/obtainx-r02-rt02b.yml',
 '.github/workflows/obtainx-r02-rt02c.yml')


def verify(root:Path=ROOT)->list[str]:
 errors=[]
 for path,marks in TOKENS.items():
  try: source=(root/path).read_text(encoding='utf-8')
  except (OSError, UnicodeError):
   errors.append(f'{path}: unreadable'); continue
  for mark in marks:
   if mark not in source:errors.append(f'{path}: missing {mark!r}')
 for path in R02_WORKFLOWS:
  try: content=(root/path).read_text(encoding='utf-8')
  except (OSError,UnicodeError):errors.append(f'{path}: missing');continue
  if ('    paths:' in content or '    paths-ignore:' in content or 'scripts/ci/obtainx_ci_policy.py plan --head' not in content):
   errors.append(f'{path}: risk path routing missing')
 try:
  config=json.loads((root/'docs/R00_BASELINE.json').read_text(encoding='utf-8'))
  if config['roadmap_sha256']!=hashlib.sha256((root/'docs/ROADMAP.md').read_bytes()).hexdigest():
   errors.append('R00 roadmap identity digest mismatch')
  policy=json.loads((root/'config/delivery-required-ci.json').read_text(encoding='utf-8'))
  if policy['base_branch']!='main' or len(policy['required_workflows'])!=6:
   errors.append('R07 base or hosted CI workflow identity drift')
 except (KeyError,ValueError,OSError,TypeError) as ex:
  errors.append('R07 required baseline/CI JSON unreadable: '+str(ex))
 try:
  files=(root/'lib/widgets/r05_install_activity_page.dart').read_text(encoding='utf-8')
  if 'class R05InstallActivityPage' in files:errors.append('old R05 screen still competes with R07')
  catalog=(root/'lib/services/r07_activity_catalog.dart').read_text(encoding='utf-8')
  if 'await _installJournal.recoverInterruptedOnce()' in catalog:
   errors.append('read-only R07 projection must not restart-recover in-flight R05 operations')
 except OSError:pass
 return errors

if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--check',action='store_true'); ap.add_argument('--root',type=Path,default=ROOT)
 args=ap.parse_args(); errors=verify(args.root)
 for e in errors:print('OX_R07_CONTRACT_REFUSED '+e,flush=True)
 if errors:raise SystemExit(1)
 print('OX_R07_SOURCE_CONTRACT_PASS; NATIVE/CI24/DEVICE/RELEASE NOT_QUALIFIED',flush=True)
