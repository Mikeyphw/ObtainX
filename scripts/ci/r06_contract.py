#!/usr/bin/env python3
"""R06 presentation, exact package history and source-bound CI regression checks.

Source/mutation contract only. No emulator, physical-device or release claim.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
INTEGRATION_BASE='main'
FILES=(
  'lib/pages/app.dart',
  'lib/components/r06_version_tile.dart',
  'lib/widgets/r05_install_activity_page.dart',
  'test/r06_app_details_test.dart',
  'test/app_page_version_actions_test.dart',
  'docs/ROADMAP.md',
  'docs/R00_BASELINE.json',
  'docs/R05_INSTALL_LIFECYCLE.md',
  'docs/R06_APP_DETAILS.md',
  'config/delivery-required-ci.json',
  'scripts/ci/r04_completion_contract.py',
  'scripts/ci/r05_contract.py',
  'scripts/ci/obtainx_ci_policy.py',
  '.github/workflows/obtainx-r00-contracts.yml',
  '.github/workflows/obtainx-r00-flutter.yml',
  '.github/workflows/obtainx-r02-api36.yml',
  '.github/workflows/obtainx-r02-rt02.yml',
  '.github/workflows/obtainx-r02-rt02b.yml',
  '.github/workflows/obtainx-r02-rt02c.yml',
)
REQUIRED_WORKFLOW_IDS={
 'ObtainX R00 / Source and Contract Integrity':413437262,
 'ObtainX R00 / Hosted Flutter Qualification':413437265,
 'ObtainX R02 / API 36 Hosted Emulator Bootstrap':413666807,
 'ObtainX R02 / RT02 Real System Installer API36':413864665,
 'ObtainX R02 / RT02B Negative Installer API36':414136383,
 'ObtainX R02 / RT02C Archive-to-Installer API36':414158361,
}

def verify(root:Path=ROOT)->int:
 errors=[]
 files={}
 for p in FILES:
  try: files[p]=(root/p).read_text(encoding='utf-8')
  except (OSError,UnicodeError) as exc:errors.append(f'{p}: missing/unreadable ({type(exc).__name__})')
 def contains(p:str,*tokens:str):
  s=files.get(p,'')
  for x in tokens:
   if x not in s:errors.append(f'{p}: missing {x!r}')
 contains('lib/pages/app.dart',
  'R06VersionTile(', "ValueKey('r06-open-installed-app')",
  'app.installedInfo?.packageName == app.app.id',
  "ValueKey('r06-install-history')",'R05InstallActivityPage(', 'packageId: app.app.id,',
  "ValueKey('r06-whats-new-action')",'?r06QuickActions,', '?changeLogCard,')
 contains('lib/components/r06_version_tile.dart',
  'class R06VersionTile extends StatelessWidget','Semantics(',
  "label: '$label: $value",'SelectableText(', 'Wrap(')
 contains('lib/widgets/r05_install_activity_page.dart',
  'final String? packageId;', 'this.packageId',
  'record.packageId == widget.packageId')
 contains('test/app_page_version_actions_test.dart',
  "ValueKey('r06-open-installed-app')",'packageReadable ? findsOneWidget : findsNothing')
 contains('test/r06_app_details_test.dart',
  'installed and available versions have distinct text labels',
  'long variant versions wrap without inventing truth',
  'skip and filtered evidence is present')
 contains('docs/ROADMAP.md',
  '18 November 2026','R00', 'R01','R02','R03','R04','R05','R06','R07','R08','R09','R10','R11','R12',
  '## G. Complete original R00–R12 specification')
 contains('docs/R06_APP_DETAILS.md','R06', 'R07', 'physical-device', 'NOT_QUALIFIED')
 contains('docs/R05_INSTALL_LIFECYCLE.md','Historical R05 milestone', 'The next R06 PR')
 contains('scripts/ci/r04_completion_contract.py',INTEGRATION_BASE)
 contains('scripts/ci/r05_contract.py',INTEGRATION_BASE)
 contains('scripts/ci/obtainx_ci_policy.py',
  "'lib/pages/app.dart'", "'lib/components/r06_*'", "'test/r06_*'", "'scripts/ci/r06_*'")
 contains('.github/workflows/obtainx-r00-contracts.yml',
  'scripts/ci/r06_contract.py --check')
 contains('.github/workflows/obtainx-r00-flutter.yml',
  'flutter test --no-pub --reporter expanded')
 for p in FILES:
  if not p.startswith('.github/workflows/obtainx-r02-'):continue
  contains(p,"- 'lib/pages/app.dart'", "- 'lib/components/r06_*'", "- 'test/r06_*'", "- 'scripts/ci/r06_*'")
 try:
  baseline=json.loads(files['docs/R00_BASELINE.json'])
  if baseline.get('roadmap_sha256') != hashlib.sha256((root/'docs/ROADMAP.md').read_bytes()).hexdigest():
   errors.append('roadmap digest differs from R00 baseline')
  if baseline.get('release_authorized') is not False or baseline.get('runtime_qualified') is not False:
   errors.append('R00 baseline must not invent device/release qualification')
 except (KeyError,OSError,ValueError,TypeError) as exc:errors.append(f'R00 baseline malformed: {exc}')
 try:
  policy=json.loads(files['config/delivery-required-ci.json'])
  actual={x['name']:x['workflow_id'] for x in policy['required_workflows']}
  if policy['base_branch']!=INTEGRATION_BASE or policy['event']!='pull_request' or \
    actual!=REQUIRED_WORKFLOW_IDS or policy['release_qualification']!='separate':
   errors.append('R06 CI policy base/required IDs/release gate mismatch')
 except (KeyError,TypeError,ValueError) as exc:errors.append(f'R06 CI policy invalid: {exc}')
 if errors:
  for e in errors:print('OX_R06_CONTRACT_REFUSED '+str(e),flush=True)
  return 1
 print('OX_R06_SOURCE_CONTRACT_PASS; hosted/device/release NOT_QUALIFIED',flush=True)
 return 0

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--check',action='store_true')
 p.add_argument('--root',type=Path,default=ROOT)
 a=p.parse_args()
 raise SystemExit(verify(a.root))
