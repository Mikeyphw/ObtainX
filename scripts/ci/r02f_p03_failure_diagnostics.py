#!/usr/bin/env python3
"""Bounded, allowlisted error categories for failed hosted P03 Flutter tests.

No log fragments, Dart error arguments, Android package inventory, paths,
package names, URLs, stack traces or tokens are emitted or uploaded.
This module NEVER certifies Android runtime or installation success.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re

NAME = 'r02f-p03-failure-diagnostics.json'
STATUS = 'FAILED_HOSTED_FLUTTER_P03_NOT_QUALIFIED'
STAGES = (
    'OX_P03_DART_STAGE=APP_ROUTE_OWNER_SURVIVED',
    'OX_P03_DART_STAGE=PRODUCTION_PROVIDER_INSTALL_STARTED',
    'OX_P03_DART_STAGE=ANDROID_APPROVAL_PENDING',
    'OX_P03_DART_STAGE=REAL_APP_PAGE_CANCEL_TAPPED',
    'OX_P03_DART_STAGE=APP_OWNED_CANCEL_RESULT_VERIFIED',
)
CATEGORIES = (
    ('P03_FIXTURE_SHA_MISSING', 'P03 fixture SHA256 missing'),
    ('P03_FIXTURE_HTTP_REFUSED', 'P03 fixture HTTP refused'),
    ('P03_FIXTURE_INTEGRITY', 'P03 source-bound APK integrity failed'),
    ('P03_PROVIDER_INIT', 'ObtainX app provider initialization refused'),
    ('P03_TRANSLATIONS_MISSING', 'App translations unavailable'),
    ('P03_CANCEL_UI_MISSING', 'Real AppPage must expose app-owned cancellation'),
    ('P03_CANCEL_UI_LOST', 'Actual production AppPage lost its Cancel action'),
    ('P03_APPROVAL_TIMEOUT', 'P03 owned session never reached Android pending user approval'),
    ('P03_HOST_FOREGROUND_REFUSED', 'Host did not verify approval screen before ObtainX foreground'),
    ('P03_CANCEL_AFTER_SUCCESS', 'App provider cannot report a successful install after UI Cancel'),
    ('P03_NATIVE_ROLLBACK_UNPROVEN', 'Native abandon and original APK integrity must be established'),
    ('P03_NATIVE_TERMINAL_UNKNOWN', 'OX_P03_DART_NATIVE_TERMINAL=UNKNOWN'),
    ('P03_NATIVE_TERMINAL_ERROR', 'OX_P03_DART_NATIVE_TERMINAL=ERROR'),
    ('P03_NATIVE_TERMINAL_MISSING', 'OX_P03_DART_NATIVE_TERMINAL=MISSING'),
    ('P03_NATIVE_TERMINAL_UNEXPECTED', 'OX_P03_DART_NATIVE_TERMINAL=UNEXPECTED'),
    ('P03_FLUTTER_TEST_TIMEOUT', 'TimeoutException'),
    ('P03_DART_NO_SUCH_METHOD', 'NoSuchMethodError'),
    ('P03_DART_NULL_ASSERTION', 'Null check operator used on a null value'),
    ('P03_ANDROID_PLATFORM_EXCEPTION', 'PlatformException'),
    ('P03_FIXTURE_SOCKET_EXCEPTION', 'SocketException'),
    ('P03_WIDGET_ASSERTION', 'TestFailure'),
    ('P03_WIDGET_ASSERTION', 'Test failed. See exception logs above.'),
    ('P03_GRADLE_FAILURE', 'FAILURE: Build failed with an exception.'),
)
ALLOWED_STAGES = frozenset(('FLUTTER_STARTING','GRADLE_BUILD','APP_ROUTE_OWNER_SURVIVED',
 'PRODUCTION_PROVIDER_INSTALL_STARTED','APPROVAL_PENDING','UI_CANCEL_TAPPED',
 'UI_CANCEL_COMPLETED','UNKNOWN'))


def classify(log_text: str, process_rc: int | None, last_runner_stage: str,
             source_sha: str, run_id: str, log_bytes: bytes) -> dict:
    if not isinstance(log_text,str) or not isinstance(log_bytes,bytes):
        raise ValueError('diagnostic input type invalid')
    if not re.fullmatch(r'[0-9a-f]{40}',source_sha):
        raise ValueError('invalid source pin')
    if not re.fullmatch(r'[0-9]{1,16}',str(run_id)):
        raise ValueError('invalid Actions run identifier')
    marker_counts = [log_text.count(m) for m in STAGES]
    present = [i+1 for i,n in enumerate(marker_counts) if n == 1]
    duplicate = any(n > 1 for n in marker_counts)
    relevant = log_text[-262144:]
    categories = sorted({name for name,needle in CATEGORIES if needle in relevant})
    if not categories:
        categories = ['P03_UNKNOWN_FLUTTER_FAILURE']
    stage = last_runner_stage if last_runner_stage in ALLOWED_STAGES else 'UNKNOWN'
    # The private log is only hashed, not uploaded; codes are fixed strings.
    return {
        'schema':1,
        'status':STATUS,
        'head_sha':source_sha,
        'run_id':str(run_id),
        'flutter_exit_nonzero':process_rc != 0,
        'flutter_success_marker_seen':'All tests passed!' in log_text,
        'last_runner_stage':stage,
        'unique_dart_marker_indices':present,
        'duplicate_dart_stage_markers':duplicate,
        'failure_categories':categories,
        'private_log_sha256':hashlib.sha256(log_bytes).hexdigest(),
        'private_log_byte_count':len(log_bytes),
        'raw_logs_uploaded':False,
        'android_live_audit_passed':False,
        'physical_device_qualified':False,
        'release_qualified':False,
    }


def write_failure(out:Path, log_path:Path, process_rc:int|None,
                  last_runner_stage:str, source_sha:str, run_id:str) -> dict:
    if not out.is_absolute() or log_path.is_symlink() or not log_path.is_file():
        raise ValueError('unsafe private log path')
    log_bytes=log_path.read_bytes()
    diag=classify(log_bytes.decode('utf-8','replace'),process_rc,last_runner_stage,
                  source_sha,str(run_id),log_bytes)
    path=out/NAME
    if path.exists() or path.is_symlink():
        raise ValueError('stale P03 failure diagnostic receipt refused')
    raw=(json.dumps(diag,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8')
    if len(raw)>4096:
        raise ValueError('bounded diagnostic oversize')
    path.write_bytes(raw)
    print('OX_R02F_P03_DIAGNOSTIC status=FAILED stage='+diag['last_runner_stage']+
          ' categories='+','.join(diag['failure_categories'])+
          ' markers='+','.join(map(str,diag['unique_dart_marker_indices']))+
          ' duplicate='+str(diag['duplicate_dart_stage_markers']).lower()+
          ' bytes='+str(diag['private_log_byte_count'])+
          ' log_sha256='+diag['private_log_sha256'],flush=True)
    return diag
