#!/usr/bin/env python3
"""Build a disposable, user-approved, unprivileged PackageInstaller target.

Hosted GitHub API36 only. Never sign or install on a personal Android device.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, secrets, shutil, subprocess, sys, zipfile
from pathlib import Path

PACKAGE = 'dev.bikram.obtainx.p04b.positive'
ACTIVITY = PACKAGE+'.PositiveInstallActivity'
APK = 'p04b-positive-target.apk'
MANIFEST = '''<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="dev.bikram.obtainx.p04b.positive" android:versionCode="1" android:versionName="1.0">
  <uses-sdk android:minSdkVersion="26" android:targetSdkVersion="35"/>
  <uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES"/>
  <application android:label="ObtainX Disposable Positive CI Target" android:hasCode="true" android:debuggable="true">
    <activity android:name=".PositiveInstallActivity" android:exported="true">
      <intent-filter><action android:name="android.intent.action.VIEW"/><category android:name="android.intent.category.DEFAULT"/><data android:mimeType="application/vnd.android.package-archive"/></intent-filter>
    </activity>
    <activity android:name=".PositiveInstallActivity$StatusActivity" android:exported="false" android:launchMode="singleTop"/>
  </application>
</manifest>
'''
JAVA = r'''package dev.bikram.obtainx.p04b.positive;
import android.app.Activity;
import android.app.PendingIntent;
import android.content.Intent;
import android.content.pm.PackageInstaller;
import android.net.Uri;
import android.os.Bundle;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import java.io.InputStream;
import java.io.OutputStream;
import java.security.MessageDigest;

/** CI-only installer: user approval mandatory; no shell, root or hidden APIs. */
public final class PositiveInstallActivity extends Activity {
  static final String PREF = "p04b_positive";
  static final String FIXTURE = "dev.bikram.obtainx.rt02.fixture";
  static void status(Activity a, String value) {
    a.getSharedPreferences(PREF, MODE_PRIVATE).edit().putString("status", value).commit();
  }
  @Override public void onCreate(Bundle state) {
    super.onCreate(state);
    status(this,"started");
    Uri uri = getIntent() == null ? null : getIntent().getData();
    if (uri == null || !"content".equals(uri.getScheme()) ||
        (getIntent().getFlags() & Intent.FLAG_GRANT_READ_URI_PERMISSION) == 0) {
      status(this,"refused_content_grant"); finish(); return;
    }
    PackageInstaller installer = getPackageManager().getPackageInstaller();
    int id = -1;
    try {
      MessageDigest sha = MessageDigest.getInstance("SHA-256");
      PackageInstaller.SessionParams options = new PackageInstaller.SessionParams(
          PackageInstaller.SessionParams.MODE_FULL_INSTALL);
      options.setAppPackageName(FIXTURE);
      options.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_REQUIRED);
      id = installer.createSession(options);
      long total=0;
      try (PackageInstaller.Session session=installer.openSession(id);
           InputStream input=getContentResolver().openInputStream(uri)) {
        if (input == null) throw new IllegalStateException("missing_input_stream");
        try (OutputStream output=session.openWrite("base.apk",0L,-1L)) {
          byte[] buffer=new byte[16384];int size;
          while ((size=input.read(buffer))!=-1) {
            total+=size;
            if (total>16L*1024*1024) throw new IllegalStateException("oversize");
            sha.update(buffer,0,size);output.write(buffer,0,size);
          }
          session.fsync(output);
        }
        if (total<300) throw new IllegalStateException("undersize");
        StringBuilder hex=new StringBuilder();
        for (byte b:sha.digest()) hex.append(String.format("%02x", b & 255));
        getSharedPreferences(PREF, MODE_PRIVATE).edit()
            .putString("sha256",hex.toString()).putString("status","approval_pending").commit();
        Intent callback=new Intent(this, StatusActivity.class);
        callback.setAction("dev.bikram.obtainx.P04B_POSITIVE_STATUS");
        callback.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent pending=PendingIntent.getActivity(this,id,callback,
            PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_MUTABLE);
        session.commit(pending.getIntentSender());
      }
    } catch (Exception ignored) {
      status(this,"installer_error");
      if (id>=0) {try {installer.abandonSession(id);} catch (Exception ignore2) {}}
    }
  }
  public static final class StatusActivity extends Activity {
    @Override public void onCreate(Bundle state) {super.onCreate(state);handle(getIntent());}
    @Override public void onNewIntent(Intent intent) {super.onNewIntent(intent);handle(intent);}
    private void handle(Intent callback) {
      int result=callback.getIntExtra(PackageInstaller.EXTRA_STATUS,PackageInstaller.STATUS_FAILURE);
      if (result==PackageInstaller.STATUS_PENDING_USER_ACTION) {
        status(this,"user_approval_requested");
        Intent approve;
        if (Build.VERSION.SDK_INT>=33)
          approve=callback.getParcelableExtra(Intent.EXTRA_INTENT,Intent.class);
        else approve=(Intent)callback.getParcelableExtra(Intent.EXTRA_INTENT);
        if (approve==null) {status(this,"missing_approval_intent");finish();return;}
        try {startActivity(approve.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));}
        catch (Exception ignored) {status(this,"approval_launch_failed");}
        finish(); return;
      }
      status(this,result==PackageInstaller.STATUS_SUCCESS?"system_status_success":"system_status_failure");
      finish();
    }
  }
}
'''

def need(x,msg):
    if not x: raise RuntimeError(msg)

def cmd(*argv):
    p=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=150)
    need(p.returncode==0,'fixture command failed '+Path(argv[0]).name+' rc='+str(p.returncode))
    return p.stdout

def build(out:Path):
    need(out.is_absolute() and out.is_dir() and not out.is_symlink(),'absolute CI fixture root required')
    need(os.getenv('GITHUB_ACTIONS')=='true' and os.getenv('RUNNER_OS')=='Linux',
         'positive install target restricted to hosted GitHub runner')
    source=os.getenv('GITHUB_SHA','')
    need(re.fullmatch('[0-9a-f]{40}',source) is not None,'source SHA invalid')
    sdk=Path(os.getenv('ANDROID_HOME') or os.getenv('ANDROID_SDK_ROOT') or '/')
    tools=sdk/'build-tools'/'35.0.0'; android=sdk/'platforms'/'android-36'/'android.jar'
    for p in (tools/'aapt2',tools/'d8',tools/'zipalign',tools/'apksigner',android):
        need(p.is_file(),'Android SDK API36/build-tools35 unavailable')
    dest=out/APK;inventory=out/'p04b_positive_inventory.json'
    need(not dest.exists() and not inventory.exists(),'stale positive fixture refused')
    builddir=out/'p04b_positive_build';builddir.mkdir()
    try:
        manifest=builddir/'AndroidManifest.xml';manifest.write_text(MANIFEST)
        java=builddir/'PositiveInstallActivity.java';java.write_text(JAVA)
        classes=builddir/'classes';classes.mkdir();dex=builddir/'dex';dex.mkdir()
        cmd('javac','-source','8','-target','8','-cp',str(android),'-d',str(classes),str(java))
        compiled=sorted(classes.rglob('*.class'))
        need(2<=len(compiled)<=12,'Java target compilation incomplete')
        cmd(str(tools/'d8'),'--min-api','26','--output',str(dex),*[str(x) for x in compiled]);need((dex/'classes.dex').is_file(),'DEX missing')
        unsigned=builddir/'unsigned.apk';aligned=builddir/'aligned.apk'
        cmd(str(tools/'aapt2'),'link','-o',str(unsigned),'-I',str(android),'--manifest',str(manifest),
            '--min-sdk-version','26','--target-sdk-version','35')
        with zipfile.ZipFile(unsigned,'a') as z:z.write(dex/'classes.dex','classes.dex')
        cmd(str(tools/'zipalign'),'-f','4',str(unsigned),str(aligned))
        key=builddir/'ci-key.jks';password=secrets.token_hex(18)
        cmd('keytool','-genkeypair','-noprompt','-alias','ci', '-dname','CN=ObtainX Disposable CI Positive',
            '-keyalg','RSA','-keysize','2048','-validity','2','-keystore',str(key),
            '-storepass',password,'-keypass',password)
        cmd(str(tools/'apksigner'),'sign','--ks',str(key),'--ks-key-alias','ci',
            '--ks-pass','pass:'+password,'--key-pass','pass:'+password,'--out',str(dest),str(aligned))
        cmd(str(tools/'apksigner'),'verify',str(dest))
        raw=dest.read_bytes();need(600<len(raw)<2*1024*1024,'signed target bounds invalid')
        data={'schema':1,'source_sha':source,'package':PACKAGE,'activity':ACTIVITY,
              'sha256':hashlib.sha256(raw).hexdigest(),'signed_disposable_target':True,
              'only_disposable_fixture_install':True,'requires_system_user_approval':True,
              'physical_device_qualified':False,'shizuku_qualified':False,'dhizuku_qualified':False}
        inventory.write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')
        print('OX_P04B_P02_HOSTED_SIGNED_POSITIVE_TARGET_PASS',flush=True)
    finally:shutil.rmtree(builddir,ignore_errors=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    try:build(a.out);return 0
    except (RuntimeError,OSError,ValueError,subprocess.TimeoutExpired) as e:
        print('OX_P04B_P02_REFUSED '+str(e),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
