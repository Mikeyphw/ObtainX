#!/usr/bin/env python3
"""Compile a disposable unprivileged ACTION_VIEW receiver on GitHub-hosted Android.

The receiver ONLY reads and hashes a content:// APK and declines the install.
This is P04B negative-path evidence, NOT a positive third-party installer.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import zipfile

PACKAGE='dev.bikram.obtainx.p04b.target'
ACTIVITY=PACKAGE+'.DeclineActivity'
APK='p04b-external-decline.apk'
MANIFEST='''<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="dev.bikram.obtainx.p04b.target" android:versionCode="1" android:versionName="1.0">
  <uses-sdk android:minSdkVersion="26" android:targetSdkVersion="35"/>
  <application android:label="ObtainX Disposable Decline Target" android:hasCode="true" android:debuggable="true">
    <activity android:name=".DeclineActivity" android:exported="true">
      <intent-filter><action android:name="android.intent.action.VIEW"/><category android:name="android.intent.category.DEFAULT"/><data android:mimeType="application/vnd.android.package-archive"/></intent-filter>
    </activity>
  </application>
</manifest>
'''
JAVA='''package dev.bikram.obtainx.p04b.target;
import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.net.Uri;
import android.content.Intent;
import java.io.InputStream;
import java.security.MessageDigest;

/** CI-only, no PackageInstaller calls, no installation privileges. */
public final class DeclineActivity extends Activity {
  @Override public void onCreate(Bundle saved) {
    super.onCreate(saved);
    String digest = "";
    String result = "refused";
    try {
      Intent intent = getIntent();
      Uri uri = intent == null ? null : intent.getData();
      if (uri == null || !"content".equals(uri.getScheme()) ||
          (intent.getFlags() & Intent.FLAG_GRANT_READ_URI_PERMISSION) == 0) {
        result = "invalid_uri_or_grant";
      } else {
        MessageDigest sha = MessageDigest.getInstance("SHA-256");
        try (InputStream input = getContentResolver().openInputStream(uri)) {
          if (input == null) throw new IllegalStateException("missing_stream");
          byte[] buf = new byte[16384];
          int n; long total = 0;
          while ((n = input.read(buf)) != -1) {
            total += n;
            if (total > 16L * 1024 * 1024) throw new IllegalStateException("oversize");
            sha.update(buf, 0, n);
          }
          if (total < 300) throw new IllegalStateException("undersize");
        }
        StringBuilder b = new StringBuilder();
        for (byte item : sha.digest()) b.append(String.format("%02x", item & 255));
        digest = b.toString();
        result = "received_and_declined";
      }
    } catch (Exception ignored) {
      result = "read_failed";
    }
    getSharedPreferences("p04b", MODE_PRIVATE).edit()
        .putString("status", result).putString("sha256", digest).commit();
    // Keep a real foreground transition long enough for ObtainX's native
    // focus-loss watcher to observe handoff before this decline returns.
    new Handler(Looper.getMainLooper()).postDelayed(new Runnable() {
      @Override public void run() { finish(); }
    }, 1500L);
  }
}
'''

def need(ok:bool, reason:str):
    if not ok:raise RuntimeError(reason)

def run(*argv:str):
    p=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE,timeout=120)
    if p.returncode:
        raise RuntimeError('P04B fixture command failed '+Path(argv[0]).name+' rc='+str(p.returncode))
    return p.stdout

def build(out:Path):
    need(out.is_absolute() and out.is_dir() and not out.is_symlink(), 'absolute fixture output directory required')
    need(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_OS')=='Linux',
         'disposable Android fixture restricted to hosted GitHub runner')
    sha=os.environ.get('GITHUB_SHA','')
    need(re.fullmatch(r'[0-9a-f]{40}',sha) is not None,'exact source SHA missing')
    sdk=Path(os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT') or '/')
    tools=sdk/'build-tools'/'35.0.0'; platform=sdk/'platforms'/'android-36'/'android.jar'
    aapt2=tools/'aapt2';d8=tools/'d8';align=tools/'zipalign';sign=tools/'apksigner'
    for x in (platform,aapt2,d8,align,sign):need(x.is_file(),'required Android SDK tool missing')
    dest=out/APK; inventory=out/'p04b_target_inventory.json'
    need(not dest.exists() and not inventory.exists(),'stale P04B fixture refused')
    builddir=out/'p04b_build';builddir.mkdir()
    manifest=builddir/'AndroidManifest.xml'; manifest.write_text(MANIFEST)
    java=builddir/'DeclineActivity.java';java.write_text(JAVA)
    classes=builddir/'classes';classes.mkdir(); dex=builddir/'dex';dex.mkdir()
    key=builddir/'fixture.jks';passwd=secrets.token_hex(16)
    try:
        run('javac','-source','8','-target','8','-cp',str(platform),'-d',str(classes),str(java))
        compiled=list(classes.rglob('*.class'))
        need(compiled and len(compiled)<10,'invalid Java target compilation')
        run(str(d8),'--min-api','26','--output',str(dex),*[str(x) for x in compiled])
        need((dex/'classes.dex').is_file(),'target Dalvik classes missing')
        unsigned=builddir/'unsigned.apk';aligned=builddir/'aligned.apk'
        run(str(aapt2),'link','-o',str(unsigned),'-I',str(platform),'--manifest',str(manifest),
            '--min-sdk-version','26','--target-sdk-version','35')
        with zipfile.ZipFile(unsigned,'a') as z:z.write(dex/'classes.dex','classes.dex')
        run(str(align),'-f','4',str(unsigned),str(aligned))
        run('keytool','-genkeypair','-noprompt','-alias','fixture','-dname','CN=ObtainX P04B Disposable CI',
            '-keyalg','RSA','-keysize','2048','-validity','2','-keystore',str(key),
            '-storepass',passwd,'-keypass',passwd)
        run(str(sign),'sign','--ks',str(key),'--ks-key-alias','fixture',
            '--ks-pass','pass:'+passwd,'--key-pass','pass:'+passwd,'--out',str(dest),str(aligned))
        run(str(sign),'verify',str(dest))
        raw=dest.read_bytes()
        need(600<len(raw)<2*1024*1024,'signed target size invalid')
        data={'schema':1,'source_sha':sha,'package':PACKAGE,'activity':ACTIVITY,
              'sha256':hashlib.sha256(raw).hexdigest(),'signed_disposable_target':True,
              'only_reads_content_uri':True,'can_install_apks':False,'physical_qualified':False}
        inventory.write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')
        print('OX_R02F_P04B_DISPOSABLE_EXTERNAL_TARGET_SIGNED_PASS',flush=True)
    finally:
        import shutil
        shutil.rmtree(builddir,ignore_errors=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    try:build(a.out);return 0
    except (RuntimeError,ValueError,OSError,subprocess.TimeoutExpired) as e:
        print('OX_R02F_P04B_TARGET_REFUSED '+str(e),file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
