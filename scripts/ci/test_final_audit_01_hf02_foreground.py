"""Exercise the actual P03 hosted foreground handshake at isolated boundaries.

No simulated fixture is Android acceptance; the real P03 CI remains mandatory.
"""
from __future__ import annotations

import contextlib
import http.client
import io
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

import r02f_p03_hosted as host
import r02_rt02c_hosted as rt02c

APP = host.FOREGROUND_COMPONENT
APPROVAL = 'com.google.android.packageinstaller/com.android.packageinstaller.InstallStart'
BASELINE = {'version_code': 1, 'base_sha256': 'a'*64}


def window(component):
    return ('  Window #2 Window{abcd u0 '+APPROVAL+'}\n'
            '  mCurrentFocus=Window{a123 u0 '+component+'}\n')


class Clock:
    def __init__(self):
        self.now = 10.0

    def monotonic(self):
        return self.now

    def sleep(self, delay):
        self.now += delay


class ForegroundTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.addCleanup(patch.stopall)
        patch.object(host.time, 'monotonic', self.clock.monotonic).start()
        patch.object(host.time, 'sleep', self.clock.sleep).start()
        self.baseline = patch.object(host.rt02c, 'baseline_v1', return_value=BASELINE).start()
        self.adb = patch.object(host.base, 'adb').start()

    def restore(self):
        host.restore_app_foreground(Path('fixtures'), BASELINE)

    def commands(self):
        return [c.args for c in self.adb.call_args_list]

    def start_count(self):
        return sum(c[:3] == ('shell', 'am', 'start') for c in self.commands())

    def refuse(self, code):
        with self.assertRaisesRegex(host.ForegroundRefused, '^'+code+'$'):
            self.restore()

    def test_delayed_approval_then_delayed_app_focus(self):
        self.adb.side_effect = [window(APP), window(APPROVAL), window(APPROVAL),
                                'Starting: Intent', window(APPROVAL), window(APP)]
        self.restore()
        self.assertEqual(self.start_count(), 1)
        self.assertEqual(self.baseline.call_count, 1)
        self.assertGreaterEqual(self.clock.now, 10.8)
        self.assertEqual(self.commands()[3], ('shell','am','start','-f','0x24000000','-n',APP))
        self.assertTrue(all(c.kwargs['timeout'] <= host.FOREGROUND_BUDGET for c in self.adb.call_args_list))

    def test_stale_unfocused_installer_is_not_proof(self):
        self.adb.return_value = window(APP)
        self.refuse('P03_APPROVAL_FOCUS_TIMEOUT')
        self.assertEqual(self.start_count(), 0)
        self.baseline.assert_not_called()
        self.assertLessEqual(self.clock.now, 10 + host.APPROVAL_FOCUS_BUDGET)

    def test_untrusted_and_ambiguous_focus(self):
        for data in (window(APPROVAL).replace(' u0 ', ' u10 '),
                     window(APPROVAL)+window(APP),
                     'mCurrentFocus=null\nmFocusedApp='+APPROVAL,
                     'mCurrentFocus=Window{a123 u0 '+APPROVAL+' extra}'):
            self.assertIsNone(host.focused_component(data))
        self.assertEqual(host.focused_component(window(APPROVAL)), APPROVAL)
        self.assertNotIn('example.packageinstaller', host.base.APPROVERS)

    def test_failed_window_command_is_not_retried(self):
        self.adb.side_effect = host.base.Refused('private host output')
        self.refuse('P03_WINDOW_QUERY_REFUSED')
        self.assertEqual(self.adb.call_count, 1)
        self.baseline.assert_not_called()

    def test_mismatched_signed_baseline_prevents_start(self):
        self.adb.return_value = window(APPROVAL)
        self.baseline.return_value = {'version_code': 2}
        self.refuse('P03_BASELINE_REFUSED')
        self.assertEqual(self.start_count(), 0)

    def test_baseline_command_failure_stays_fixed(self):
        self.adb.return_value = window(APPROVAL)
        self.baseline.side_effect = rt02c.Refused('private APK path')
        self.refuse('P03_BASELINE_REFUSED')
        self.assertEqual(self.start_count(), 0)

    def test_slow_baseline_cannot_authorize_late_mutation(self):
        self.adb.return_value = window(APPROVAL)
        def late(*args, **kwargs):
            self.assertEqual(kwargs['deadline'], 10 + host.FOREGROUND_BUDGET)
            self.clock.now += host.FOREGROUND_BUDGET + 1
            return BASELINE
        self.baseline.side_effect = late
        self.refuse('P03_FOREGROUND_DEADLINE')
        self.assertEqual(self.start_count(), 0)

    def test_approval_disappears_before_start(self):
        self.adb.side_effect = lambda *args, **kw: window(APPROVAL if self.adb.call_count == 1 else APP)
        self.refuse('P03_APPROVAL_FOCUS_TIMEOUT')
        self.assertEqual(self.start_count(), 0)

    def test_command_error_not_retried_even_on_zero_exit(self):
        self.adb.side_effect = [window(APPROVAL), window(APPROVAL), 'Error: private details']
        self.refuse('P03_FOREGROUND_START_REFUSED')
        self.assertEqual(self.start_count(), 1)

    def test_uncertain_foreground_command_not_retried(self):
        self.adb.side_effect = [window(APPROVAL), window(APPROVAL), host.base.Refused('private text')]
        self.refuse('P03_FOREGROUND_START_REFUSED')
        self.assertEqual(self.start_count(), 1)

    def test_successful_start_without_focus_cannot_pass(self):
        self.adb.side_effect = lambda *args, **kw: ('Starting: Intent' if args[:3] == ('shell','am','start') else window(APPROVAL))
        self.refuse('P03_APP_FOCUS_TIMEOUT')
        self.assertEqual(self.start_count(), 1)


class HandlerTests(unittest.TestCase):
    def setUp(self):
        host.P03Handler.foreground_count = 0
        host.P03Handler.foreground_attempted = False
        host.P03Handler.baseline = BASELINE
        host.P03Handler.fixtures = Path('fixtures')
        self.server = host.ThreadingHTTPServer(('127.0.0.1',0), host.P03Handler)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.thread.join, 3)
        self.addCleanup(self.server.shutdown)

    def post(self, path='/p03/foreground', body=b''):
        c = http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        try:
            c.request('POST',path,body=body)
            r = c.getresponse()
            return r.status,r.read()
        finally:
            c.close()

    def test_one_real_handler_success_then_duplicate_refusal(self):
        with patch.object(host,'restore_app_foreground') as restore:
            self.assertEqual(self.post(),(200,b'foreground_ready'))
            self.assertEqual(self.post()[0],409)
            restore.assert_called_once_with(Path('fixtures'),BASELINE)
        self.assertEqual(host.P03Handler.foreground_count,1)

    def test_failure_is_fixed_and_cannot_be_replayed(self):
        with patch.object(host,'restore_app_foreground',side_effect=host.ForegroundRefused('P03_BASELINE_REFUSED')) as restore, contextlib.redirect_stdout(io.StringIO()) as log:
            status,body=self.post()
            self.assertEqual(status,409)
            self.assertIn(b'P03_BASELINE_REFUSED',body)
            self.assertEqual(self.post()[0],409)
            restore.assert_called_once()
        self.assertEqual(host.P03Handler.foreground_count,0)
        self.assertEqual(log.getvalue().strip(),'OX_R02F_P03_FOREGROUND_REFUSED code=P03_BASELINE_REFUSED')

    def test_bad_request_never_starts_foreground(self):
        with patch.object(host,'restore_app_foreground') as restore:
            self.assertEqual(self.post('/other')[0],403)
            self.assertEqual(self.post(body=b'x')[0],403)
            restore.assert_not_called()
        self.assertFalse(host.P03Handler.foreground_attempted)


if __name__ == '__main__':
    unittest.main()
