"""Source wiring sentinels; Dart behavioral tests are the runtime authority."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]

def text(name):
    return (ROOT / name).read_text()

class FinalAudit02Contract(unittest.TestCase):
    def test_digest_reaches_byte_verifier(self):
        for marker in ('expectedSha256: sourceAssetSha256(app, asset)',
                       'expectedSha256: downloadRelease.expectedSha256',
                       'expectedSha256: sourceAssetSha256(app, fileUrl)'):
            self.assertIn(marker, text('lib/providers/apps_provider_install.dart'))
        self.assertIn('digest != expectedSha256', text('lib/services/r03_download_engine.dart'))
        self.assertIn('release.expectedSha256', text('lib/version/app_version.dart'))

    def test_pause_uses_committed_bytes_and_identity(self):
        src = text('lib/services/r03_download_engine.dart')
        self.assertIn('!await _verifyBlocks(part, saved.blocks)', src)
        self.assertLess(src.index('await _truncateTo(part, saved.validatedBytes)'),
                        src.index('throw R03PausedException(saved.jobId)'))
        self.assertIn('failureTransferId: (error)', text('lib/providers/apps_provider_install.dart'))

    def test_local_archive_operation_precedes_private_copy(self):
        src = text('lib/services/r02_local_archive_import.dart')
        self.assertLess(src.index('await timeline.beginLocalArchive()'), src.index("('copy', {"))
        self.assertIn('await timeline.bindLocalArchive(', src)
        self.assertIn('await timeline.settlePreparation(', src)

    def test_export_is_bounded_and_transactional(self):
        src = text('lib/services/r11_history.dart')
        self.assertIn('256 * 1024 * 1024', src)
        self.assertIn('part.create(exclusive: true)', src)
        self.assertIn('await part.rename(destination.path)', src)
        self.assertIn('if (!published && await part.exists()) await part.delete()', src)
        self.assertIn('visitForExport', text('lib/services/r07_activity_catalog.dart'))

if __name__ == '__main__':
    unittest.main()
