"""HF01 current positive-path regression tests (no device, no historical contracts)."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

ROOT=Path(__file__).resolve().parents[2]
TARGET=ROOT/'scripts/ci/r02f_p04b_p02_target.py'
HOST=ROOT/'scripts/ci/r02f_p04b_p02_hosted.py'
WORKFLOW=ROOT/'.github/workflows/obtainx-r02-rt02c.yml'


def load_runner():
    # Test only pure diagnostic helpers; never create emulator/ADB sessions.
    original={name:sys.modules.get(name) for name in
              ('r02_rt02_hosted','r02f_p04b_p02_target')}
    sys.modules['r02_rt02_hosted']=types.ModuleType('r02_rt02_hosted')
    sys.modules['r02f_p04b_p02_target']=types.ModuleType('r02f_p04b_p02_target')
    try:
        spec=importlib.util.spec_from_file_location('p04b_p02_hf01_pure',HOST)
        assert spec and spec.loader
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name,prior in original.items():
            if prior is None:sys.modules.pop(name,None)
            else:sys.modules[name]=prior

class PositivePathHF01(unittest.TestCase):
    def test_01_disposable_activity_finishes_after_session_commit(self):
        source=TARGET.read_text()
        start=source.index('session.commit(pending.getIntentSender())')
        end=source.index('public static final class StatusActivity',start)
        segment=source[start:end]
        self.assertIn('} finally {',segment)
        self.assertIn('finish();',segment)
        self.assertIn('status(this,"installer_error")',segment)
        self.assertEqual(source.count('session.commit(pending.getIntentSender())'),1)

    def test_02_target_states_are_strict(self):
        run=load_runner()
        self.assertEqual(run.normalize_target_status({'status':'user_approval_requested'}),
                         'user_approval_requested')
        self.assertEqual(run.normalize_target_status({'status':'system_status_success'}),
                         'system_status_success')
        self.assertEqual(run.normalize_target_status({'status':'user\nsecret'}),
                         'unrecognized_or_missing')
        self.assertEqual(run.normalize_target_status({'other':'value'}),
                         'unrecognized_or_missing')
        self.assertIn('installer_error',run.FAILURE_STATES)

    def test_03_refusal_receipt_bounded_and_never_promotes_success(self):
        run=load_runner()
        with tempfile.TemporaryDirectory(prefix='ox-hf01-') as tmp:
            root=Path(tmp)
            private=root/'private.log'
            private.write_text('sensitive-runtime-log\n')
            import time
            report=run.failure_report(root,'a'*40,'12345','not-a-valid-stage',
                 time.monotonic()-8,0,'secrets-and-internal-value',25,4,False,
                 private,'TIMEOUT')
            path=root/run.DIAGNOSTIC
            payload=path.read_text()
            self.assertLess(len(payload),4096)
            self.assertEqual(report['stage'],'UNCLASSIFIED')
            self.assertEqual(report['target_status'],'unrecognized_or_missing')
            self.assertEqual(report['status'],'REFUSED_NOT_QUALIFIED')
            self.assertFalse(report['real_android_positive_qualified'])
            self.assertFalse(report['release_qualified'])
            self.assertFalse(report['raw_logs_uploaded'])
            self.assertNotIn('sensitive-runtime-log',payload)
            self.assertNotIn('secrets-and-internal-value',payload)
            self.assertEqual(report,json.loads(payload))

    def test_04_positive_approval_cannot_be_inferred_from_flutter_only(self):
        s=HOST.read_text()
        self.assertIn("last_status=='system_status_success' and approvals>0",s)
        self.assertIn('package_observation(fx,2)',s)
        self.assertIn("base.APP+'/dev.imranr.obtainium.MainActivity'",s)
        self.assertIn('if process.poll() is not None and process.returncode != 0:',s)
        self.assertIn('need(approvals>0 and last_status==',s)
        self.assertIn("'status':'system_status_success'",s)
        self.assertIn("'dart_handoff_not_success':True",s)

    def test_05_failure_diagnostic_only_upload(self):
        w=WORKFLOW.read_text()
        self.assertIn('obtainx-rt02c/r02f-p04b-p02-diagnostics.json',w)
        self.assertIn('obtainx-rt02c/r02f-p04b-p02-positive.json',w)
        upload=w.split('name: Record only bounded receipt hashes before artifact upload',1)[-1]
        self.assertNotIn('r02f-p04b-p02-private.log',upload)

if __name__=='__main__':unittest.main()
