#!/usr/bin/env python3
"""R03 adversarial source mutation tests. A suite cannot pass by self-skipping."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('r03_contract',HERE/'r03_contract.py')
M=importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
ROOT=HERE.parents[1]
PATHS=[
 'lib/services/r03_download_engine.dart','lib/providers/apps_provider.dart',
 'test/r03_download_engine_test.dart','scripts/ci/obtainx_ci_policy.py',
 '.github/workflows/obtainx-r00-contracts.yml',
 '.github/workflows/obtainx-r00-flutter.yml',
 '.github/workflows/obtainx-r02-api36.yml',
 '.github/workflows/obtainx-r02-rt02.yml',
 '.github/workflows/obtainx-r02-rt02b.yml',
 '.github/workflows/obtainx-r02-rt02c.yml',
 'docs/R03_DOWNLOAD_PERSISTENCE.md',
 'test/overall_optimization_test.dart',
]

class R03MutationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ROOT/'lib/services/r03_download_engine.dart').is_file():
            raise AssertionError('R03 production source missing; test must not silently skip')
    def mutated(self,path,old,new):
        with tempfile.TemporaryDirectory(prefix='ox-r03-mutate-') as tmp:
            base=Path(tmp)
            for p in PATHS:
                target=base/p
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes((ROOT/p).read_bytes())
            source=(base/path).read_text()
            self.assertIn(old,source,old)
            (base/path).write_text(source.replace(old,new,1))
            self.assertNotEqual(M.verify(base),0)
    def test_remove_range_validation(self):
        self.mutated(PATHS[0],'final range = r03ContentRange(response.headers.value(HttpHeaders.contentRangeHeader))','final range = null')
    def test_remove_journal_offset_validation(self):
        self.mutated(PATHS[0],"if (input['validatedBytes'] != blocks.length * r03ChunkBytes)", 'if (false)')
    def test_remove_final_digest(self):
        self.mutated(PATHS[0],'finalDigest: digest, completedBytes: received','finalDigest: null, completedBytes: received')
    def test_remove_source_fingerprint(self):
        self.mutated(PATHS[0],'sourceFingerprint: jobId','sourceFingerprint: overwritten')
    def test_remove_real_resume_validator(self):
        self.mutated(PATHS[0],"..['if-range'] = checkpoint.ifRange!", "..['wrong-range'] = checkpoint.ifRange!")
    def test_remove_verified_blocks(self):
        self.mutated(PATHS[0],'eligibleForResume = await _verifyBlocks(part, previous.blocks)', 'eligibleForResume = true')
    def test_remove_active_digest_policy(self):
        self.mutated(PATHS[0], '_activeExpectedDigest[key] != expectedSha256', 'false')
    def test_remove_runtime_check(self):
        self.mutated(PATHS[0],"if (isCancelled()) throw const R03InvalidEntityException('cancelled');",'if (false) throw const R03InvalidEntityException(\"cancelled\");')
    def test_remove_atomic_publish(self):
        self.mutated(PATHS[0],'await part.rename(destination.path)',
                     'await part.delete()')
    def test_old_engine_bypass(self):
        self.mutated(PATHS[1],'await engine.download(', 'await oldDownload(')
    def test_remove_private_journal(self):
        self.mutated(PATHS[1],'await getApplicationSupportDirectory()',
                     'await getDownloadsDirectory()')
    def test_remove_cancelled_header_exception_translation(self):
        self.mutated(PATHS[1],
            '    cancellationToken?.throwIfCancelled();\n    rethrow;\n  } finally {',
            '    rethrow;\n  } finally {')
    def test_remove_private_path_provider_mock(self):
        self.mutated(PATHS[-1],
            "return '${directory.path}/r03-private-support'", 'return null')
    def test_remove_orphan_range_refusal(self):
        self.mutated(PATHS[-1],
            "expect(ranges, [null], reason: 'no verified .part block')",
            'expect(ranges, isNotEmpty)')
    def test_remove_retry_stop(self):
        self.mutated(PATHS[1],'r03CanRetryHttpStatus(code)', 'true')
    def test_remove_mock_http_suite(self):
        self.mutated(PATHS[5],
            'flutter test --no-pub test/r03_download_engine_test.dart',
            'echo no tests')
    def test_remove_python_contract(self):
        self.mutated(PATHS[4],
            'python3 -B scripts/ci/r03_contract.py --check', 'echo ignored')
    def test_remove_ci_risk_scope(self):
        self.mutated(PATHS[3],"'lib/services/r03_*'", "'docs/r03_*'")
    def test_remove_rt02c_path_gate(self):
        self.mutated(PATHS[9],"scripts/ci/obtainx_ci_policy.py plan --head", "- 'docs/r03_*'")

if __name__=='__main__': unittest.main(verbosity=2)
