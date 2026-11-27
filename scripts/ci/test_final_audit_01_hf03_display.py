"""Android WindowManager display-state parsing and command regression.

Fixtures reproduce documented AOSP dump structure, not recorded emulator
output. Real hosted cancellation remains mandatory.
"""
from __future__ import annotations

import contextlib
import io
import unittest
from unittest.mock import patch

import r02f_p03_hosted as host
from test_final_audit_01_hf02_foreground import APP, APPROVAL, Clock, window


class DisplayStateTests(unittest.TestCase):
    def test_window_inventory_cannot_authorize_focus(self):
        dump = ('WINDOW MANAGER WINDOWS (dumpsys window windows)\n'
                ' Window #0 Window{a123 u0 '+APPROVAL+'}:\n'
                ' mTopFocusedDisplayId=0\n')
        self.assertEqual(host.focus_observation(dump), (None, 'DISPLAY_HEADER_MISSING'))

    def test_real_display_dump_layout_accepts_live_focus(self):
        self.assertEqual(host.focus_observation(window(APPROVAL)), (APPROVAL, 'APPROVER_FOCUSED'))
        self.assertEqual(host.focus_observation(window(APP)), (APP, 'APP_FOCUSED'))
        self.assertEqual(host.focus_observation(window(APP).replace('mDisplayId=0', 'mDisplayId=0 (organized)')), (APP, 'APP_FOCUSED'))

    def test_crlf_and_short_component(self):
        short = 'com.google.android.packageinstaller/.InstallStart'
        self.assertEqual(host.focus_observation(window(short).replace('\n', '\r\n')),
                         ('com.google.android.packageinstaller/com.google.android.packageinstaller.InstallStart', 'APPROVER_FOCUSED'))

    def test_nondefault_and_multiple_displays_refuse(self):
        self.assertEqual(host.focus_observation(window(APPROVAL).replace('mDisplayId=0', 'mDisplayId=10')),
                         (None, 'DISPLAY_AMBIGUOUS'))
        self.assertEqual(host.focus_observation(window(APPROVAL)+' Display: mDisplayId=3\n mCurrentFocus=null\n'),
                         (None, 'DISPLAY_AMBIGUOUS'))

    def test_missing_null_duplicate_and_malformed_focus(self):
        dump = window(APPROVAL)
        for replacement, expected in [('', 'FOCUS_MISSING'), (' mCurrentFocus=null', 'FOCUS_NULL'),
                                      (' mCurrentFocus=Window{abcd u10 '+APPROVAL+'}', 'FOCUS_NONCOMPONENT'),
                                      (' mCurrentFocus=Window{abcd u0 '+APPROVAL+' EXITING}', 'FOCUS_NONCOMPONENT')]:
            with self.subTest(expected=expected):
                modified = '\n'.join(replacement if 'mCurrentFocus=' in line else line for line in dump.splitlines())
                self.assertEqual(host.focus_observation(modified), (None, expected))
        self.assertEqual(host.focus_observation(dump+' mCurrentFocus=Window{a123 u0 '+APP+'}\n'),
                         (None, 'FOCUS_AMBIGUOUS'))

    def test_focused_app_is_not_window_focus(self):
        self.assertEqual(host.focus_observation(window(APP)), (APP, 'APP_FOCUSED'))
        self.assertEqual(host.focus_observation(window('example.packageinstaller/.InstallStart')),
                         ('example.packageinstaller/example.packageinstaller.InstallStart', 'OTHER_FOCUSED'))

    def test_oversize_refuses(self):
        self.assertEqual(host.focus_observation('x'*(2*1024*1024+1)), (None, 'DISPLAY_OVERSIZE'))

    def test_exact_adb_command_and_safe_timeout_diagnostic(self):
        clock = Clock()
        with patch.object(host.time, 'monotonic', clock.monotonic), patch.object(host.time, 'sleep', clock.sleep), \
             patch.object(host.base, 'adb', return_value=window('private.example/.Hidden')) as adb, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaisesRegex(host.ForegroundRefused, '^P03_APPROVAL_FOCUS_TIMEOUT$'):
                host.wait_focused_window(lambda c: c.split('/',1)[0] in host.base.APPROVERS,
                                         clock.now+0.8, 'P03_APPROVAL_FOCUS_TIMEOUT')
        self.assertTrue(adb.call_args_list)
        self.assertTrue(all(call.args == ('shell','dumpsys','window','displays') for call in adb.call_args_list))
        self.assertEqual(output.getvalue().strip(), 'OX_R02F_P03_FOCUS_TIMEOUT category=OTHER_FOCUSED')
        self.assertNotIn('private.example', output.getvalue())


if __name__ == '__main__':
    unittest.main()
