#!/usr/bin/env python3
"""RT02E OBB verified-copy and Gradle-cache source contracts (not device proof)."""
from __future__ import annotations
import argparse
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
SERVICE='lib/services/verified_obb_delivery.dart'
PROVIDER='lib/providers/apps_provider_install.dart'
TEST='test/r02e_verified_obb_delivery_test.dart'
FLUTTER='.github/workflows/obtainx-r00-flutter.yml'
SOURCE_CI='.github/workflows/obtainx-r00-contracts.yml'
RT02C_CI='.github/workflows/obtainx-r02-rt02c.yml'
DOC='docs/R02_RT02E_OBB_DELIVERY.md'
PATHS=(SERVICE,PROVIDER,TEST,FLUTTER,SOURCE_CI,RT02C_CI,DOC)
ANCHORS={
 SERVICE:(
  'copyVerifiedObbFile(', 'validateObbFileNames([source.path], packageName)',
  'FileSystemEntity.typeSync(source.path, followLinks: false)',
  'sha256.bind(source.openRead()).first',
  'sha256.bind(pending.openRead()).first',
  'await pending.rename(targetPath)',
  'await backup.rename(targetPath)',
  'isCancelled?.call()',
  'destinationFolder.create(recursive: true)',
 ),
 PROVIDER:(
  "import 'package:obtainium/services/verified_obb_delivery.dart';",
  'await moveObbFile(obb, plan.packageName)',
  'OBB payload cannot be installed by this backend on Android 11+',
  'OBB write permission denied before Android installation',
  'copyVerifiedObbFile(',
  'destinationFolder: target',
 ),
 TEST:(
  'copies exact OBB bytes', 'cancelled preflight',
  'cancellation after copy', 'rejects wrong app',
  'rejects empty, oversized', 'destination symlinks',
 ),
 FLUTTER:('flutter test --no-pub test/r02e_verified_obb_delivery_test.dart',),
 SOURCE_CI:('python3 -B scripts/ci/r02e_source_contract.py --check',),
 RT02C_CI:('cache: gradle', 'cache-dependency-path:',
           'android/gradle/wrapper/gradle-wrapper.properties'),
 DOC:('RT02E', 'Android 11+', 'Not qualified', 'Gradle'),
}

def inspect(root:Path=ROOT)->list[str]:
  errors=[]; data={}
  for rel in PATHS:
    path=root/rel
    if not path.is_file() or path.is_symlink():
      errors.append('missing or linked RT02E file '+rel)
      data[rel]=''
    else:
      data[rel]=path.read_text(encoding='utf8')
  for rel,anchors in ANCHORS.items():
    for anchor in anchors:
      if anchor not in data[rel]:errors.append(rel+': RT02E protected anchor missing '+anchor)
  # A doc comment ahead of imports is dangling without a Dart library directive.
  # Anchor it at file start so a decoy `library;` elsewhere cannot pass.
  if not re.match(r'\A(?:///[^\n]*\n)+library;\n', data[SERVICE]):
    errors.append('OBB service library documentation must precede library directive')
  provider=data[PROVIDER]
  start=provider.find('Future<bool> installApkDir(')
  install=provider.find('await installApk(\n',start)
  permission=provider.find('OBB write permission denied before Android installation',start)
  if start<0 or install<0 or permission<0 or not (start<permission<install):
    errors.append('OBB permission preflight must precede APK session')
  if provider.count('OBB payload cannot be installed by this backend on Android 11+')!=2:
    errors.append('both preflight and runtime Android 11+ OBB refusals required')
  if provider.count('await moveObbFile(obb, plan.packageName)')!=1:
    errors.append('OBB after-confirmation operation must occur exactly once')
  if data[SERVICE].count('sha256.bind(')!=2:
    errors.append('OBB source and staged copy both require SHA256')
  if data[SERVICE].count('isCancelled?.call()')!=2:
    errors.append('pre-copy and pre-commit cancellation guards both required')
  if 'flutter test --no-pub test/r02d_device_compatibility_test.dart' not in data[FLUTTER]:
    errors.append('inherited RT02D Flutter tests removed')
  if 'python3 scripts/ci/r02d_source_contract.py --check' not in data[SOURCE_CI]:
    errors.append('inherited RT02D source CI removed')
  if 'flutter analyze integration_test lib test' not in data[RT02C_CI]:
    errors.append('RT02C analyzer removed')
  return errors

def main()->int:
  parser=argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--check',action='store_true',help='read-only source contract inspection')
  parser.parse_args()
  errors=inspect()
  for error in errors:print('OX_RT02E_CONTRACT_REFUSED:',error)
  if errors:return 1
  print('OX_RT02E_SOURCE_CONTRACT_PASS; OBB_DEVICE_RUNTIME=NOT_QUALIFIED')
  return 0
if __name__=='__main__':raise SystemExit(main())
