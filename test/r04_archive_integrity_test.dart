import 'dart:io';
import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/services/r04_actions_archive_integrity.dart';

const _source = 'https://github.com/example/repo';
const _artifact = 'https://api.github.com/repos/example/repo/actions/artifacts/41/zip';
const _name = 'android-arm64-apk.zip';
const _sha = 'aabbccddeeff00112233445566778899aabbccdd';

Map<String, dynamic> _settings(String digest) => {
  'r04GitHubSourceMode': 'actions',
  r04ActionsArchiveEvidenceKey: {
    'sourceUrl': _source,
    'archiveUrl': _artifact,
    'archiveName': _name,
    'archiveSha256': digest,
    'artifactId': 41,
    'runId': 12,
    'runAttempt': 1,
    'workflowId': 7,
    'commitSha': _sha,
    'expiresAt': '2099-01-01T00:00:00Z',
  },
};

void main() {
  late Directory directory;
  late File archive;
  setUp(() async {
    directory = await Directory.systemTemp.createTemp('obtainx-r04-p02-');
    archive = File('${directory.path}/android.zip');
    await archive.writeAsBytes([0x50, 0x4b, 0x03, 0x04, 1, 2, 3]);
  });
  tearDown(() async {
    if (await directory.exists()) {
      await directory.delete(recursive: true);
    }
  });

  Future<void> verify(Map<String, dynamic> settings, {
    String source = _source, String url = _artifact, String name = _name,
  }) => verifyR04ActionsArchiveBeforeExtraction(
    archive: archive, additionalSettings: settings,
    sourceUrl: source, selectedAssetUrl: url, selectedAssetName: name,
  );

  test('published matching ZIP SHA-256 allows bounded extractor to proceed', () async {
    final expected = sha256.convert(await archive.readAsBytes()).toString();
    await verify(_settings(expected));
    expect(await archive.exists(), isTrue);
  });

  test('mismatched ZIP SHA-256 refuses and deletes cached poisoned file', () async {
    await expectLater(verify(_settings(List<String>.filled(64, '0').join())),
      throwsA(isA<R04ArchiveIntegrityFailure>()));
    expect(await archive.exists(), isFalse);
  });

  test('missing ZIP digest cannot turn a successful run into install proof', () async {
    await expectLater(verify(_settings('')),
      throwsA(isA<R04ArchiveIntegrityFailure>()));
    expect(await archive.exists(), isTrue);
  });

  test('changed repository, URL and artifact name reject stale evidence', () async {
    final digest = sha256.convert(await archive.readAsBytes()).toString();
    await expectLater(verify(_settings(digest), source: 'https://github.com/other/repo'),
      throwsA(isA<R04ArchiveIntegrityFailure>()));
    await expectLater(verify(_settings(digest), url: 'https://api.github.com/repos/example/repo/actions/artifacts/42/zip'),
      throwsA(isA<R04ArchiveIntegrityFailure>()));
    await expectLater(verify(_settings(digest), name: 'android-x86-apk.zip'),
      throwsA(isA<R04ArchiveIntegrityFailure>()));
  });

  test('cross-repository artifact URL is refused even with matching digest', () async {
    final digest = sha256.convert(await archive.readAsBytes()).toString();
    final forged = _settings(digest);
    const differentRepo =
        'https://api.github.com/repos/other/repo/actions/artifacts/41/zip';
    (forged[r04ActionsArchiveEvidenceKey] as Map)['archiveUrl'] = differentRepo;
    await expectLater(verify(forged, url: differentRepo),
      throwsA(isA<R04ArchiveIntegrityFailure>()));
    expect(await archive.exists(), isTrue);
  });

  test('forged host and missing run provenance fail closed', () async {
    final digest = sha256.convert(await archive.readAsBytes()).toString();
    final bad = _settings(digest);
    (bad[r04ActionsArchiveEvidenceKey] as Map)['archiveUrl'] =
      'https://attacker.invalid/repos/example/repo/actions/artifacts/41/zip';
    await expectLater(verify(bad, url: bad[r04ActionsArchiveEvidenceKey]['archiveUrl']),
      throwsA(isA<R04ArchiveIntegrityFailure>()));
    final missing = _settings(digest);
    (missing[r04ActionsArchiveEvidenceKey] as Map).remove('runAttempt');
    await expectLater(verify(missing), throwsA(isA<R04ArchiveIntegrityFailure>()));
  });

  test('expired cached ZIP is refused after source receipt expiry', () async {
    final digest = sha256.convert(await archive.readAsBytes()).toString();
    final settings = _settings(digest);
    (settings[r04ActionsArchiveEvidenceKey] as Map)['expiresAt'] =
      '2020-01-01T00:00:00Z';
    await expectLater(verify(settings),
      throwsA(isA<R04ArchiveIntegrityFailure>()));
    expect(await archive.exists(), isTrue);
  });

  test('JSON persisted evidence remains source-bound across process restart', () async {
    final digest = sha256.convert(await archive.readAsBytes()).toString();
    final restored = Map<String, dynamic>.from(
      jsonDecode(jsonEncode(_settings(digest))) as Map);
    await verify(restored);
    expect(await archive.exists(), isTrue);
  });

  test('GitHub Releases unchanged by Actions-only verification gate', () async {
    await verify({'r04GitHubSourceMode': 'releases'});
    expect(await archive.exists(), isTrue);
  });

  test('symlink archive cannot bypass regular file check', () async {
    final digest = sha256.convert(await archive.readAsBytes()).toString();
    final link = Link('${directory.path}/symlink.zip');
    await link.create(archive.path);
    await expectLater(verifyR04ActionsArchiveBeforeExtraction(
      archive: File(link.path), additionalSettings: _settings(digest),
      sourceUrl: _source, selectedAssetUrl: _artifact, selectedAssetName: _name,
    ), throwsA(isA<R04ArchiveIntegrityFailure>()));
    expect(await archive.exists(), isTrue);
  });
}
