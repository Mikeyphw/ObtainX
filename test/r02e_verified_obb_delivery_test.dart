import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/services/verified_obb_delivery.dart';

const appId = 'org.example.demo';
const fileName = 'main.22.org.example.demo.obb';

void main() {
  late Directory scratch;
  late File source;
  late Directory destination;
  setUp(() async {
    scratch = await Directory.systemTemp.createTemp('ox-rt02e-');
    final staging = await Directory('${scratch.path}/stage/Android/obb/$appId')
        .create(recursive: true);
    source = File('${staging.path}/$fileName');
    await source.writeAsBytes([1, 2, 3, 4, 5], flush: true);
    destination = Directory('${scratch.path}/dest/Android/obb/$appId');
  });
  tearDown(() async {
    if (scratch.existsSync()) await scratch.delete(recursive: true);
  });

  test('RT02E copies exact OBB bytes and returns an immutable digest receipt', () async {
    final result = await copyVerifiedObbFile(
      source: source, packageName: appId, destinationFolder: destination);
    expect(result.fileName, fileName);
    expect(result.length, 5);
    expect(result.sha256, hasLength(64));
    expect(await File('${destination.path}/$fileName').readAsBytes(),
        [1, 2, 3, 4, 5]);
    expect(await source.readAsBytes(), [1, 2, 3, 4, 5]);
  });

  test('RT02E replaces existing file only after verified staging', () async {
    await destination.create(recursive: true);
    final previous = File('${destination.path}/$fileName');
    await previous.writeAsBytes([99, 98]);
    await copyVerifiedObbFile(
      source: source, packageName: appId, destinationFolder: destination);
    expect(await previous.readAsBytes(), [1, 2, 3, 4, 5]);
    expect(destination.listSync().length, 1);
  });

  test('RT02E cancelled preflight leaves destination untouched', () async {
    await destination.create(recursive: true);
    final previous = File('${destination.path}/$fileName');
    await previous.writeAsBytes([44]);
    await expectLater(copyVerifiedObbFile(
      source: source, packageName: appId, destinationFolder: destination,
      isCancelled: () => true), throwsFormatException);
    expect(await previous.readAsBytes(), [44]);
  });

  test('RT02E cancellation after copy but before rename rolls back staging', () async {
    await destination.create(recursive: true);
    final previous = File('${destination.path}/$fileName');
    await previous.writeAsBytes([55]);
    var polls = 0;
    await expectLater(copyVerifiedObbFile(
      source: source, packageName: appId, destinationFolder: destination,
      isCancelled: () => ++polls == 2), throwsFormatException);
    expect(await previous.readAsBytes(), [55]);
    expect(destination.listSync().length, 1);
  });

  test('RT02E rejects wrong app and invalid OBB name', () async {
    await expectLater(copyVerifiedObbFile(
      source: source, packageName: 'org.other.app',
      destinationFolder: destination), throwsFormatException);
    final bad = File('${source.parent.path}/other.22.$appId.obb');
    await bad.writeAsBytes([8]);
    await expectLater(copyVerifiedObbFile(
      source: bad, packageName: appId,
      destinationFolder: destination), throwsFormatException);
    expect(destination.existsSync(), isFalse);
  });

  test('RT02E rejects empty, oversized and symlink source files', () async {
    await source.writeAsBytes([]);
    await expectLater(copyVerifiedObbFile(
      source: source, packageName: appId,
      destinationFolder: destination), throwsFormatException);
    await source.writeAsBytes([1, 2, 3, 4, 5]);
    await expectLater(copyVerifiedObbFile(
      source: source, packageName: appId,
      destinationFolder: destination, maxBytes: 4), throwsFormatException);
    final real = File('${source.parent.path}/real.bin');
    await real.writeAsBytes([7]);
    await source.delete();
    await Link(source.path).create(real.path);
    await expectLater(copyVerifiedObbFile(
      source: source, packageName: appId,
      destinationFolder: destination), throwsFormatException);
  });

  test('RT02E refuses destination symlinks without overwriting their targets', () async {
    await destination.create(recursive: true);
    final outside = File('${scratch.path}/untouched.bin');
    await outside.writeAsBytes([42]);
    await Link('${destination.path}/$fileName').create(outside.path);
    await expectLater(copyVerifiedObbFile(
      source: source, packageName: appId,
      destinationFolder: destination), throwsFormatException);
    expect(await outside.readAsBytes(), [42]);
  });
}
