#!/usr/bin/env python3
"""Original R03 source, completion, source-routing and hosted-CI contract."""
from __future__ import annotations
import argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def verify(root:Path=ROOT)->int:
    def read(p):return (root/p).read_text(encoding='utf8')
    engine=read('lib/services/r03_download_engine.dart')
    provider=read('lib/providers/apps_provider.dart')
    tests=read('test/r03_download_engine_test.dart')
    legacy=read('test/overall_optimization_test.dart')
    scope=read('scripts/ci/obtainx_ci_policy.py')
    contracts=read('.github/workflows/obtainx-r00-contracts.yml')
    flutter=read('.github/workflows/obtainx-r00-flutter.yml')
    doc=read('docs/R03_DOWNLOAD_PERSISTENCE.md')
    failures=[]
    def assert_has(condition,why):
        if not condition: failures.append(why)
    for word in ('r03ContentRange(', 'r03StrongEtag(', 'sourceFingerprint',
        'validatedBytes', 'finalDigest', 'sourceFingerprint', 'R03Stage.cancelled',
        '_verifyBlocks(', '_truncateTo(', 'FileMode.append', 'HttpStatus.partialContent',
        'HttpHeaders.contentRangeHeader','if-range', 'r03CanRetryHttpStatus(',
        'r03RetryAfterSeconds(', 'await _sha256File(part)',
        'await part.rename(destination.path)', 'sourceFingerprint: jobId',
        'isCancelled()', 'response.compressionState',
        'await journalDirectory.create(recursive: true)'):
        assert_has(word in engine,'engine lost '+word)
    assert_has('final range = r03ContentRange(response.headers.value(HttpHeaders.contentRangeHeader))' in engine,
        '206 resume must actually parse the strict content range')
    assert_has("eligibleForResume = await _verifyBlocks(part, previous.blocks)" in engine,
        'resume must actually validate block digests')
    assert_has("..['if-range'] = previous.ifRange!" in engine,
        'resume must send actual If-Range header')
    assert_has("if (input['validatedBytes'] != blocks.length * r03ChunkBytes)" in engine,
        'journal must bind validated offset to block inventory')
    assert_has('finalDigest: digest, completedBytes: received' in engine,
        'terminal receipt must store verified bytes and digest')
    assert_has('_activeExpectedDigest[key] != expectedSha256' in engine and
        '_activeExpectedDigest[key] = expectedSha256' in engine,
        'active download can bypass a conflicting trusted digest')
    assert_has("whenComplete(() => _active.remove(key))" not in
        engine.split('unawaited(next.then<void>', 1)[-1],
        'unhandled failed Future returned by active cleanup')
    assert_has(engine.count("if (isCancelled()) throw const R03InvalidEntityException('cancelled');") >= 3,
        'cancellation checks must remain before and after transfer')
    assert_has("url.toString(), destination.absolute.path" in engine,
        'R03 identity missing URL/path fingerprint')
    assert_has('finalOrigin: currentOrigin' in engine,
        'R03 final redirect origin missing')
    assert_has('R03DownloadEngine(' in provider and
        'r03_download_engine.dart' in provider and
        'await engine.download(' in provider,
        'production provider bypasses R03 engine')
    assert_has('downloadFileWithRetry(' in provider and
        'r03CanRetryHttpStatus(code)' in provider and
        'cancellationToken.whenCancelled' in provider,
        'retry/notification cancellation bypasses R03')
    assert_has('await getApplicationSupportDirectory()' in provider,
        'journal must use app-private storage')
    assert_has('} catch (_) {\n    // The first GET can fail while waiting for response headers.' in provider and
        'cancellationToken?.throwIfCancelled();\n    rethrow;\n  } finally {' in provider,
        'header cancellation must retain canonical cancellation exception')
    assert_has("MethodChannel('plugins.flutter.io/path_provider')" in legacy and
        "call.method != 'getApplicationSupportDirectory'" in legacy and
        "return '${directory.path}/r03-private-support'" in legacy,
        'integrated tests must mock private support path, not bypass journal')
    assert_has('orphan .part cannot authorize Range' in legacy and
        "expect(ranges, [null], reason: 'no verified .part block')" in legacy,
        'orphan parts must never authorize unsafe Range')
    assert_has('unsolicited HTTP $responseCode never publishes an APK' in legacy and
        "'HTTP_ERROR'" in legacy,
        'unsolicited partial and transient HTTP failures must not publish')
    assert_has("_waitForConcurrentDownload(" not in provider,
        'old unowned part-file polling retained')
    assert_has('length == fullContentLength' not in provider,
        'old length-only cache qualification retained')
    assert_has("'lib/providers/apps_provider.dart'" in scope and
        "'lib/services/r03_*'" in scope and "'test/r03_*'" in scope,
        'R03 risk paths are not full CI gated')
    for p in ('.github/workflows/obtainx-r02-api36.yml',
              '.github/workflows/obtainx-r02-rt02.yml',
              '.github/workflows/obtainx-r02-rt02b.yml',
              '.github/workflows/obtainx-r02-rt02c.yml'):
        src=read(p)
        for expected in ("- 'lib/services/r03_*'", "- 'test/r03_*'",
                         "- 'lib/providers/apps_provider.dart'"):
            assert_has(expected in src,p+' missing full hosted scope '+expected)
    assert_has('python3 -B scripts/ci/r03_contract.py --check' in contracts,
        'R03 Python contract is not executed by hosted CI')
    assert_has('flutter test --no-pub test/r03_download_engine_test.dart' in flutter,
        'R03 live HTTP mock tests are not executed before Android build')
    assert_has("flutter analyze lib test" in flutter,
        'R03 requires full hosted analyzer')
    for name in ('strict 206 Content-Range', 'after cancellation',
                 'ignored Range response', 'changed ETag',
                 'expected digest mismatch', 'no content-length',
                 'two clients for same job', '302 redirect', '416 on resumed range', '401/403/410/416/429/5xx',
                  'conflicting concurrent trusted digests', 'unverified in-flight transfer'):
        assert_has(name in tests,'mock HTTP coverage missing '+name)
    assert_has('NOT_QUALIFIED' in doc and 'R04' in doc,
        'R03 acceptance boundary incorrectly claimed')
    if failures:
        for failure in failures:print('OX_R03_CONTRACT_REFUSED: '+failure,flush=True)
        return 1
    print('OX_R03_ORIGINAL_PHASE_SOURCE_CONTRACT_PASS',flush=True)
    return 0

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check',action='store_true')
    ap.add_argument('--root',type=Path,default=ROOT)
    args=ap.parse_args()
    return verify(args.root)
if __name__=='__main__':raise SystemExit(main())
