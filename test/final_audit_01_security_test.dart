import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/app_sources/gitlab.dart';
import 'package:obtainium/custom_errors.dart';
import 'package:obtainium/http/linked_changelog_policy.dart';
import 'package:obtainium/http/origin_redirect_policy.dart';
import 'package:obtainium/providers/logs_provider.dart';
import 'package:obtainium/services/diagnostic_redaction.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

const _sentinel = 'synthetic-opaque-value-17';

class _GitLabFixture extends GitLab {
  int reads = 0;
  @override
  Future<String?> getPATIfAny(Map<String, dynamic> additionalSettings) async {
    reads++;
    return _sentinel;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  test('GitLab linked releases use a canonical header-only request', () async {
    final plan = planLinkedChangelog(
      'https://gitlab.com/group/nested/project',
      'https://gitlab.com/group/nested/project/-/releases/v1/beta',
      gitlab: true, github: false, gitlabHost: 'gitlab.com',
    );
    expect(plan.uri.pathSegments, ['api', 'v4', 'projects', 'group/nested/project', 'releases', 'v1/beta']);
    expect(plan.uri.hasQuery, isFalse);
    expect(plan.sourceHeaders, isTrue);
    expect(plan.gitlabRelease, isTrue);
    final source = _GitLabFixture();
    final headers = await source.getRequestHeaders({}, plan.uri.toString());
    expect(headers?['PRIVATE-TOKEN'], _sentinel);
    expect(plan.uri.toString(), isNot(contains(_sentinel)));
    expect(crossOriginDownloadHeaders(headers), isEmpty);
    expect(source.reads, 1);
    final blob = planLinkedChangelog(
      'https://gitlab.com/group/nested/project',
      'https://gitlab.com/group/nested/project/-/blob/main/docs/changes.md',
      gitlab: true, github: false, gitlabHost: 'gitlab.com',
    );
    expect(blob.uri.pathSegments, ['api', 'v4', 'projects', 'group/nested/project', 'repository', 'files', 'docs/changes.md', 'raw']);
    expect(blob.uri.queryParameters, {'ref': 'main'});
    expect(hasCredentialQuery(blob.uri), isFalse);
  });

  test('credentialed linked metadata refuses malformed and foreign origins', () async {
    final source = _GitLabFixture();
    const tracked = 'https://gitlab.com/group/project';
    for (final url in [
      'http://gitlab.com/group/project/-/releases',
      'https://gitlab.com.evil.test/group/project/-/releases',
      'https://gitlab.com:8443/group/project/-/releases',
      'https://name:$_sentinel@gitlab.com/group/project/-/releases',
      'https://gitlab.com/group/project/-/releases?private_token=$_sentinel',
      'https://gitlab.com/group/project/-/releases?%50rivate%5FToken=$_sentinel',
      'https://gitlab.com/group/project/-/releases?other=$_sentinel',
      'javascript:alert(1)',
      '/group/project/-/releases',
    ]) {
      expect(() => planLinkedChangelog(tracked, url,
        gitlab: true, github: false, gitlabHost: 'gitlab.com'), throwsFormatException);
    }
    await expectLater(source.getRequestHeaders({}, 'https://gitlab.com/api/v4/projects?access_token=$_sentinel'), throwsFormatException);
    expect(source.reads, 0);
    expect(await source.getRequestHeaders({}, 'https://gitlab.com.evil.test/a'), isNull);
    expect(source.reads, 0);
  });

  test('unsafe changelog navigation is refused before rendering', () {
    const base = 'https://gitlab.com/group/project';
    expect(safeChangelogNavigation(base, 'https://other.test/path?token=$_sentinel'), isNull);
    expect(safeChangelogNavigation(base, 'javascript:alert(1)'), isNull);
    expect(safeChangelogNavigation(base, '//name:$_sentinel@other.test'), isNull);
    expect(safeChangelogNavigation(base, '/public')?.toString(), 'https://gitlab.com/public');
  });

  test('GitHub API conversion is exact-origin; third-party metadata is public', () {
    final plan = planLinkedChangelog('https://github.com/org/repo',
      'https://github.com/org/repo/releases/tag/v1/beta', gitlab: false, github: true);
    expect(plan.uri.host, 'api.github.com');
    expect(plan.uri.pathSegments.last, 'v1/beta');
    expect(plan.githubRelease, isTrue);
    final foreign = planLinkedChangelog('https://github.com/org/repo',
      'https://evilgithub.com/org/repo/releases', gitlab: false, github: true);
    expect(foreign.sourceHeaders, isFalse);
    expect(foreign.githubRelease, isFalse);
  });

  test('log records redact URL credentials, opaque paths and header blocks', () {
    final fixtures = [
      'URL https://name:$_sentinel@example.test/a?other=$_sentinel#$_sentinel',
      'URL https://example.test/$_sentinel',
      'URL https%3A%2F%2Fexample.test%2F$_sentinel',
      'Authorization: Bearer $_sentinel',
      'PRIVATE-TOKEN: $_sentinel\n$_sentinel',
      '{"gitlab-creds": "$_sentinel"}',
      'headers: {X-Custom: $_sentinel}',
      'Cookie: session=$_sentinel',
      'Bearer $_sentinel\n$_sentinel',
    ];
    for (final fixture in fixtures) {
      final log = Log(fixture, LogLevel.error);
      expect(log.message, isNot(contains(_sentinel)));
      expect(log.toString(), isNot(contains(_sentinel)));
      expect(log.toMap()[messageColumn], isNot(contains(_sentinel)));
      expect(redactDiagnosticText(log.message), log.message);
      log.message = fixture;
      expect(log.message, isNot(contains(_sentinel)));
    }
    expect(Log('HTTP 403: provider refused', LogLevel.error).message,
      'HTTP 403: provider refused');
    expect(safeErrorDisplay(StateError(_sentinel)), 'StateError');
    expect(safeErrorDisplay(ObtainiumError('Download refused', url: 'https://example.test/$_sentinel')), isNot(contains(_sentinel)));
    expect(boundedDiagnosticText(List.filled(40000, 'x').join()), contains('withheld'));
  });

  test('new SQLite log writes and legacy reads never expose synthetic credentials', () async {
    final directory = await Directory.systemTemp.createTemp('ox-final-audit-log-');
    await databaseFactory.setDatabasesPath(directory.path);
    addTearDown(() async {
      await LogsProvider.close();
      await directory.delete(recursive: true);
    });
    final legacy = await openDatabase(dbPath, version: 1, onCreate: (db, _) async {
      await db.execute('CREATE TABLE logs (_id INTEGER PRIMARY KEY AUTOINCREMENT, level INTEGER NOT NULL, message TEXT NOT NULL, timestamp INTEGER NOT NULL)');
    });
    await legacy.insert(logTable, {levelColumn: LogLevel.error.index, messageColumn: _sentinel, timestampColumn: 123});
    await legacy.close();
    final logs = LogsProvider(runDefaultClear: false);
    final created = await logs.add('PRIVATE-TOKEN: $_sentinel', level: LogLevel.error);
    final database = await logs.getDB();
    final stored = await database.query(logTable, where: '$idColumn = ?', whereArgs: [created.id]);
    expect(stored.single[messageColumn], isNot(contains(_sentinel)));
    final entries = await logs.get();
    expect(entries.length, 2);
    expect(entries.map((e) => e.toString()).join('\n'), isNot(contains(_sentinel)));
    expect(entries.any((e) => e.message.contains('legacy diagnostic withheld')), isTrue);
  });
}
