#!/usr/bin/env python3
"""Negative checks for R06 UI evidence, roadmap digest and all six required CI gates."""
from __future__ import annotations
import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('r06_contract',ROOT/'scripts/ci/r06_contract.py')
module=importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)

class R06SourceMutationTests(unittest.TestCase):
 def mutated(self,path:str,needle:str):
  with tempfile.TemporaryDirectory(prefix='ox-r06-mut-') as d:
   root=Path(d)
   for f in module.FILES:
    dst=root/f;dst.parent.mkdir(parents=True,exist_ok=True)
    dst.write_bytes((ROOT/f).read_bytes())
   target=root/path
   s=target.read_text(encoding='utf-8')
   self.assertEqual(s.count(needle),1,(path,needle))
   target.write_text(s.replace(needle,'R06_DISABLED_BY_MUTATION',1),encoding='utf-8')
   with contextlib.redirect_stdout(io.StringIO()):
    self.assertNotEqual(module.verify(root),0,path)
 def test_exact_installed_package_gate(self):
  self.mutated('lib/pages/app.dart','app.installedInfo?.packageName == app.app.id')
 def test_open_action(self):
  self.mutated('lib/pages/app.dart',"ValueKey('r06-open-installed-app')")
 def test_changelog_navigation(self):
  self.mutated('lib/pages/app.dart',"ValueKey('r06-whats-new-action')")
 def test_history_package_filter(self):
  self.mutated('lib/widgets/r05_install_activity_page.dart',
   'record.packageId == widget.packageId')
 def test_roadmap_digest(self):
  self.mutated('docs/R00_BASELINE.json','roadmap_sha256')
 def test_stack_base_branch(self):
  self.mutated('config/delivery-required-ci.json',module.R05_BASE)
 def test_required_workflow_identity(self):
  self.mutated('config/delivery-required-ci.json','413864665')
 def test_negative_no_r06_api36_trigger(self):
  self.mutated('.github/workflows/obtainx-r02-api36.yml',"- 'lib/components/r06_*'")
 def test_negative_no_r06_rt02_trigger(self):
  self.mutated('.github/workflows/obtainx-r02-rt02.yml',"- 'lib/pages/app.dart'")

if __name__=='__main__':unittest.main(verbosity=2)
