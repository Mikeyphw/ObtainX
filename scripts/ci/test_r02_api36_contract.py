"""Regression, mutation, and evidence integrity tests for RT01 API36 smoke."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import subprocess

ROOT = Path(__file__).resolve().parents[2]

def load(name, path):
    spec=importlib.util.spec_from_file_location(name, ROOT/path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

audit=load('r02_api36_contract', 'scripts/ci/r02_api36_contract.py')
smoke=load('r02_api36_smoke', 'scripts/ci/r02_api36_smoke.py')

class R02Api36SafetyContracts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ox-api36-test-')
        self.root=Path(self.temp.name)
        for f in (audit.WORKFLOW,audit.SMOKE,audit.TEST,audit.DOC,audit.INHERITED_CI,
                  audit.R00_CONTRACT,audit.R00_TEST):
            dst=self.root/f;dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/f,dst)
    def tearDown(self):self.temp.cleanup()
    def mutate(self,path,old,new):
        f=self.root/path
        value=f.read_text()
        self.assertIn(old,value,'stale test mutation anchor: '+old)
        f.write_text(value.replace(old,new,1))
        self.assertNotEqual(audit.inspect(self.root),[], 'mutation not detected: '+path)
    def test_baseline_valid(self):self.assertEqual(audit.inspect(self.root),[])
    def test_r00_exact_allowlist_required(self):
        self.mutate(audit.R00_CONTRACT, "'obtainx-r02-api36.yml',", "'unknown.yml',")
    def test_r00_default_deny_must_survive(self):
        self.mutate(audit.R00_CONTRACT, 'unexpected = names - EXPECTED_WORKFLOWS',
                    'unexpected = set()')
    def test_r00_missing_gate_must_survive(self):
        self.mutate(audit.R00_CONTRACT, 'missing = EXPECTED_WORKFLOWS - names',
                    'missing = set()')
    def test_r00_workflow_inspection_must_run(self):
        self.mutate(audit.R00_CONTRACT, 'errors.extend(check_workflows(workflows))',
                    'errors.extend([])')
    def test_r00_allowlist_mutation_tests_must_exist(self):
        self.mutate(audit.R00_TEST,
                    'test_reviewed_api36_required_and_no_unknown_workflows',
                    'test_ignore_unknown_workflows')
    def test_inherited_source_ci_covered(self):self.mutate(audit.INHERITED_CI,'run: python3 scripts/ci/r02_api36_contract.py --check','run: true')
    def test_api36_not_downgradable(self):self.mutate(audit.WORKFLOW,'api-level: 36','api-level: 35')
    def test_runner_action_pinned(self):self.mutate(audit.WORKFLOW,'@a421e43855164a8197daf9d8d40fe71c6996bb0d','@main')
    def test_kvm_gate_not_skippable(self):self.mutate(audit.WORKFLOW,'test -c /dev/kvm','echo kvm-not-required')
    def test_disk_gate_not_skippable(self):self.mutate(audit.WORKFLOW,'(( available_kib >= 4 * 1024 * 1024 ))','true')
    def test_gh_source_pinned(self):self.mutate(audit.WORKFLOW,'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"','true')
    def test_release_build_forbidden(self):self.mutate(audit.WORKFLOW,'flutter build apk --debug --flavor normal --no-pub','flutter build apk --release --flavor normal --no-pub')
    def test_emulator_proof_mandatory(self):self.mutate(audit.SMOKE,"adb('shell', 'getprop', 'ro.kernel.qemu') == '1'",'True')
    def test_sdk_verification_mandatory(self):self.mutate(audit.SMOKE,"adb('shell', 'getprop', 'ro.build.version.sdk') == '36'",'True')
    def test_installed_bytes_proof_mandatory(self):self.mutate(audit.SMOKE,"installed_sha_text[0] == apk_sha",'True')
    def test_app_identity_mandatory(self):self.mutate(audit.SMOKE,"f\"package: name='{PACKAGE}'\" in badging",'True')
    def test_do_not_claim_split_e2e(self):self.mutate(audit.SMOKE,"'split_install_e2e_qualified': False","'split_install_e2e_qualified': True")
    def test_do_not_claim_release_qualification(self):self.mutate(audit.SMOKE,"'release_qualified': False","'release_qualified': True")
    def test_activity_process_proof_mandatory(self):self.mutate(audit.SMOKE,"query_main_pid() == pid",'True')
    def test_upload_allowlist_mandatory(self):self.mutate(audit.WORKFLOW,'obtainx-r02-api36/receipt.json','somewhere-else/receipt.json')
    def test_package_id_verifier_mandatory(self):self.mutate(audit.SMOKE,"'package': PACKAGE", "'package': 'other'")
    def test_docs_scope_required(self):self.mutate(audit.DOC,'NOT a split-install E2E qualification','does all installation')
    def test_fresh_probe_must_be_invoked(self):
        self.mutate(audit.SMOKE, '    verify_fresh_package_absent()\n', '    pass # bypass fresh-package proof\n')
    def test_package_listing_mandatory(self):
        self.mutate(audit.SMOKE, "'shell', 'cmd', 'package', 'list', 'packages', '--user', '0', PACKAGE", "'shell', 'getprop', 'ro.product.brand'")
    def test_exit_code_must_be_bounded(self):
        self.mutate(audit.SMOKE, 'result.returncode in (0, 1) and not stdout and not stderr', 'True')
    def test_package_inventory_must_be_empty(self):
        self.mutate(audit.SMOKE, 'need(not listing.strip()', 'need(True')
    def test_stdout_errors_must_be_visible(self):
        self.mutate(audit.SMOKE, "or result.stdout.decode(errors='replace').strip()", "or ''")
    def test_foreground_activity_proof_not_skippable(self):
        self.mutate(audit.SMOKE, "activity_proof in ('resumed', 'focused')", 'True')
    def test_foreground_activity_state_must_be_queried(self):
        self.mutate(audit.SMOKE, "adb('shell', 'dumpsys', 'activity', 'activities'", "adb('shell', 'getprop', 'ro.product.brand'")
    def test_foreground_window_state_must_be_queried(self):
        self.mutate(audit.SMOKE, "adb('shell', 'dumpsys', 'window', 'windows'", "adb('shell', 'getprop', 'ro.product.brand'")
    def test_stable_process_must_be_queried(self):
        self.mutate(audit.SMOKE, 'query_main_pid() == pid', 'True')
    def test_foreground_activity_stability_required(self):
        self.mutate(audit.SMOKE, "observe_main_activity() in ('resumed', 'focused')", 'True')
    def test_receipt_foreground_proof_mandatory(self):
        self.mutate(audit.SMOKE, "data.get('activity_proof') in ('resumed', 'focused')", 'True')

class R02Api36FreshPackageProof(unittest.TestCase):
    """Reproduce API36 pm path's absent-package exit and verify fail-closed proof."""
    def probe(self, status=1, stdout=b'', stderr=b'', listing=''):
        result=subprocess.CompletedProcess(['adb'], status, stdout, stderr)
        with patch.object(smoke.subprocess, 'run', return_value=result) as run, \
             patch.object(smoke, 'adb', return_value=listing) as listing_call:
            smoke.verify_fresh_package_absent()
            run.assert_called_once()
            listing_call.assert_called_once_with(
                'shell', 'cmd', 'package', 'list', 'packages', '--user', '0', smoke.PACKAGE)

    def test_absent_pm_path_rc1_with_independent_listing(self):
        self.probe(status=1)

    def test_absent_pm_path_rc0_with_independent_listing(self):
        self.probe(status=0)

    def test_nonfresh_pm_path_refused(self):
        with self.assertRaises(smoke.Refused):
            self.probe(status=0, stdout=b'package:/data/app/installed/base.apk')

    def test_nonfresh_package_listing_refused(self):
        with self.assertRaises(smoke.Refused):
            self.probe(status=1, listing='package:'+smoke.PACKAGE)

    def test_ambiguous_pm_path_status_refused(self):
        with self.assertRaises(smoke.Refused):
            self.probe(status=2)

    def test_ambiguous_pm_path_stderr_refused(self):
        with self.assertRaises(smoke.Refused):
            self.probe(status=1, stderr=b'Package manager unavailable')

    def test_failed_second_probe_refused(self):
        result=subprocess.CompletedProcess(['adb'], 1, b'', b'')
        with patch.object(smoke.subprocess, 'run', return_value=result), \
             patch.object(smoke, 'adb', side_effect=smoke.Refused('ADB query failed')):
            with self.assertRaises(smoke.Refused):
                smoke.verify_fresh_package_absent()

    def test_command_failure_logs_argv_and_stdout(self):
        result=subprocess.CompletedProcess(['adb'], 1, b'stdout-only reason', b'')
        with patch.object(smoke.subprocess, 'run', return_value=result):
            with self.assertRaises(smoke.Refused) as ex:
                smoke.call('adb', '-s', smoke.SERIAL, 'shell', 'pm', 'path', smoke.PACKAGE)
        self.assertIn('shell pm path', str(ex.exception))
        self.assertIn('stdout-only reason', str(ex.exception))

    def test_command_failure_logs_stderr(self):
        result=subprocess.CompletedProcess(['adb'], 2, b'', b'device offline')
        with patch.object(smoke.subprocess, 'run', return_value=result):
            with self.assertRaises(smoke.Refused) as ex:
                smoke.call('adb', '-s', smoke.SERIAL, 'get-state')
        self.assertIn('device offline', str(ex.exception))


class R02Api36ActivityProof(unittest.TestCase):
    RESUMED = ('  topResumedActivity=ActivityRecord{21c u0 '
               + smoke.COMPONENT + ' t14}')
    FOCUSED = '  mCurrentFocus=Window{123 u0 ' + smoke.COMPONENT + '}'

    def test_am_start_different_output_requires_real_activity(self):
        # A successful am-start banner on its own must NEVER prove launch.
        self.assertEqual(smoke.main_activity_proof('Starting: Intent', 'Status: ok'), '')
        self.assertEqual(smoke.launch_report('Starting: Intent\nWarning: task reused'),
                         'Starting: Intent | Warning: task reused')

    def test_resumed_activity_exact_package(self):
        self.assertEqual(smoke.main_activity_proof(self.RESUMED, ''), 'resumed')
        shortened = 'mResumedActivity: ActivityRecord{42 ' + smoke.PACKAGE + '/.MainActivity t2}'
        self.assertEqual(smoke.main_activity_proof(shortened, ''), 'resumed')

    def test_focused_activity_exact_package(self):
        self.assertEqual(smoke.main_activity_proof('', self.FOCUSED), 'focused')

    def test_foreground_unrelated_process_refused(self):
        other = 'mCurrentFocus=Window{a u0 another.app/dev.imranr.obtainium.MainActivity}'
        self.assertEqual(smoke.main_activity_proof('', other), '')
        spoof = ('mCurrentFocus=Window{1 ' + smoke.PACKAGE
                 + '.evil/dev.imranr.obtainium.MainActivity}')
        self.assertEqual(smoke.main_activity_proof('', spoof), '')

    def test_foreground_activity_text_not_in_resumed_field_refused(self):
        history = 'ActivityRecord{a ' + smoke.COMPONENT + ' t2}'
        not_top = 'mResumedActivity: ActivityRecord{b another.app/.MainActivity t3}'
        self.assertEqual(smoke.main_activity_proof(history + '\n' + not_top, ''), '')
        self.assertEqual(smoke.main_activity_proof('topResumedActivity=None',
                         'mCurrentFocus=Window{0 com.android.launcher/.Launcher}'), '')

    def test_missing_pid_may_be_transient(self):
        value = subprocess.CompletedProcess(['adb'], 1, b'', b'')
        with patch.object(smoke.subprocess, 'run', return_value=value):
            self.assertEqual(smoke.query_main_pid(), '')

    def test_ambiguous_pid_query_refused(self):
        for rc,out,err in ((0,b'123 456',b''),(2,b'',b'device offline'),(1,b'',b'oops')):
            value = subprocess.CompletedProcess(['adb'], rc, out, err)
            with patch.object(smoke.subprocess, 'run', return_value=value):
                with self.assertRaises(smoke.Refused): smoke.query_main_pid()

    def test_valid_pid_query(self):
        value = subprocess.CompletedProcess(['adb'], 0, b'4321\n', b'')
        with patch.object(smoke.subprocess, 'run', return_value=value):
            self.assertEqual(smoke.query_main_pid(), '4321')

    def emulate_launch(self, proof, start):
        with tempfile.TemporaryDirectory(prefix='rt01-hf03-integration-') as td:
            out=Path(td)/'out';out.mkdir()
            apk=Path(td)/'app-normal-debug.apk'
            blob=b'APK-source-byte-proof'*8000
            apk.write_bytes(blob)
            sdk=Path(td)/'android-sdk';tools=sdk/'build-tools'/'35.0.0';tools.mkdir(parents=True)
            (tools/'aapt').write_text('fixture')
            (tools/'apksigner').write_text('fixture')
            sha=hashlib.sha256(blob).hexdigest()
            source='a'*40;run_id='42'
            receipt={'schema':1,'status':'NOT_RUN','source_sha':source,'run_id':run_id,
                     'hosted_emulator_only':True,'physical_device_qualified':False,
                     'split_install_e2e_qualified':False,'obtainx_installer_e2e_qualified':False,
                     'release_qualified':False,'publication_allowed':False}
            (out/'receipt.json').write_text(json.dumps(receipt))
            png=b'\x89PNG\r\n\x1a\n'+b'0'*3000
            def fake_adb(*args,**kwargs):
                if args==('get-state',):return 'device'
                if args==('shell','getprop','ro.kernel.qemu'):return '1'
                if args==('shell','getprop','ro.build.version.sdk'):return '36'
                if args==('install','-t',str(apk)):return 'Success'
                if args==('shell','pm','path',smoke.PACKAGE):return 'package:/data/app/fixture/base.apk'
                if args==('shell','sha256sum','/data/app/fixture/base.apk'):
                    return sha+'  /data/app/fixture/base.apk'
                if args==('shell','am','start','-W','-n',smoke.COMPONENT):return start
                if args==('exec-out','screencap','-p'):return png
                raise AssertionError('unexpected device command '+str(args))
            def fake_call(*args,**kwargs):
                if args[1:]==('dump','badging',str(apk)):
                    return "package: name='"+smoke.PACKAGE+"' versionCode='1'"
                if args[1:]==('verify','--print-certs',str(apk)):
                    return 'Signer #1 certificate SHA-256 digest: '+'b'*64
                raise AssertionError('unexpected host command '+str(args))
            with patch.object(smoke,'host_identity',return_value=(source,run_id)),                  patch.object(smoke,'APK',apk),                  patch.object(smoke,'adb',side_effect=fake_adb),                  patch.object(smoke,'call',side_effect=fake_call),                  patch.object(smoke,'verify_fresh_package_absent'),                  patch.object(smoke,'query_main_pid',return_value='5123'),                  patch.object(smoke,'observe_main_activity',return_value=proof),                  patch.dict(smoke.os.environ,{'ANDROID_HOME':str(sdk)}),                  patch.object(smoke.time,'sleep',return_value=None):
                if proof:
                    smoke.run_emulator(out)
                    smoke.verify(out)
                    result=json.loads((out/'receipt.json').read_text())
                    self.assertEqual(result['activity_proof'],proof)
                    self.assertTrue(result['foreground_activity_verified'])
                else:
                    with self.assertRaises(smoke.Refused):smoke.run_emulator(out)
                    self.assertEqual(json.loads((out/'receipt.json').read_text())['status'],'NOT_RUN')

    def test_full_launch_nonstandard_am_stdout_requires_resumed_proof(self):
        self.emulate_launch('resumed','Starting: Intent { cmp=... }\nWarning: Activity not started, task brought to front')

    def test_full_launch_no_foreground_refused_even_if_am_status_ok(self):
        self.emulate_launch('', 'Status: ok\nComplete')


class R02Api36ReceiptProof(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ox-api36-receipt-')
        self.out=Path(self.temp.name)
        self.sha='a'*40
        self.run='12345'
        self.png=b'\x89PNG\r\n\x1a\n'+b'p'*3000
        self.app_sha='b'*64
        self.cert='c'*64
        self.out.joinpath('app_launch.png').write_bytes(self.png)
        self.receipt={
            'schema':1,'status':'PASS','source_sha':self.sha,'run_id':self.run,
            'hosted_emulator_only':True,'physical_device_qualified':False,
            'split_install_e2e_qualified':False,'obtainx_installer_e2e_qualified':False,
            'release_qualified':False,'publication_allowed':False,'api_level':36,
            'emulator_abi':'x86_64','emulator_serial':smoke.SERIAL,
            'package':smoke.PACKAGE,'activity':smoke.COMPONENT,
            'activity_proof':'resumed','foreground_activity_verified':True,
            'app_apk_sha256':self.app_sha,'installed_apk_sha256':self.app_sha,
            'debug_certificate_sha256':self.cert,
            'app_launch_png_sha256':hashlib.sha256(self.png).hexdigest(),
            'app_launch_png_bytes':len(self.png)}
        self._write()
    def _write(self):self.out.joinpath('receipt.json').write_text(json.dumps(self.receipt))
    def tearDown(self):self.temp.cleanup()
    def verified(self):
        with patch.object(smoke,'host_identity',return_value=(self.sha,self.run)):
            smoke.verify(self.out)
    def test_valid_receipt(self):self.verified()
    def test_activity_missing_receipt_refused(self):
        self.receipt.pop('activity_proof'); self._write()
        with self.assertRaises(smoke.Refused):self.verified()
    def test_activity_unverified_receipt_refused(self):
        self.receipt['foreground_activity_verified']=False; self._write()
        with self.assertRaises(smoke.Refused):self.verified()
    def test_wrong_source_refused(self):
        self.receipt['source_sha']='d'*40;self._write()
        with self.assertRaises(smoke.Refused):self.verified()
    def test_false_release_claim_refused(self):
        self.receipt['release_qualified']=True;self._write()
        with self.assertRaises(smoke.Refused):self.verified()
    def test_false_split_claim_refused(self):
        self.receipt['split_install_e2e_qualified']=True;self._write()
        with self.assertRaises(smoke.Refused):self.verified()
    def test_installed_apk_divergence_refused(self):
        self.receipt['installed_apk_sha256']='e'*64;self._write()
        with self.assertRaises(smoke.Refused):self.verified()
    def test_tampered_screenshot_refused(self):
        self.out.joinpath('app_launch.png').write_bytes(self.png+b'garbage')
        with self.assertRaises(smoke.Refused):self.verified()
    def test_unrun_receipt_refused(self):
        self.receipt['status']='NOT_RUN';self._write()
        with self.assertRaises(smoke.Refused):self.verified()
    def test_api35_refused(self):
        self.receipt['api_level']=35;self._write()
        with self.assertRaises(smoke.Refused):self.verified()

if __name__=='__main__':unittest.main()
