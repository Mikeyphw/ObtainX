#!/usr/bin/env python3
"""R07 adversarial source-contract mutations with real temporary worktrees."""
from __future__ import annotations
import importlib.util, pathlib, tempfile, unittest
import shutil, os
SPEC=importlib.util.spec_from_file_location('r07_contract',pathlib.Path(__file__).with_name('r07_contract.py'))
module=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(module)
class R07ContractTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
  self.addCleanup(self.temp.cleanup)
  self.root=pathlib.Path(self.temp.name)
  for path in (*module.TOKENS,*module.R02_WORKFLOWS,'docs/R00_BASELINE.json','config/delivery-required-ci.json'):
   src=module.ROOT/path
   target=self.root/path;target.parent.mkdir(parents=True,exist_ok=True)
   shutil.copyfile(src,target)
  (self.root/'docs/ROADMAP.md').write_bytes((module.ROOT/'docs/ROADMAP.md').read_bytes())
 def mutate(self,path,needle,replacement='INVALID'):
  p=self.root/path
  s=p.read_text();self.assertIn(needle,s)
  p.write_text(s.replace(needle,replacement,1))
 def test_source_contract(self): self.assertEqual(module.verify(self.root),[])
 def test_reject_missing_notification_route(self):
  self.mutate('lib/providers/notifications_provider.dart',"payload.startsWith('r07:')")
  self.assertTrue(any('notifications' in x for x in module.verify(self.root)))
 def test_reject_missing_existing_journal(self):
  self.mutate('lib/services/r07_activity_catalog.dart','R05OperationJournal.instance')
  self.assertTrue(any('catalog' in x for x in module.verify(self.root)))
 def test_reject_old_competing_page(self):
  p=self.root/'lib/widgets/r05_install_activity_page.dart'
  p.write_text(p.read_text()+'\nclass R05InstallActivityPage {}\n')
  self.assertTrue(any('competes' in x for x in module.verify(self.root)))
 def test_reject_live_pending_restart_mutation(self):
  p=self.root/'lib/services/r07_activity_catalog.dart'
  p.write_text(p.read_text()+'\n// await _installJournal.recoverInterruptedOnce()\n')
  self.assertTrue(any('in-flight' in x for x in module.verify(self.root)))
 def test_reject_r02_risk_omission(self):
  self.mutate(module.R02_WORKFLOWS[0],"- 'lib/services/r07_*'")
  self.assertTrue(any('risk path' in x for x in module.verify(self.root)))
 def test_reject_roamdap_digest_tamper(self):
  with (self.root/'docs/ROADMAP.md').open('ab') as f:f.write(b'\nmodified')
  self.assertTrue(any('digest' in x for x in module.verify(self.root)))
 def test_reject_missing_r06_navigation(self):
  self.mutate('lib/pages/app.dart','R07ActivityCenterPage(')
  self.assertTrue(any('app.dart' in x for x in module.verify(self.root)))
if __name__=='__main__': unittest.main()
