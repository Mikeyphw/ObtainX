/// Retention of terminal transfer metadata only. Partial/archive bytes are
/// never removed here; the transfer engine owns all writes to its cache.
library;

import 'dart:convert';
import 'dart:io';
import 'package:crypto/crypto.dart';

import 'package:obtainium/services/r03_download_engine.dart';
import 'package:obtainium/services/r07_journal_guard.dart';
import 'package:path_provider/path_provider.dart';

class R03RetentionPreview {
  R03RetentionPreview._(this.cutoff, this.listingKey, this.packageId, this.channel,
      Map<String, String> entries) : entries = Map.unmodifiable(entries);
  final DateTime cutoff;
  final String? listingKey, packageId, channel;
  final Map<String, String> entries;
}

class R03DownloadHistory {
  R03DownloadHistory({required this.cache, this.testingRoot});
  final Directory cache;
  final Directory? testingRoot;
  static final _receiptName = RegExp(r'^[a-f0-9]{64}\.json$');
  static const maxReceiptBytes = 320 * 1024;
  static final archivedName = RegExp(r'^[a-f0-9]{64}-[a-f0-9]{64}\.json$');
  static Directory archiveOf(Directory root) => Directory('${root.path}.history');
  static String archiveName(R03DownloadRecord record, List<int> raw) =>
      '${record.jobId}-${sha256.convert(raw)}.json';

  static Future<void> verifyDirectory(Directory directory) async {
    final type = await FileSystemEntity.type(directory.path, followLinks: false);
    if (type != FileSystemEntityType.notFound && type != FileSystemEntityType.directory) {
      throw const FileSystemException('Unsafe transfer history directory');
    }
  }

  Future<Directory> _root() async {
    final base = testingRoot ?? await getApplicationSupportDirectory();
    final root = Directory('${base.path}/r03-download-journal');
    final type = await FileSystemEntity.type(root.path, followLinks: false);
    if (type != FileSystemEntityType.notFound && type != FileSystemEntityType.directory) {
      throw const FileSystemException('Unsafe transfer history root');
    }
    return root;
  }

  static Future<R03DownloadRecord> readRecord(File file, {bool archived = false}) async {
    if (await FileSystemEntity.type(file.path, followLinks: false) != FileSystemEntityType.file ||
        await file.length() > maxReceiptBytes) {
      throw const FormatException('Untrusted transfer history');
    }
    final bytes = await file.readAsBytes();
    if (bytes.length > maxReceiptBytes) throw const FormatException('Oversize transfer history');
    final value = jsonDecode(utf8.decode(bytes));
    if (value is! Map<String, dynamic>) throw const FormatException('Invalid transfer history');
    final record = R03DownloadRecord.fromJson(value);
    if (file.uri.pathSegments.last != (archived ? archiveName(record, bytes) : '${record.jobId}.json') ||
        record.sourceFingerprint != record.jobId) {
      throw const FormatException('Transfer history identity mismatch');
    }
    return record;
  }

  Future<bool> _eligible(R03DownloadRecord record, DateTime cutoff, File file,
      String? listingKey, String? packageId, String? channel) async {
    final owner = record.historyBinding;
    final name = record.fileName;
    if (owner == null || owner.releaseFingerprint == null ||
        record.cacheRootFingerprint != r07JournalFingerprint(cache.absolute.path) ||
        await FileSystemEntity.type(cache.path, followLinks: false) != FileSystemEntityType.directory ||
        (listingKey != null && owner.listingKey != listingKey) ||
        (packageId != null && owner.packageId != packageId) ||
        (channel != null && owner.channel != channel) ||
        name.isEmpty || name == '.' || name == '..' ||
        name.contains(RegExp(r'[\x00-\x1f/\\]')) ||
        !(await file.stat()).modified.toUtc().isBefore(cutoff) ||
        !const {R03Stage.ready, R03Stage.completed, R03Stage.failed, R03Stage.cancelled}.contains(record.stage)) {
      return false;
    }
    // A failed/cancelled transfer can still own resumable bytes. Preserve
    // every path and refuse legacy/unknown cache ownership.
    final base = '${cache.path}/$name';
    for (final path in [base, '$base.part', '$base-dir']) {
      if (await FileSystemEntity.type(path, followLinks: false) != FileSystemEntityType.notFound) return false;
    }
    return true;
  }

  Future<R03RetentionPreview> previewTerminalBefore(DateTime cutoff,
      {String? listingKey, String? packageId, String? channel}) async {
    final root = await _root();
    final entries = <String, String>{};
    for (final archived in [false, true]) {
      final directory = archived ? archiveOf(root) : root;
      await verifyDirectory(directory);
      if (!await directory.exists()) continue;
      await for (final entity in directory.list(followLinks: false)) {
        final name = entity.uri.pathSegments.last;
        if (!archived && name.endsWith('.json.tmp') && _receiptName.hasMatch(name.substring(0, name.length - 4)) &&
            await FileSystemEntity.type(entity.path, followLinks: false) == FileSystemEntityType.file) {
          continue;
        }
        if (entity is! File || !(archived ? archivedName : _receiptName).hasMatch(name)) {
          throw const FormatException('Unknown transfer journal entry');
        }
        final record = await readRecord(entity, archived: archived);
        if (await _eligible(record, cutoff.toUtc(), entity, listingKey, packageId, channel)) {
          entries['${archived ? 'archive' : 'live'}:$name'] = jsonEncode(record.toJson());
        }
      }
    }
    return R03RetentionPreview._(cutoff.toUtc(), listingKey, packageId, channel, entries);
  }

  /// Move immutable terminal metadata away from the recovery directory. This
  /// never erases a checkpoint, never runs an installer, and does not make
  /// a missing cache root proof that its bytes have been deleted.
  Future<int> archiveTerminalWithoutBytes() async {
    final root = await _root();
    if (!await root.exists()) return 0;
    final archive = archiveOf(root);
    await verifyDirectory(archive);
    var moved = 0;
    final cutoff = DateTime.now().toUtc();
    await for (final entity in root.list(followLinks: false)) {
      if (entity is! File || !_receiptName.hasMatch(entity.uri.pathSegments.last)) { continue; }
      try {
        final record = await readRecord(entity);
        if (!await _eligible(record, cutoff, entity, null, null, null)) continue;
        await withR07JournalGuard(root, 'destination:${File('${cache.path}/${record.fileName}').absolute.path}', () async {
          final current = await readRecord(entity);
          if (jsonEncode(current.toJson()) != jsonEncode(record.toJson()) ||
              !await _eligible(current, cutoff, entity, null, null, null)) {
            return;
          }
          await verifyDirectory(archive);
          await archive.create(recursive: true);
          final bytes = await entity.readAsBytes();
          final target = File('${archive.path}/${archiveName(current, bytes)}');
          if (await FileSystemEntity.type(target.path, followLinks: false) != FileSystemEntityType.notFound) return;
          await entity.rename(target.path);
          moved++;
        }, acquisitionTimeout: const Duration(milliseconds: 100));
      } on FileSystemException {
        // Preserve unreadable/racing records for explicit review.
      } on FormatException {
        // Corrupt records cannot authorize archival or deletion.
      } on TypeError {
        // Preserve malformed metadata.
      } on R07JournalBusy {
        // A live owner may still hold the destination lock.
      }
    }
    return moved;
  }

  Future<int> prune(R03RetentionPreview preview) async {
    final root = await _root();
    return withR07JournalGuard(root, 'retention-review', () async {
      final current = await previewTerminalBefore(preview.cutoff, listingKey: preview.listingKey,
        packageId: preview.packageId, channel: preview.channel);
      if (current.entries.length != preview.entries.length ||
          preview.entries.entries.any((entry) => current.entries[entry.key] != entry.value)) {
        throw StateError('Transfer retention changed; preview again');
      }
      var removed = 0;
      for (final entry in preview.entries.entries) {
        final archived = entry.key.startsWith('archive:');
        final name = entry.key.substring(archived ? 8 : 5);
        if (!(archived ? archivedName : _receiptName).hasMatch(name)) {
          throw const FormatException('Invalid retention identity');
        }
        final file = File('${(archived ? archiveOf(root) : root).path}/$name');
        final record = await readRecord(file, archived: archived);
        if (jsonEncode(record.toJson()) != entry.value) throw StateError('Transfer receipt changed');
        final destination = File('${cache.path}/${record.fileName}');
        await withR07JournalGuard(root, 'destination:${destination.absolute.path}', () async {
          final latest = await readRecord(file, archived: archived);
          if (jsonEncode(latest.toJson()) != entry.value ||
              !await _eligible(latest, preview.cutoff, file, preview.listingKey, preview.packageId, preview.channel)) {
            throw StateError('Transfer retention ownership changed');
          }
          await file.delete();
          removed++;
        });
      }
      return removed;
    });
  }
}
