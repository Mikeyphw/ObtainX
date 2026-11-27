"""Source-level negative contracts; Dart runtime evidence is a separate gate."""
from pathlib import Path
import unittest
from obtainx_ci_policy import classify

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return (ROOT / path).read_text(encoding='utf-8')


def linked_errors(text):
    start = text.index('Future<String?> _loadLinkedChangeLog(')
    end = text.index('String resolveChangeLogImageSrc(', start)
    loader = text[start:end]
    return [item for item in (
        'credential query injected' if 'private_token' in loader or 'getPATIfAny' in loader else '',
        'exact route missing' if 'planLinkedChangelog(' not in loader or "'GET', plan.uri, headers, followRedirects: false" not in loader else '',
        'source rewrite allowed' if '.sourceRequest(' in loader else '',
        'header gate missing' if 'if (plan.sourceHeaders)' not in loader or 'getRequestHeaders(merged, plan.uri.toString())' not in loader else '',
    ) if item]


def log_errors(text):
    return [item for item in (
        'write redaction absent' if 'set message(String value) => _message = boundedDiagnosticText(value)' not in text else '',
        'legacy redaction absent' if 'map[redactionColumn] == diagnosticRedactionVersion' not in text or '[legacy diagnostic withheld:' not in text else '',
        'safe persistence absent' if 'insert(logTable, l.toMap())' not in text else '',
        'legacy schema mark absent' if 'add column $redactionColumn integer not null default 0' not in text else '',
        'raw exception forwarded' if 'diagnosticErrorCategory(error)' not in text or '$error' in text or '$stack' in text else '',
    ) if item]


class FinalAudit01Contract(unittest.TestCase):
    def test_linked_loader_and_mutations(self):
        s = read('lib/pages/apps.dart')
        self.assertEqual(linked_errors(s), [])
        for before, after in (
            ('planLinkedChangelog(', 'bypass('),
            ('plan.uri, headers, followRedirects: false', 'plan.uri, headers, followRedirects: true'),
            ('if (plan.sourceHeaders)', 'if (true)'),
            ('final plan = planLinkedChangelog(', "final private_token = 'synthetic'; final plan = planLinkedChangelog("),
        ):
            self.assertIn(before, s)
            with self.subTest(before=before):
                self.assertTrue(linked_errors(s.replace(before, after, 1)))
        self.assertIn('safeChangelogNavigation(app.url, href)', s)
        self.assertIn('safeChangesUrl.toString()', s)

    def test_exact_header_guard_precedes_secret_lookup(self):
        s = read('lib/app_sources/gitlab.dart').split('Future<Map<String, String>?> getRequestHeaders(', 1)[1]
        self.assertLess(s.index('hasCredentialQuery(uri)'), s.index('await getPATIfAny('))
        self.assertLess(s.index('sameRequestOrigin(uri,'), s.index('await getPATIfAny('))
        self.assertIn("'PRIVATE-TOKEN': ?pat", s)
        self.assertNotIn('private_token', s)

    def test_log_boundary_and_mutations(self):
        s = read('lib/providers/logs_provider.dart')
        self.assertEqual(log_errors(s), [])
        for before, after in (
            ('_message = boundedDiagnosticText(value)', '_message = value'),
            ('map[redactionColumn] == diagnosticRedactionVersion', 'true'),
            ('add column $redactionColumn integer not null default 0', 'add column $redactionColumn integer not null default 1'),
            ('diagnosticErrorCategory(error)', '$error'),
        ):
            self.assertIn(before, s)
            with self.subTest(before=before):
                self.assertTrue(log_errors(s.replace(before, after, 1)))
        self.assertIn('safeErrorDisplay(e)', read('lib/custom_errors.dart'))
        self.assertIn('raw details withheld', read('lib/main.dart'))

    def test_security_changes_require_full_hosted_gate(self):
        for name in ('lib/http/linked_changelog_policy.dart', 'lib/services/diagnostic_redaction.dart',
                     'lib/providers/logs_provider.dart', 'scripts/ci/r12_device_evidence.py',
                     'test/final_audit_01_security_test.dart', 'scripts/ci/test_final_audit_01_contract.py'):
            with self.subTest(name=name):
                self.assertTrue(classify([name])['full_flutter'])
