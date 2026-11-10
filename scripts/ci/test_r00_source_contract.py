import json
import tempfile
import unittest
from pathlib import Path
from r00_source_contract import check_private_material, check_workflows, inspect

EXAMPLE_WORKFLOW = '''name: Source contracts
on: [push]
permissions:
  contents: read
jobs:
  source:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262
'''


class R00ContractTests(unittest.TestCase):
    def test_signing_key_material_is_denied(self):
        paths = ['lib/main.dart', 'android/app/release.jks', 'android/key.properties',
                 'android/app/secret.p12', 'assets/ca-certs/isrg-root-x1.crt']
        self.assertEqual(check_private_material(paths), paths[1:4])

    def test_upstream_release_workflow_fails_closed(self):
        files = {
            'obtainx-r00-contracts.yml': EXAMPLE_WORKFLOW,
            'obtainx-r00-flutter.yml': EXAMPLE_WORKFLOW,
            'release.yml': 'on: workflow_dispatch\n',
        }
        self.assertTrue(check_workflows(files))

    def test_unpinned_actions_and_write_access_fail(self):
        files = {
            'obtainx-r00-contracts.yml': EXAMPLE_WORKFLOW.replace(
                'contents: read', 'contents: write').replace(
                'actions/checkout@11d5960a326750d5838078e36cf38b85af677262',
                'actions/checkout@v4'),
            'obtainx-r00-flutter.yml': EXAMPLE_WORKFLOW,
        }
        messages = '\n'.join(check_workflows(files))
        self.assertIn('write access', messages)
        self.assertIn('not pinned', messages)

    def test_valid_strict_workflows(self):
        files = {name: EXAMPLE_WORKFLOW for name in (
            'obtainx-r00-contracts.yml', 'obtainx-r00-flutter.yml')}
        self.assertEqual(check_workflows(files), [])

    def test_baseline_drift_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'docs').mkdir()
            (root / '.github/workflows').mkdir(parents=True)
            (root / 'docs/ROADMAP.md').write_text('roadmap', encoding='utf-8')
            (root / 'docs/R00_TEST_AUDIT.md').write_text('unqualified', encoding='utf-8')
            (root / 'docs/SECURITY_RELEASE_POLICY.md').write_text('no release', encoding='utf-8')
            (root / 'docs/DEVELOPMENT.md').write_text('dev', encoding='utf-8')
            (root / 'docs/R00_BASELINE.json').write_text(json.dumps({
                'schema_version': 1, 'upstream_sha': '1'*40, 'fork_main_sha':'1'*40,
                'upstream_repo': 'bikram-agarwal/ObtainX',
                'fork_repo': 'Mikeyphw/ObtainX', 'roadmap_sha256':'0'*64,
            }), encoding='utf-8')
            for name in ('obtainx-r00-contracts.yml', 'obtainx-r00-flutter.yml'):
                (root / '.github/workflows'/name).write_text(EXAMPLE_WORKFLOW, encoding='utf-8')
            self.assertTrue(any('roadmap digest drift' in i for i in inspect(root, validate_git=False)))


if __name__ == '__main__':
    unittest.main()
