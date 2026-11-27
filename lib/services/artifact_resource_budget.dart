// Resource admission checks. The Android plugin is registered on foreground
// and background engines; missing capacity evidence is not treated as space.
import 'dart:io';
import 'package:flutter/services.dart';

const artifactStorageReserveBytes = 16 * 1024 * 1024;
const _resourceChannel = MethodChannel('dev.imranr.obtainium/r02_local_archive');

Future<void> ensureArtifactStorageCapacity(String directory, int requiredBytes,
    {Future<int?> Function(String)? probe}) async {
  if (requiredBytes < 0 || requiredBytes > 8 * 1024 * 1024 * 1024) {
    throw const FileSystemException('Invalid artifact storage budget');
  }
  if (probe == null && !Platform.isAndroid) return;
  final available = await (probe?.call(directory) ??
      _resourceChannel.invokeMethod<int>('availableBytes', {'directory': directory}));
  if (available == null || available < artifactStorageReserveBytes ||
      requiredBytes > available - artifactStorageReserveBytes) {
    throw const FileSystemException('Insufficient artifact storage capacity');
  }
}
