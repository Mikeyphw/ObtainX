"""HF02 regression: exact source guards, early-exit privacy and real Android gates.

Host-only unit tests. Never issue ADB or install a package.
"""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import types
import unittest

ROOT=Path(__file__).resolve().parents[2]
HOST=ROOT/'scripts/ci/r02f_p04b_p02_hosted.py'
DOC=ROOT/'docs/R02F_P04B_P02_EXTERNAL_POSITIVE.md'
CONTRACT=ROOT/'scripts/ci/r02f_p04b_p02_contract.py'


def load(module_path,name):
    spec=importlib.util.spec_from_file_location(name,module_path)
    assert spec and spec.loader
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_pure_host():
    stubs={name:sys.modules.get(name) for name in
           ('r02_rt02_hosted','r02f_p04b_p02_target')}
    for name in stubs:
        sys.modules[name]=types.ModuleType(name)
    try:return load(HOST,'p04b_p02_hf02_test_host')
    finally:
        for name,prior in stubs.items():
            if prior is None:sys.modules.pop(name,None)
            else:sys.modules[name]=prior


class Hf02Guards(unittest.TestCase):
    def test_signed_v2_single_mutation_anchor_both_live_observations(self):
        s=HOST.read_text()
        self.assertEqual(s.count('package_observation(fx,2)'),1)
        self.assertEqual(s.count('observe_signed_v2()'),3)
        self.assertIn('def observe_signed_v2():\n            return package_observation(fx,2)',s)
        self.assertIn('                    observe_signed_v2()\n',s)
        self.assertIn('        after=observe_signed_v2()\n',s)
        self.assertIn("'status':'system_status_success'",s)
        self.assertIn('need(approvals==1,',s)

    def test_document_scope_mutation_is_detected_at_exact_phrase(self):
        c=load(CONTRACT,'p04b_hf02_scope_contract')
        self.assertEqual(c.inspect(ROOT),[])
        with tempfile.TemporaryDirectory(prefix='p04b-hf02-doc-') as tmp:
            root=Path(tmp)
            for path in c.PATHS:
                p=root/path;p.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(ROOT/path,p)
            doc=root/c.DOC
            orig=doc.read_text()
            anchor='**NOT_QUALIFIED** until hosted API 36 workflow actually passes.'
            self.assertEqual(orig.count(anchor),1)
            # Historical R00 test_15 uses the shorter bold-marker anchor.
            # Never append a second occurrence in the HF02 handoff notes.
            self.assertEqual(orig.count('**NOT_QUALIFIED**'),1)
            doc.write_text(orig.replace(anchor,'**PASS** until hosted API 36 workflow actually passes.',1))
            reasons=c.inspect(root)
            self.assertTrue(any('qualification statement' in x for x in reasons))

    def test_known_failures_are_categorized_without_raw_log_contents(self):
        h=load_pure_host()
        with tempfile.TemporaryDirectory(prefix='ox-hf02-private-') as tmp:
            root=Path(tmp)
            log=root/'flutter-private.log'
            log.write_text('DO-NOT-SHARE /sdcard/Download/private AND PlatformException(secret)')
            self.assertEqual(h.private_flutter_failure_kind(log),'PLATFORM_CHANNEL')
            result=h.failure_report(root,'a'*40,'42','FLUTTER_EXIT_EARLY',
                  time.monotonic()-10,0,'approval_pending',2,0,False,log,
                  'OTHER',1)
            public=(root/h.DIAGNOSTIC).read_text()
            self.assertEqual(result['flutter_failure_kind'],'PLATFORM_CHANNEL')
            self.assertEqual(result['flutter_exit_code'],1)
            self.assertEqual(result['target_status'],'approval_pending')
            self.assertEqual(result['status'],'REFUSED_NOT_QUALIFIED')
            self.assertFalse(result['real_android_positive_qualified'])
            self.assertFalse(result['release_qualified'])
            self.assertFalse(result['raw_logs_uploaded'])
            self.assertEqual(json.loads(public),result)
            self.assertLess(len(public),4096)
            self.assertNotIn('DO-NOT-SHARE',public)
            self.assertNotIn('/sdcard/Download/private',public)
            self.assertNotIn('secret',public)
            log.write_text('x'*120000+'\nLost connection to device\n')
            self.assertEqual(h.private_flutter_failure_kind(log),'DEVICE_DISCONNECTED')

    def test_missing_or_unrecognized_private_log_never_leaks(self):
        h=load_pure_host()
        with tempfile.TemporaryDirectory(prefix='ox-hf02-log-') as tmp:
            p=Path(tmp)/'nonexistent'
            self.assertEqual(h.private_flutter_failure_kind(p),'NO_PRIVATE_LOG')
            p.write_text('foo\nbar\n')
            self.assertEqual(h.private_flutter_failure_kind(p),'UNCLASSIFIED_PRIVATE_FAILURE')

    def test_approval_must_come_from_android_callback(self):
        s=HOST.read_text()
        self.assertIn("'user_approval_requested',):",s)
        self.assertNotIn("'approval_pending','user_approval_requested'):",s)
        self.assertIn('if process.poll() is not None and process.returncode != 0:',s)
        self.assertLess(s.index("last_status=normalize_target_status(observed)"),
                        s.index('if process.poll() is not None and process.returncode != 0:'))
        self.assertIn('if approve_if_verified():',s)
        self.assertIn('process.returncode if process is not None else None',s)
        self.assertIn('if (last_status==\'system_status_success\' and approvals>0',s)

if __name__=='__main__':unittest.main()
