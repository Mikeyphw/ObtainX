#!/usr/bin/env python3
"""RT02D source and mandatory-hosted-test drift audit; not Android qualification."""
from __future__ import annotations
import argparse
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
PLANNER='lib/services/install_bundle_plan.dart'
PROVIDER='lib/providers/apps_provider_install.dart'
FLUTTER='.github/workflows/obtainx-r00-flutter.yml'
CONTRACTS='.github/workflows/obtainx-r00-contracts.yml'
TEST='test/r02d_device_compatibility_test.dart'
DOC='docs/R02_RT02D_DEVICE_COMPATIBILITY.md'
PATHS=(PLANNER,PROVIDER,FLUTTER,CONTRACTS,TEST,DOC)

GUARDS={
 PLANNER:(
  'deviceLocales = const <String>[]',
  'deviceDensityDpi',
  'Ambiguous language splits require locale evidence',
  'Ambiguous density splits require display evidence',
  'No compatible language configuration split',
  'Multiple APK splits for the same density',
  'validateStagedObbPaths(',
  "path.split('/').contains('..')",
  "path.startsWith('$root/')",
 ),
 PROVIDER:(
  'deviceLocales: uiLocales',
  'deviceDensityDpi: uiDensityDpi',
  'validateStagedObbPaths(',
  'extractionRoot: dir.extracted.path',
  'obbFiles.isNotEmpty && !installer.wantsContainerHandoff',
  'OBB payload cannot be installed by this backend on Android 11+',
 ),
 FLUTTER:('flutter test --no-pub test/r02d_device_compatibility_test.dart',),
 CONTRACTS:('python3 scripts/ci/r02d_source_contract.py --check',),
 TEST:(
  'refuses ambiguous locale',
  'refuses ambiguous density',
  'staged OBB paths cannot escape extraction root',
  'picks exact region',
  'selects ARM64',
 ),
 DOC:('full Android runtime','OBB','RT02D','RT02C'),
}

def inspect(root:Path=ROOT)->list[str]:
  problems=[];data={}
  for rel in PATHS:
    path=root/rel
    if not path.is_file():problems.append('missing RT02D source '+rel);data[rel]=''
    else:data[rel]=path.read_text('utf-8')
  for rel,anchors in GUARDS.items():
    for anchor in anchors:
      if anchor not in data[rel]:problems.append(rel+': missing required contract '+anchor)
  p=data[PLANNER]
  if p.count('Ambiguous language splits require locale evidence')!=1:
    problems.append('language ambiguity refusal not unique')
  if p.count('Ambiguous density splits require display evidence')!=1:
    problems.append('density ambiguity refusal not unique')
  if 'flutter test --no-pub test/r02_install_bundle_plan_test.dart' not in data[FLUTTER]:
    problems.append('legacy R02 planner tests must remain mandatory')
  if 'await moveObbFile(obb, plan.packageName)' not in data[PROVIDER]:
    problems.append('legacy lower-API OBB code unexpectedly removed')
  if re.search(r'\b(?:gh release create|flutter build apk --release)\b',data[CONTRACTS]):
    problems.append('release side effects forbidden')
  return problems

def main()->int:
  parser=argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--check', action='store_true',
                      help='run the read-only RT02D source integrity audit')
  parser.parse_args()
  errs=inspect()
  for err in errs:print('OX_RT02D_SOURCE_REFUSED:',err)
  if errs:return 1
  print('OX_RT02D_SOURCE_CONTRACT_PASS; DEVICE_RUNTIME=NOT_QUALIFIED')
  return 0
if __name__=='__main__':raise SystemExit(main())
