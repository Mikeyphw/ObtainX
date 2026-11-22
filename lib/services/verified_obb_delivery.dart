/// Source-bound, single-file OBB delivery after confirmed APK installation.
///
/// This handles one expansion file transactionally. It cannot make a
/// multi-file OBB set atomic across a power loss, and does not grant Android
/// 11+ scoped-storage access. Those paths remain unsupported by stock install.
library;

import 'dart:io';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:obtainium/services/install_bundle_plan.dart';

class VerifiedObbReceipt {
  const VerifiedObbReceipt({
    required this.fileName,
    required this.sha256,
    required this.length,
  });

  final String fileName;
  final String sha256;
  final int length;
}

/// Copies the verified original to a private sibling, checks its SHA256, then
/// atomically swaps that sibling into place. An existing file is backed up and
/// restored on any failure before replacement completes. The source is never
/// deleted. Aborts before commit leave the existing destination untouched.
///
/// [isCancelled] is checked before copying and before destination mutation;
/// it is not a guarantee of rollback after the atomic rename has completed.
Future<VerifiedObbReceipt> copyVerifiedObbFile({
  required File source,
  required String packageName,
  required Directory destinationFolder,
  bool Function()? isCancelled,
  int maxBytes = 2 * 1024 * 1024 * 1024,
}) async {
  validateObbFileNames([source.path], packageName);
  if (maxBytes <= 0) {
    throw const FormatException('Invalid OBB size limit');
  }
  if (FileSystemEntity.typeSync(source.path, followLinks: false) !=
      FileSystemEntityType.file) {
    throw const FormatException('OBB source must be a regular file');
  }
  final originalSize = await source.length();
  if (originalSize <= 0 || originalSize > maxBytes) {
    throw const FormatException('OBB file length outside permitted bounds');
  }
  if (isCancelled?.call() ?? false) {
    throw const FormatException('OBB copy cancelled before staging');
  }
  final fileName = source.uri.pathSegments.last;
  final targetPath = '${destinationFolder.path}/$fileName';
  if (source.absolute.path == File(targetPath).absolute.path) {
    throw const FormatException('OBB source cannot equal destination');
  }
  if (destinationFolder.existsSync() &&
      FileSystemEntity.typeSync(destinationFolder.path, followLinks: false) !=
          FileSystemEntityType.directory) {
    throw const FormatException('OBB destination must be a real directory');
  }
  final destination = File(targetPath);
  if (FileSystemEntity.typeSync(targetPath, followLinks: false) !=
          FileSystemEntityType.notFound &&
      FileSystemEntity.typeSync(targetPath, followLinks: false) !=
          FileSystemEntityType.file) {
    throw const FormatException('OBB destination cannot be a symlink or directory');
  }
  await destinationFolder.create(recursive: true);
  final nonce = Random.secure().nextInt(0x7fffffff).toRadixString(16);
  final pending = File('${destinationFolder.path}/.$fileName.$nonce.pending');
  final backup = File('${destinationFolder.path}/.$fileName.$nonce.backup');
  if (pending.existsSync() || backup.existsSync()) {
    throw const FormatException('OBB transaction path collision');
  }
  var oldBackedUp = false;
  try {
    // Bounded stream digests: never load a potentially large OBB into memory.
    final expected = (await sha256.bind(source.openRead()).first).toString();
    await source.copy(pending.path);
    if (await pending.length() != originalSize ||
        (await sha256.bind(pending.openRead()).first).toString() != expected) {
      throw const FormatException('OBB copy SHA256 or size verification failed');
    }
    if (isCancelled?.call() ?? false) {
      throw const FormatException('OBB copy cancelled before commit');
    }
    // Recheck immediately before swapping: refuse TOCTOU symlink replacement.
    final targetType = FileSystemEntity.typeSync(targetPath, followLinks: false);
    if (targetType != FileSystemEntityType.notFound &&
        targetType != FileSystemEntityType.file) {
      throw const FormatException('OBB destination changed during copying');
    }
    if (targetType == FileSystemEntityType.file) {
      await destination.rename(backup.path);
      oldBackedUp = true;
    }
    try {
      await pending.rename(targetPath);
    } catch (_) {
      if (oldBackedUp) {
        await backup.rename(targetPath);
        oldBackedUp = false;
      }
      rethrow;
    }
    if (oldBackedUp && backup.existsSync()) {
      await backup.delete();
    }
    return VerifiedObbReceipt(
      fileName: fileName, sha256: expected, length: originalSize);
  } finally {
    if (pending.existsSync()) await pending.delete();
    // If a post-swap cleanup fails, retain the prior backup for manual recovery
    // rather than silently removing the only known-good old copy.
  }
}
