"""HF09: no uploaded raw logs; classify actual Flutter P03 failure safely."""
from __future__ import annotations
import ast
from pathlib import Path
import hashlib
import json
import tempfile
import unittest
import importlib.util
import contextlib
import io

HERE=Path(__file__).resolve().parent
P=HERE/'r02f_p03_failure_diagnostics.py'
H=HERE/'r02f_p03_hosted.py'
WF=HERE.parent.parent/'.github/workflows/obtainx-r02-rt02c.yml'

def module():
    spec=importlib.util.spec_from_file_location('r02f_p03_failure_diagnostics',P)
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

class DiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.M=module()
        cls.sha='a'*40
    def classify(self,txt='',rc=1,stage='GRADLE_BUILD'):
        return self.M.classify(txt,rc,stage,self.sha,'12345',txt.encode())
    def test_unclassified_failure_still_refuses(self):
        d=self.classify('private /secret/app/file username=top-secret')
        self.assertEqual(d['status'],self.M.STATUS)
        self.assertEqual(d['failure_categories'],['P03_UNKNOWN_FLUTTER_FAILURE'])
        self.assertFalse(d['android_live_audit_passed'])
        self.assertFalse(d['release_qualified'])
        self.assertNotIn('secret',json.dumps(d))
        self.assertEqual(d['private_log_sha256'],hashlib.sha256(b'private /secret/app/file username=top-secret').hexdigest())
    def test_late_cancel_widget_lost(self):
        d=self.classify(self.M.STAGES[0]+'\nActual production AppPage lost its Cancel action')
        self.assertEqual(d['unique_dart_marker_indices'],[1])
        self.assertIn('P03_CANCEL_UI_LOST',d['failure_categories'])
    def test_foreground_failure_not_android_pass(self):
        d=self.classify('Host did not verify approval screen before ObtainX foreground')
        self.assertEqual(d['failure_categories'],['P03_HOST_FOREGROUND_REFUSED'])
        self.assertFalse(d['android_live_audit_passed'])
    def test_approval_timeout(self):
        d=self.classify('P03 owned session never reached Android pending user approval')
        self.assertIn('P03_APPROVAL_TIMEOUT',d['failure_categories'])
    def test_prior_flutter_success_with_nonzero_exit_refused(self):
        d=self.classify('All tests passed!\nException: TestFailure',rc=1)
        self.assertTrue(d['flutter_success_marker_seen'])
        self.assertTrue(d['flutter_exit_nonzero'])
        self.assertEqual(d['status'],self.M.STATUS)
    def test_duplicate_approval_markers_flagged(self):
        d=self.classify((self.M.STAGES[2]+'\n')*2)
        self.assertTrue(d['duplicate_dart_stage_markers'])
        self.assertEqual(d['unique_dart_marker_indices'],[])
    def test_no_unknown_runner_stage_exfiltration(self):
        d=self.classify('some raw text',stage='/home/runner/secret')
        self.assertEqual(d['last_runner_stage'],'UNKNOWN')
        self.assertNotIn('/home/',json.dumps(d))
    def test_reject_source_and_run_identifier_forgery(self):
        with self.assertRaises(ValueError):
            self.M.classify('',1,'FLUTTER_STARTING','bad','123',b'')
        with self.assertRaises(ValueError):
            self.M.classify('',1,'FLUTTER_STARTING',self.sha,'../../file',b'')
    def test_private_bounded_writing_and_stale_refusal(self):
        with tempfile.TemporaryDirectory(prefix='p03-hf09-') as d:
            root=Path(d);p=root/'private.log';p.write_text('PlatformException token=DO-NOT-PRINT /very/private\n')
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                diag=self.M.write_failure(root,p,1,'APPROVAL_PENDING',self.sha,'12345')
            self.assertEqual(diag['failure_categories'],['P03_ANDROID_PLATFORM_EXCEPTION'])
            data=(root/self.M.NAME).read_text()
            self.assertNotIn('DO-NOT-PRINT',data+output.getvalue())
            self.assertNotIn('/very/private',data+output.getvalue())
            self.assertNotIn('PlatformException',data+output.getvalue())
            with self.assertRaises(ValueError):
                self.M.write_failure(root,p,1,'APPROVAL_PENDING',self.sha,'12345')
    def test_symlink_private_log_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);src=root/'file';src.write_text('raw private');s=root/'alias';s.symlink_to(src)
            with self.assertRaises(ValueError):
                self.M.write_failure(root,s,1,'UNKNOWN',self.sha,'12345')
    def test_complete_code_allowlist(self):
        self.assertTrue(all(k.startswith('P03_') and k.upper()==k for k,_ in self.M.CATEGORIES))
        self.assertTrue(all(len(v)<100 for _,v in self.M.CATEGORIES))
    def test_all_case_markers_are_constant(self):
        self.assertEqual(len(self.M.STAGES),5)
        self.assertTrue(all(s.startswith('OX_P03_DART_STAGE=') for s in self.M.STAGES))
    def test_hosted_runner_reports_before_refusing(self):
        if not H.is_file():self.skipTest('standalone diagnostic module test')
        s=H.read_text()
        old_call = 'write_failure(out, log, process.returncode, stage, source, runid)'
        direct_call = 'write_failure(out, log, process.returncode, final_stage, source, runid)'
        recompute = 'for marker, label in reversed(tuple(zip(MARKERS,'
        self.assertNotIn('print(text)', s)
        self.assertIn("raise Refused('Flutter P03 app UI test failed", s)
        if recompute in s:
            self.assertIn('final_stage = stage', s)
            if direct_call in s:
                call = direct_call
                self.assertLess(s.index('final_stage = stage'), s.index(call))
            else:
                call = old_call
                assign = 'stage = final_stage\n            diag = ' + call
                self.assertIn(assign, s)
                self.assertLess(s.index('final_stage = stage'), s.index(assign))
        else:
            call = old_call
            self.assertIn(call, s)
        self.assertEqual(s.count(old_call) + s.count(direct_call), 1)
        self.assertLess(s.index(call), s.index("raise Refused('Flutter P03 app UI test failed"))
    def test_workflow_artifact_keeps_private_log_excluded(self):
        if not WF.is_file():self.skipTest('standalone diagnostic module test')
        w=WF.read_text()
        self.assertIn('r02f-p03-failure-diagnostics.json',w)
        self.assertNotIn('${{ runner.temp }}/obtainx-rt02c/r02f-p03-private.log',w)
        self.assertEqual(w.count('r02f_p03_hosted.py run --out'),1)
        self.assertEqual(w.count('r02f_p03_hosted.py audit --out'),1)
        self.assertEqual(w.count('r02f_p03_hosted.py verify --out'),1)
    def test_runtime_code_valid_ast(self):
        ast.parse(P.read_text())
        if H.is_file():ast.parse(H.read_text())

if __name__=='__main__':unittest.main()
