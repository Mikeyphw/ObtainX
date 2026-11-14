import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/services/verified_obb_delivery.dart';

void main() {
  test('P05 refuses OBB destination directory with symlink ancestor', () async {
    final temp = await Directory.systemTemp.createTemp('ox-p05-obb-');
    try {
      final sourceDir = await Directory('${temp.path}/stage/Android/obb/org.example.p05')
          .create(recursive: true);
      final source = File('${sourceDir.path}/main.5.org.example.p05.obb');
      await source.writeAsBytes([5, 4, 3, 2, 1], flush: true);
      final external = await Directory('${temp.path}/external').create();
      final alias = Link('${temp.path}/alias');
      await alias.create(external.path);
      await expectLater(copyVerifiedObbFile(
        source: source, packageName: 'org.example.p05',
        destinationFolder: Directory('${alias.path}/Android/obb/org.example.p05')),
        throwsFormatException);
      expect(external.listSync(), isEmpty);
    } finally {
      if (temp.existsSync()) await temp.delete(recursive: true);
    }
  });
  test('P05 retains normal verified copy and source SHA', () async {
    final temp = await Directory.systemTemp.createTemp('ox-p05-obb-');
    try {
      final sourceDir = await Directory('${temp.path}/stage/Android/obb/org.example.p05')
          .create(recursive: true);
      final source = File('${sourceDir.path}/patch.5.org.example.p05.obb');
      await source.writeAsBytes([1, 3, 5, 7, 9], flush: true);
      final dest = Directory('${temp.path}/real/Android/obb/org.example.p05');
      final receipt = await copyVerifiedObbFile(source: source,
        packageName: 'org.example.p05', destinationFolder: dest);
      expect(receipt.length, 5);
      expect(await File('${dest.path}/${receipt.fileName}').readAsBytes(),
        [1, 3, 5, 7, 9]);
    } finally {
      if (temp.existsSync()) await temp.delete(recursive: true);
    }
  });
}
