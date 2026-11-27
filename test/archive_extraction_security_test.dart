import 'dart:async';
import 'dart:io';

import 'package:archive/archive.dart' as archive;

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
    expect(workspace.listSync().where(
      (file) => file.path.contains('.obtainx-extract-'),
    ), isEmpty, reason: 'Temporary extraction tree must be removed');
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

  test('ZIP and TAR.GZ stream members larger than the 64KiB read chunk', () async {
    final payload = List<int>.generate(196608 + 37, (i) => (i * 31) % 251);
    final contents = archive.Archive()
      ..add(archive.ArchiveFile.bytes('bundle/base.apk', payload));
    final zipFile = File('${workspace.path}/large-valid.zip')
      ..writeAsBytesSync(archive.ZipEncoder().encode(contents));
    final tarFile = File('${workspace.path}/large-valid.tar.gz')
      ..writeAsBytesSync(
        const archive.GZipEncoder().encode(archive.TarEncoder().encode(contents)),
      );
    await extractZipOffIsolate(zipFile.path, target());
    expect(File('${target()}/bundle/base.apk').readAsBytesSync(), payload);
    final tarTarget = '${workspace.path}/tar-extracted';
    await extractTarballOffIsolate(tarFile.path, tarTarget);
    expect(File('$tarTarget/bundle/base.apk').readAsBytesSync(), payload);
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

  test('ZIP metadata budget is enforced before member decoding', () async {
    await expectZipRejected('valid.zip', limits:
      const ArchiveExtractionLimits(maxMetadataBytes: 10));
  });

  test('BZIP2 refuses missing end marker, trailing bytes and invalid block size', () async {
    for (final name in ['truncated.tar.bz2', 'trailing.tar.bz2', 'invalid_block.tar.bz2']) {
      await expectTarRejected(name);
    }
  });

  test('XZ independently compressed CRC32, CRC64 and SHA256 streams', () async {
    final expected = List<int>.generate(196608 + 37, (i) => (i * 31) % 251);
    for (final check in ['crc32', 'crc64', 'sha256']) {
      final destination = '${workspace.path}/extracted-$check';
      await extractTarballOffIsolate(
        fixture('hf02_large_$check.tar.xz'),
        destination,
      );
      expect(File('$destination/nested/app.apk').readAsBytesSync(), expected);
    }
    expect(workspace.listSync().where(
      (file) => file.path.contains('.obtainx-extract-'),
    ), isEmpty);
  });

  test('XZ rejects legacy reversed index VLIs without publishing', () async {
    await expectTarRejected('hf02_legacy_index.tar.xz');
  });

  test('XZ verifies block checks independently of valid stream metadata', () async {
    await expectTarRejected('hf02_bad_block_check.tar.xz');
  });

  test('XZ refuses expanded bytes above budget without publishing', () async {
    await expectTarRejected('hf02_large_crc64.tar.xz', limits:
        const ArchiveExtractionLimits(maxEntryBytes: 65536,
            maxExpandedBytes: 65536));
  });

  test('XZ oversized dictionary refuses even a tiny valid archive', () async {
    await expectTarRejected('large_dictionary.tar.xz');
  });

  test('orphan stage recovery is confined to exact marked ownership', () async {
    final orphan = Directory('${workspace.path}/.obtainx-extract-2147483646-dead')..createSync();
    File('${orphan.path}/owner.lock').writeAsStringSync('obtainx-extraction-v2:2147483646');
    final foreign = Directory('${workspace.path}/.obtainx-extract-2147483645-foreign')..createSync();
    File('${foreign.path}/owner.lock').writeAsStringSync('not-owned');
    await extractZipOffIsolate(fixture('valid.zip'), target());
    expect(orphan.existsSync(), isFalse);
    expect(foreign.existsSync(), isTrue);
    expect(Directory(target()).existsSync(), isTrue);
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

  test('deadline refusal never publishes or leaves private staging', () async {
    await expectLater(
      extractZipOffIsolate(fixture('valid.zip'), target(),
        limits: const ArchiveExtractionLimits(
          maxWallTime: Duration(microseconds: 1))),
      throwsA(isA<TimeoutException>()),
    );
    expect(Directory(target()).existsSync(), isFalse);
    expect(workspace.listSync(), isEmpty);
  });

  test('cancellation at publication boundary refuses completed staging', () async {
    var checks = 0;
    await expectLater(
      extractZipOffIsolate(fixture('valid.zip'), target(),
        checkCancellation: () {
          if (++checks > 1) throw StateError('cancelled');
        }),
      throwsA(isA<StateError>()),
    );
    expect(Directory(target()).existsSync(), isFalse);
    expect(workspace.listSync(), isEmpty);
  });

  test('TAR cancellation before staging leaves destination untouched', () async {
    await expectLater(
      extractTarballOffIsolate(fixture('valid.tar.gz'), target(),
        checkCancellation: () => throw StateError('cancelled')),
      throwsA(isA<StateError>()),
    );
    expect(workspace.listSync(), isEmpty);
  });

  test('invalid limits are rejected before writing', () async {
    await expectZipRejected('valid.zip', limits:
        const ArchiveExtractionLimits(maxEntryBytes: 4096,
            maxExpandedBytes: 1000));
  });
}
