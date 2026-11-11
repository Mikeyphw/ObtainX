"""RT02E mutation checks: failing source contracts are never waived."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('r02e_source_contract',
    ROOT/'scripts/ci/r02e_source_contract.py')
assert SPEC and SPEC.loader
C=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)

class RT02EContracts(unittest.TestCase):
  def setUp(self):
    self.tmp=tempfile.TemporaryDirectory(prefix='obtainx-rt02e-contract-')
    self.addCleanup(self.tmp.cleanup)
    self.root=Path(self.tmp.name)
    for rel in C.PATHS:
      dest=self.root/rel;dest.parent.mkdir(parents=True,exist_ok=True)
      shutil.copyfile(ROOT/rel,dest)
  def mutation(self,path,old,new):
    p=self.root/path;text=p.read_text('utf8')
    self.assertGreaterEqual(text.count(old),1,'outdated contract mutation anchor '+path+' '+old)
    p.write_text(text.replace(old,new,1),'utf8')
    self.assertTrue(C.inspect(self.root),'RT02E security/CI mutation escaped: '+path)
  def test_valid_source(self):self.assertEqual(C.inspect(self.root),[])
  def test_dangling_obb_doc_comment_rejected(self):
    self.mutation(C.SERVICE, 'library;\n\nimport \'dart:io\';', 'import \'dart:io\';')
  def test_actual_cli_supports_check(self):
    result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/ci/r02e_source_contract.py'),'--check'],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=40)
    self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
  def test_no_missing_source_check(self):
    self.mutation(C.SERVICE,'sha256.bind(source.openRead()).first','sha256.convert([0])')
  def test_no_missing_copy_digest(self):
    self.mutation(C.SERVICE,'sha256.bind(pending.openRead()).first','sha256.convert([0])')
  def test_no_unsafe_source_symlink(self):
    self.mutation(C.SERVICE,'FileSystemEntity.typeSync(source.path, followLinks: false)','FileSystemEntity.typeSync(source.path, followLinks: true)')
  def test_no_skip_destination_atomic_swap(self):
    self.mutation(C.SERVICE,'await pending.rename(targetPath)','await pending.copy(targetPath)')
  def test_no_skip_rollback(self):
    self.mutation(C.SERVICE,'await backup.rename(targetPath)','await backup.delete()')
  def test_no_bypass_cancel(self):
    self.mutation(C.SERVICE,"if (isCancelled?.call() ?? false) {\n    throw const FormatException('OBB copy cancelled before staging');","if (false) {\n    throw const FormatException('OBB copy cancelled before staging');")
  def test_no_unsafe_android11_copy(self):
    self.mutation(C.PROVIDER,'OBB payload cannot be installed by this backend on Android 11+','OBB copy allowed on all SDKs')
  def test_no_permission_bypass(self):
    self.mutation(C.PROVIDER,'OBB write permission denied before Android installation','ignore OBB permission')
  def test_no_missing_flutter_test(self):
    self.mutation(C.FLUTTER,'flutter test --no-pub test/r02e_verified_obb_delivery_test.dart','echo skipped')
  def test_no_missing_hosted_contract(self):
    self.mutation(C.SOURCE_CI,'python3 -B scripts/ci/r02e_source_contract.py --check','echo skipped')
  def test_no_uncached_expensive_gradle(self):
    self.mutation(C.RT02C_CI,'cache: gradle','cache: false')
  def test_no_missing_test_negative_case(self):
    self.mutation(C.TEST,'destination symlinks','destination ignored')

if __name__=='__main__':unittest.main()
