import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/services/artifact_file_work.dart';

void main() {
  final fixtures = Directory('test/fixtures/r01_archives');
  late Directory workspace;

  setUp(() {
    workspace = Directory.systemTemp.createTempSync('obtainx-r01-test-');
  });
  tearDown(() {
    if (workspace.existsSync()) workspace.deleteSync(recursive: true);
  });

  String fixture(String name) => File('${fixtures.path}/$name').absolute.path;
  String target() => '${workspace.path}/extracted';

  Future<void> expectZipRejected(
    String name, {
    ArchiveExtractionLimits limits = const ArchiveExtractionLimits(),
  }) async {
    await expectLater(
      extractZipOffIsolate(fixture(name), target(), limits: limits),
      throwsA(isA<Exception>()),
    );
    expect(Directory(target()).existsSync(), isFalse,
        reason: 'A rejected ZIP must never publish partial extraction');
    expect(File('${workspace.path}/escape.apk').existsSync(), isFalse);
    expect(workspace.listSync().where(
      (file) => file.path.contains('.obtainx-extract-'),
    ), isEmpty, reason: 'Temporary extraction tree must be removed');
  }

  Future<void> expectTarRejected(
    String name, {
    ArchiveExtractionLimits limits = const ArchiveExtractionLimits(),
  }) async {
    await expectLater(
      extractTarballOffIsolate(fixture(name), target(), limits: limits),
      throwsA(isA<Exception>()),
    );
    expect(Directory(target()).existsSync(), isFalse);
    expect(File('${workspace.path}/escape.apk').existsSync(), isFalse);
  }

  test('ZIP extraction publishes expected APK files only when complete', () async {
    await extractZipOffIsolate(fixture('valid.zip'), target());
    expect(File('${target()}/bundle/base.apk').readAsBytesSync(),
        'example apk contents'.codeUnits);
    expect(File('${target()}/bundle/config.arm64_v8a.apk').existsSync(), isTrue);
  });

  test('TAR raw, BZIP2 and XZ remain supported', () async {
    for (final format in ['raw', 'bz2', 'xz']) {
      final destination = '${workspace.path}/extracted-$format';
      await extractTarballOffIsolate(fixture('valid.tar.$format'), destination);
      expect(File('$destination/bundle/base.apk').readAsBytesSync(),
          'extra tar variant'.codeUnits);
    }
  });

  test('TAR.GZ extraction remains supported and atomic', () async {
    await extractTarballOffIsolate(fixture('valid.tar.gz'), target());
    expect(File('${target()}/bundle/base.apk').readAsBytesSync(),
        'tar apk'.codeUnits);
  });

  test('ZIP refuses ../ traversal', () async {
    await expectZipRejected('traversal.zip');
  });

  test('ZIP refuses absolute entry paths', () async {
    await expectZipRejected('absolute.zip');
  });

  test('ZIP refuses symbolic links', () async {
    await expectZipRejected('symlink.zip');
  });

  test('ZIP refuses duplicate central-directory entries', () async {
    await expectZipRejected('duplicate.zip');
  });

  test('ZIP refuses case-folding filename collisions', () async {
    await expectZipRejected('collision.zip');
  });

  test('ZIP refuses exceeding the file-count budget', () async {
    await expectZipRejected('too_many.zip',
      limits: const ArchiveExtractionLimits(maxEntries: 2));
  });

  test('ZIP refuses exceeding the per-file extracted size budget', () async {
    await expectZipRejected('large.zip',
      limits: const ArchiveExtractionLimits(maxEntryBytes: 1024));
  });

  test('ZIP refuses exceeding the path-depth budget', () async {
    await expectZipRejected('nested.zip',
      limits: const ArchiveExtractionLimits(maxDepth: 3));
  });

  test('ZIP refuses exceeding the source archive byte budget', () async {
    await expectZipRejected('valid.zip',
      limits: const ArchiveExtractionLimits(maxArchiveBytes: 10));
  });

  test('ZIP refuses cumulative extracted-size overflow and cleans stage', () async {
    await expectZipRejected('combined_size.zip', limits:
        const ArchiveExtractionLimits(maxEntryBytes: 1600,
            maxExpandedBytes: 2000));
  });

  test('ZIP refuses Windows drive and backslash traversal paths', () async {
    await expectZipRejected('windows_drive.zip');
    await expectZipRejected('backslashes.zip');
  });

  test('TAR decoder output itself is bounded before staging', () async {
    await expectTarRejected('valid.tar.gz', limits:
        const ArchiveExtractionLimits(maxEntryBytes: 1024,
            maxExpandedBytes: 2048));
  });

  test('ZIP checks extracted member CRC32 rather than just byte length', () async {
    await expectZipRejected('crc_mismatch.zip');
  });

  test('ZIP refuses malformed payload', () async {
    await expectZipRejected('bad.zip');
  });

  test('TAR refuses traversal and symlink entries', () async {
    await expectTarRejected('traversal.tar.gz');
    await expectTarRejected('symlink.tar.gz');
  });

  test('TAR refuses exceeding expanded-size budget', () async {
    await expectTarRejected('large.tar.gz',
      limits: const ArchiveExtractionLimits(maxEntryBytes: 1024));
  });

  test('existing extraction destination is never overwritten', () async {
    Directory(target()).createSync();
    final marker = File('${target()}/marker.txt')..writeAsStringSync('keep');
    await expectLater(
      extractZipOffIsolate(fixture('valid.zip'), target()),
      throwsA(isA<FormatException>()),
    );
    expect(marker.readAsStringSync(), 'keep');
  });

  test('invalid limits are rejected before writing', () async {
    await expectZipRejected('valid.zip', limits:
        const ArchiveExtractionLimits(maxEntryBytes: 4096,
            maxExpandedBytes: 1000));
  });
}
