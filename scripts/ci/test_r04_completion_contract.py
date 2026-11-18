#!/usr/bin/env python3
"""Adversarial mutation suite for all new R04 security and history boundaries."""
from __future__ import annotations
import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('r04_completion_contract',
    ROOT/'scripts/ci/r04_completion_contract.py')
MODULE=importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

class R04FinalMutationTests(unittest.TestCase):
    def mutated(self, rel:str, before:str, after:str):
        with tempfile.TemporaryDirectory(prefix='ox-r04-final-mut-') as directory:
            root=Path(directory)
            for path in MODULE.FILES:
                target=root/path
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes((ROOT/path).read_bytes())
            victim=root/rel
            text=victim.read_text(encoding='utf-8')
            self.assertEqual(text.count(before),1,(rel,before))
            victim.write_text(text.replace(before,after,1),encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertNotEqual(MODULE.verify(root),0)

    def test_remove_redirect_token_stripping(self):
        self.mutated('lib/providers/source_provider.dart',
          'r04ArtifactStorageHeaders(requestHeaders)', 'requestHeaders')
    def test_remove_storage_host_policy(self):
        self.mutated('lib/providers/source_provider.dart',
          'r04ValidateArtifactRedirect(currentUrl, nextUrl)', 'nextUrl.toString()')
    def test_allow_unsuccessful_history_run(self):
        self.mutated('lib/services/r04_actions_history_catalog.dart',
          'run not successful; not installable', 'run succeeded')
    def test_remove_id_selection(self):
        self.mutated('lib/services/r04_github_actions.dart',
          'selectedArtifactId != null && id != selectedArtifactId', 'false')
    def test_disable_sha_binding(self):
        self.mutated('lib/services/r04_github_actions.dart',
          'commit SHA changed after manual selection', 'SHA not compared')
    def test_allow_unpinned_source_transport(self):
        self.mutated('lib/app_sources/github.dart',
          'Actions source requires direct HTTPS and certificate validation', 'insecure allowed')
    def test_remove_private_api_media_type(self):
        self.mutated('lib/app_sources/github.dart',
          "headers[HttpHeaders.acceptHeader] = 'application/vnd.github+json';",
          "headers[HttpHeaders.acceptHeader] = 'application/octet-stream';")
    def test_required_ci_policy_cannot_disable_pr_gate(self):
        self.mutated('config/delivery-required-ci.json',
          '"event": "pull_request"', '"event": "push"')
    def test_required_ci_policy_cannot_swap_workflow_id(self):
        self.mutated('config/delivery-required-ci.json',
          '"workflow_id": 413437262', '"workflow_id": 413437263')
    def test_stacked_r05_pr_base_must_match_committed_policy(self):
        # Mutate the actual CI policy, not the assertion itself. This must
        # fail closed while keeping all six exact workflow ID gates intact.
        self.mutated('config/delivery-required-ci.json',
          '"base_branch": "feature/obtainx-r04-actions-source-native-20261115"',
          '"base_branch": "feature/obtainx-r03-resumable-download-engine-20261115"')
    def test_skip_archive_verification(self):
        self.mutated('lib/providers/apps_provider_install.dart',
          'await verifyR04ActionsArchiveBeforeExtraction(',
          'await disableR04Verification(')
    def test_remove_expired_receipt_gate(self):
        self.mutated('lib/services/r04_actions_archive_integrity.dart',
          'expiresAt == null || !expiresAt.isAfter(DateTime.now().toUtc())',
          'false')
    def test_remove_persisted_expiry_receipt(self):
        self.mutated('lib/app_sources/github.dart',
          "'expiresAt': archive.expiresAt.toUtc().toIso8601String()",
          "'expiresAt': null")
    def test_remove_live_redirect_host_check(self):
        self.mutated('scripts/ci/r04_live_acceptance.py',
          'def trusted_storage_url(url: str) -> bool:',
          'def trust_any_storage(url: str) -> bool:')
    def test_remove_live_no_pat_storage_boundary(self):
        self.mutated('scripts/ci/r04_live_acceptance.py',
          "headers=api_headers if hop==0 else {'Accept':'application/octet-stream'}",
          'headers=api_headers')
    def test_remove_live_verification_hash(self):
        self.mutated('scripts/ci/r04_live_acceptance.py',
          "receipt['zip_sha256']", "receipt['missing']")
    def test_remove_history_dropdown_refresh(self):
        self.mutated('lib/components/generated_form_renderer.dart',
          'formInputs[r][e] = KeyedSubtree(',
          'formInputs[r][e] = const SizedBox.shrink(')
    def test_remove_history_ui_action(self):
        self.mutated('lib/app_sources/github.dart',
          'assistAction: _browseR04ActionsHistory',
          'assistAction: null')
    def test_remove_fluter_ui_regression(self):
        self.mutated('.github/workflows/obtainx-r00-flutter.yml',
          'flutter test --no-pub test/r04_actions_history_test.dart',
          'echo tests bypassed')
    def test_remove_android_risk_path(self):
        self.mutated('.github/workflows/obtainx-r02-api36.yml',
          "- 'lib/providers/source_provider.dart'", "- 'docs/other.dart'")

if __name__ == '__main__':
    unittest.main(verbosity=2)
