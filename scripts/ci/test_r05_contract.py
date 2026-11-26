#!/usr/bin/env python3
"""Negative/mutation probes of the consolidated R05 source contract."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('r05_contract',ROOT/'scripts/ci/r05_contract.py')
contract=importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(contract)

class R05ContractMutation(unittest.TestCase):
    def mutation(self,path:str,needle:str):
        with tempfile.TemporaryDirectory(prefix='r05-mut-') as directory:
            target=Path(directory)
            for p in (*contract.FILES, *contract.ANDROID_CI):
                dst=target/p;dst.parent.mkdir(parents=True,exist_ok=True)
                dst.write_bytes((ROOT/p).read_bytes())
            victim=target/path
            data=victim.read_text(encoding='utf8')
            self.assertIn(needle,data)
            victim.write_text(data.replace(needle,'R05_REMOVED_BY_MUTATION',1),encoding='utf8')
            self.assertNotEqual(contract.verify(target),0)

    def test_source_swap_before_handoff_is_rejected(self):
        self.mutation('lib/providers/apps_provider_install.dart', 'if (!_r05ListingStillBound(attempt) || getInstaller().modeKey != attempt.backend)')
    def test_historical_success_cannot_advance_replacement_release(self):
        self.mutation('lib/providers/apps_provider_install.dart', 'return _r05ListingStillBound(attempt);')
    def test_remove_evidence_gate(self):
        self.mutation('lib/services/r05_operation_receipt.dart',
                      'evidence.packageName != packageId')
    def test_late_attempt_cannot_confirm(self):
        self.mutation('lib/services/r05_operation_receipt.dart','evidence.attemptId != id')
    def test_installed_bytes_cannot_be_ignored(self):
        self.mutation('lib/services/r05_operation_receipt.dart','_r05SameDigests(selectedApkSha256, evidence.installedApkSha256)')
    def test_installed_signer_set_cannot_be_ignored(self):
        self.mutation('lib/services/r05_operation_receipt.dart','_r05SameDigests(archiveSignerSet, evidence.installedSignerSet)')
    def test_download_channel_cannot_be_relabelled(self):
        self.mutation('lib/providers/apps_provider_install.dart','provenance.channelFingerprint != r11ChannelFingerprint(app)')
    def test_archive_selection_cannot_change(self):
        self.mutation('lib/providers/apps_provider_install.dart','entry.value.sha256 == plan.selectedMembers[entry.key].sha256')
    def test_member_digest_cannot_change(self):
        self.mutation('lib/providers/apps_provider_install.dart','plannedMembers[i].sha256 != hashes[i]')
    def test_remove_nonmonotonic_receipt_check(self):
        self.mutation('lib/services/r05_operation_receipt.dart','if (time.isBefore(updatedUtc))')
    def test_remove_private_app_storage(self):
        self.mutation('lib/services/r05_operation_journal.dart',
                      'getApplicationSupportDirectory()')
    def test_remove_atomic_write(self):
        self.mutation('lib/services/r05_operation_journal.dart',
                      'stage.rename(target.path)')
    def test_remove_durable_source_precommit(self):
        self.mutation('lib/providers/apps_provider_install.dart',
                      'final r05 = await _r05BeginAttempt(')
    def test_remove_background_future_handler(self):
        self.mutation('lib/providers/apps_provider_install.dart',
                      'Future<void> _r05TrackBackgroundInstall(')
    def test_remove_signed_local_reconciliation(self):
        self.mutation('lib/services/r02_local_archive_import.dart',
                      'byteEvidenceQualified: exactBytes')
    def test_remove_crash_recovery(self):
        self.mutation('lib/providers/apps_provider_lifecycle.dart',
                      'R05OperationJournal.instance.recoverInterruptedOnce()')
    def test_remove_review_route(self):
        self.mutation('lib/pages/settings.dart','R07ActivityCenterPage()')
    def test_remove_hosted_flutter_regression(self):
        self.mutation('.github/workflows/obtainx-r00-flutter.yml',
                      'flutter test --no-pub test/r05_operation_receipt_test.dart')
    def test_remove_android_risk_scope(self):
        self.mutation('.github/workflows/obtainx-r02-rt02c.yml',
                      "scripts/ci/obtainx_ci_policy.py plan --head")

    def test_cannot_retarget_required_ci_away_from_main(self):
        self.mutation('config/delivery-required-ci.json',
                      '"base_branch": "main"')

if __name__=='__main__':unittest.main(verbosity=2)
