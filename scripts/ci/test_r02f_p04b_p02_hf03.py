"""HF03: broadcast status callback and Android approval UI safety guards.

No device, no local Gradle; the actual hosted API36 step remains mandatory.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
TARGET=ROOT/'scripts/ci/r02f_p04b_p02_target.py'
HOST=ROOT/'scripts/ci/r02f_p04b_p02_hosted.py'
CONTRACT=ROOT/'scripts/ci/r02f_p04b_p02_contract.py'
DOC=ROOT/'docs/R02F_P04B_P02_EXTERNAL_POSITIVE.md'


def load_contract():
    spec=importlib.util.spec_from_file_location('p04b_hf03_contract',CONTRACT)
    assert spec and spec.loader
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PositiveAndroidBroadcastHF03(unittest.TestCase):
    def test_00_real_source_contract(self):
        self.assertEqual(load_contract().inspect(ROOT),[])

    def test_01_mutable_nonexported_receiver(self):
        t=TARGET.read_text()
        self.assertIn('PendingIntent.getBroadcast(this,id,callback,',t)
        self.assertNotIn('PendingIntent.getActivity(this,id,callback,',t)
        self.assertIn('new Intent(this, StatusReceiver.class)',t)
        self.assertIn('PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_MUTABLE',t)
        self.assertIn('<receiver android:name=".PositiveInstallActivity$StatusReceiver" android:exported="false"/>',t)
        self.assertIn('class StatusReceiver extends BroadcastReceiver',t)
        self.assertIn('Intent.FLAG_RECEIVER_FOREGROUND',t)
        self.assertEqual(t.count('session.commit(pending.getIntentSender())'),1)
        self.assertNotIn('Runtime.getRuntime().exec(',t)

    def test_02_callback_precedes_user_action(self):
        t=TARGET.read_text()
        receiver=t[t.index('public static final class StatusReceiver'):]
        self.assertIn('PackageInstaller.STATUS_PENDING_USER_ACTION',receiver)
        self.assertIn('callback.getParcelableExtra(Intent.EXTRA_INTENT,Intent.class)',receiver)
        self.assertIn('pendingApprovalIntent=approve;',receiver)
        self.assertIn('status(context,"user_approval_requested");',receiver)
        self.assertLess(receiver.index('pendingApprovalIntent=approve;'),
                        receiver.index('status(context,"user_approval_requested");'))
        self.assertIn('status(context,"missing_approval_intent")',receiver)
        self.assertIn('PackageInstaller.STATUS_SUCCESS',receiver)

    def test_03_foreground_only_launches_os_provided_intent(self):
        t=TARGET.read_text()
        entry=t[t.index('if (getIntent() != null && SHOW_APPROVAL.equals'):t.index('status(this,"started");')]
        self.assertIn('StatusReceiver.pendingApprovalIntent',entry)
        self.assertIn('"user_approval_requested".equals(',entry)
        self.assertIn('startActivity(approval.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));',entry)
        self.assertIn('StatusReceiver.pendingApprovalIntent=null;',entry)
        self.assertIn('status(this,"approval_launch_failed")',entry)
        self.assertNotIn('session.commit(',entry)
        self.assertNotIn('pm install',entry)

    def test_04_host_uses_native_status_before_one_ui_launch(self):
        h=HOST.read_text()
        self.assertIn('approval_activity_started=False',h)
        self.assertIn("observed.get('status') in (\n                        'user_approval_requested',):",h)
        self.assertNotIn("observed.get('status') in (\n                        'approval_pending'",h)
        self.assertIn("if not approval_activity_started:",h)
        self.assertIn("'dev.bikram.obtainx.P04B_POSITIVE_SHOW_APPROVAL'",h)
        self.assertIn("'-n',target.PACKAGE+'/'+target.ACTIVITY,timeout=30)",h)
        self.assertIn('if approve_if_verified():',h)
        self.assertIn("need(approvals==1,",h)
        self.assertLess(h.index('if not approval_activity_started:'), h.index('if approve_if_verified():'))

    def test_05_no_approval_forgery_or_weakened_signed_bytes(self):
        h=HOST.read_text()
        self.assertEqual(h.count('package_observation(fx,2)'),1)
        self.assertEqual(h.count('observe_signed_v2()'),3)
        self.assertIn("last_status=='system_status_success' and approvals>0",h)
        self.assertIn("'status':'system_status_success'",h)
        self.assertIn("'dart_handoff_not_success':True",h)
        self.assertIn("obj['system_approval_taps']==1",h)
        self.assertIn("'release_qualified':False",h)

    def test_06_negative_mutations_always_refused(self):
        c=load_contract()
        with tempfile.TemporaryDirectory(prefix='p04b-hf03-src-') as tmp:
            root=Path(tmp)
            for path in c.PATHS:
                p=root/path;p.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(ROOT/path,p)
            self.assertEqual(c.inspect(root),[])
            target=root/c.TARGET
            original=target.read_text()
            for old,new in (
                ('PendingIntent.getBroadcast(this,id,callback,','PendingIntent.getActivity(this,id,callback,'),
                ('android:exported="false"/>','android:exported="true"/>'),
                ('new Intent(this, StatusReceiver.class)','new Intent(this, StatusActivity.class)'),
                ('SHOW_APPROVAL.equals(getIntent().getAction())','false'),
            ):
                self.assertIn(old,original)
                target.write_text(original.replace(old,new,1))
                self.assertTrue(c.inspect(root),'mutation unexpectedly passed '+old)
                target.write_text(original)
            host=root/c.HOST
            before=host.read_text()
            host.write_text(before.replace("'user_approval_requested',):","'approval_pending',):",1))
            self.assertTrue(c.inspect(root))

    def test_07_document_qualification_unambiguous(self):
        text=DOC.read_text()
        self.assertEqual(text.count('**NOT_QUALIFIED**'),1)
        self.assertIn('six exact-head hosted',text)
        self.assertIn('STATUS_SUCCESS',text)
        self.assertIn('signed-v2',text)

if __name__=='__main__':unittest.main()
