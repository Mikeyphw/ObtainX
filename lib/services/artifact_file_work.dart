import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:isolate';
import 'dart:typed_data';

import 'package:archive/archive_io.dart' as archive;
import 'package:crypto/crypto.dart';

/// Explicit extraction budget. Applies to both ZIPs and TAR-based artifacts.
///
/// The limits are intentionally conservative on mobile devices. A rejected
/// archive is never published to its destination, including after exceptions.
class ArchiveExtractionLimits {
  const ArchiveExtractionLimits({
    this.maxArchiveBytes = 1024 * 1024 * 1024,
    this.maxExpandedBytes = 1536 * 1024 * 1024,
    this.maxEntryBytes = 768 * 1024 * 1024,
    this.maxEntries = 4096,
    this.maxDepth = 20,
    this.maxPathLength = 1024,
    this.maxMetadataBytes = 8 * 1024 * 1024,
    this.maxWallTime = const Duration(minutes: 5),
  });

  final int maxArchiveBytes;
  final int maxExpandedBytes;
  final int maxEntryBytes;
  final int maxEntries;
  final int maxDepth;
  final int maxPathLength;
  final int maxMetadataBytes;
  final Duration maxWallTime;

  void validate() {
    if (maxArchiveBytes <= 0 || maxExpandedBytes <= 0 ||
        maxEntryBytes <= 0 || maxEntries <= 0 ||
        maxEntries > 4096 || maxDepth <= 0 || maxDepth > 20 ||
        maxPathLength <= 0 || maxPathLength > 1024 || maxMetadataBytes <= 0 ||
        maxMetadataBytes > 16 * 1024 * 1024 ||
        maxWallTime <= Duration.zero ||
        maxEntryBytes > maxExpandedBytes) {
      throw const FormatException('Invalid archive extraction limits');
    }
  }
}

Future<String> sha256FileOffIsolate(String path) {
  return Isolate.run(() async {
    return (await sha256.bind(File(path).openRead()).first).toString();
  }, debugName: 'artifact-sha256');
}

/// Both entry points use identical path checks, size limits and atomic publish.
Future<void> extractZipOffIsolate(
  String path,
  String destination, {
  ArchiveExtractionLimits limits = const ArchiveExtractionLimits(),
  void Function()? checkCancellation,
}) => _runExtraction(path, destination, tarball: false, limits: limits,
    checkCancellation: checkCancellation);

Future<void> extractTarballOffIsolate(
  String path,
  String destination, {
  ArchiveExtractionLimits limits = const ArchiveExtractionLimits(),
  void Function()? checkCancellation,
}) => _runExtraction(path, destination, tarball: true, limits: limits,
    checkCancellation: checkCancellation);

// The worker receives only its private staging directory, never the public
// destination. Cancellation/timeout kills it and waits for actual exit before
// deleting staging. Only the caller can publish a completed result.
void _extractionWorker((SendPort, String, String, bool, ArchiveExtractionLimits) args) {
  final (reply, path, work, tarball, limits) = args;
  try {
    // Preflight and decoders must consume the same privately staged bytes.
    final source = _stageExtractionInput(path, work, limits);
    _extractArchive(source, work, tarball: tarball, limits: limits);
  } catch (_) {
    Isolate.exit(reply, false);
  }
  Isolate.exit(reply, true);
}

Future<void> _runExtraction(String path, String destination, {
  required bool tarball,
  required ArchiveExtractionLimits limits,
  void Function()? checkCancellation,
}) async {
  limits.validate();
  checkCancellation?.call();
  _checkArchiveInput(path, limits);
  final target = Directory(destination).absolute;
  if (FileSystemEntity.typeSync(target.path, followLinks: false) !=
      FileSystemEntityType.notFound) {
    throw const FormatException('Extraction destination already exists');
  }
  final parent = target.parent;
  if (!parent.existsSync()) {
    throw const FormatException('Extraction destination parent does not exist');
  }
  _reclaimOrphanExtractionStages(parent);
  final work = parent.createTempSync('.obtainx-extract-$pid-');
  RandomAccessFile? ownership;
  try {
    final marker = File('${work.path}/owner.lock')..createSync(exclusive: true);
    ownership = marker.openSync(mode: FileMode.write);
    ownership.lockSync(FileLock.exclusive);
    ownership.writeStringSync('obtainx-extraction-v2:$pid');
    ownership.flushSync();
  } catch (_) {
    ownership?.closeSync();
    work.deleteSync(recursive: true);
    rethrow;
  }
  final stage = Directory('${work.path}/output');
  final reply = ReceivePort();
  final exited = Completer<void>();
  var completed = false;
  Object? refusal;
  Isolate? worker;
  Timer? watchdog;
  final elapsed = Stopwatch()..start();
  void check() {
    checkCancellation?.call();
    if (elapsed.elapsed >= limits.maxWallTime) {
      throw TimeoutException('Archive extraction deadline exceeded');
    }
  }
  final subscription = reply.listen((message) {
    if (message == null) {
      exited.complete();
    } else if (message == true) {
      completed = true;
    } else {
      refusal ??= const FormatException('Archive extraction failed');
    }
  });
  try {
    worker = await Isolate.spawn(_extractionWorker,
        (reply.sendPort, path, work.path, tarball, limits),
        onExit: reply.sendPort, onError: reply.sendPort,
        errorsAreFatal: true, debugName: 'artifact-extraction');
    void poll() {
      if (exited.isCompleted || refusal != null) return;
      try {
        check();
      } catch (error) {
        refusal = error;
        worker?.kill(priority: Isolate.immediate);
      }
    }
    watchdog = Timer.periodic(const Duration(milliseconds: 25), (_) => poll());
    poll();
    await exited.future;
    if (refusal != null) throw refusal!;
    if (!completed) throw const FormatException('Archive worker exited without proof');
    check();
    if (FileSystemEntity.typeSync(target.path, followLinks: false) !=
        FileSystemEntityType.notFound) {
      throw const FormatException('Extraction destination changed');
    }
    stage.renameSync(target.path);
  } finally {
    watchdog?.cancel();
    if (worker != null && !exited.isCompleted) {
      worker.kill(priority: Isolate.immediate);
      await exited.future;
    }
    await subscription.cancel();
    reply.close();
    try {
      if (work.existsSync()) work.deleteSync(recursive: true);
    } finally {
      ownership.closeSync();
    }
  }
}

/// Never sweep arbitrary old files or work owned by an isolate in this process.
// A valid prior owner marker plus a nonblocking OS lock proves the prior
// process no longer holds the stage. A reused PID only delays reclamation.
void _reclaimOrphanExtractionStages(Directory parent) {
  final pattern = RegExp(r'^\.obtainx-extract-([1-9][0-9]*)-[A-Za-z0-9]+$');
  for (final entry in parent.listSync(followLinks: false)) {
    if (entry is! Directory) continue;
    final match = pattern.firstMatch(entry.uri.pathSegments.where((p) => p.isNotEmpty).last);
    if (match == null || match.group(1) == '$pid') continue;
    final marker = File('${entry.path}/owner.lock');
    if (FileSystemEntity.typeSync(marker.path, followLinks: false) != FileSystemEntityType.file || marker.lengthSync() > 64) continue;
    RandomAccessFile? lock;
    try {
      // A marker's exact content is checked before and after locking. The
      // active owner writes it only *after* acquiring its exclusive lock.
      final expected = 'obtainx-extraction-v2:${match.group(1)}';
      if (marker.readAsStringSync() != expected) continue;
      lock = marker.openSync(mode: FileMode.append);
      lock.lockSync(FileLock.exclusive);
      if (marker.readAsStringSync() != expected) continue;
      entry.deleteSync(recursive: true);
    } on FileSystemException {
      // Active process, concurrently reclaimed stage or denied access: leave
      // it intact; never infer that a lock failure means the owner is dead.
    } finally {
      lock?.closeSync();
    }
  }
}

String _stageExtractionInput(String path, String work, ArchiveExtractionLimits limits) {
  _checkArchiveInput(path, limits);
  final input = File(path).openSync();
  final output = File('$work/input').openSync(mode: FileMode.write);
  try {
    var copied = 0;
    while (true) {
      final bytes = input.readSync(65536);
      if (bytes.isEmpty) break;
      if (bytes.length > limits.maxArchiveBytes - copied) {
        throw const FormatException('Archive changed or exceeded size limit');
      }
      output.writeFromSync(bytes);
      copied += bytes.length;
    }
    if (copied == 0) throw const FormatException('Empty archive input');
    output.flushSync();
    return '$work/input';
  } finally {
    output.closeSync();
    input.closeSync();
  }
}

// Enforces actual bytes sent to the file, not only potentially forged archive
/// headers. Also bounds the intermediate decoded TAR created for .tar.gz/.xz.
class _LimitedOutputStream extends archive.OutputStream {
  _LimitedOutputStream(this.output, this.maxBytes)
      : super(byteOrder: output.byteOrder);

  final archive.OutputStream output;
  final int maxBytes;
  int written = 0;

  void _reserve(int byteCount) {
    if (byteCount < 0 || byteCount > maxBytes - written) {
      throw const FormatException('Archive expanded-size limit exceeded');
    }
    written += byteCount;
  }

  @override
  int get length => output.length;

  @override
  bool get isOpen => output.isOpen;

  @override
  void open() => output.open();

  @override
  void flush() => output.flush();

  @override
  void clear() => throw const FormatException('Decoder output reset is forbidden');

  @override
  void closeSync() => output.closeSync();

  @override
  Future<void> close() => output.close();

  @override
  void writeByte(int value) {
    _reserve(1);
    output.writeByte(value);
  }

  @override
  void writeBytes(List<int> bytes, {int? length}) {
    final count = length ?? bytes.length;
    if (count > bytes.length) {
      throw const FormatException('Malformed archive write length');
    }
    _reserve(count);
    output.writeBytes(bytes, length: count);
  }

  @override
  void writeStream(archive.InputStream stream) {
    // Avoid converting the entire decompressed entry into a single byte array.
    const chunkBytes = 64 * 1024;
    final start = stream.position;
    try {
      while (!stream.isEOS) {
        // archive v4 exposes readBytes on InputStream; readInto is available
        // only on concrete input-stream types. Never buffer more than 64KiB.
        final bytes = stream.readBytes(chunkBytes).toUint8List();
        if (bytes.isEmpty) {
          throw const FormatException('Unexpected end of archive stream');
        }
        writeBytes(bytes);
      }
    } finally {
      stream.setPosition(start);
    }
  }

  @override
  Uint8List subset(int start, [int? end]) =>
      throw const FormatException('Decoder whole-output readback is forbidden');
}

// CRC32 checks ZIP payload integrity after decoding. This detects damaged
// archives, not malicious replacement; R03 adds trusted SHA-256 provenance.
final List<int> _crcTable = List<int>.generate(256, (index) {
  var value = index;
  for (var i = 0; i < 8; i++) {
    value = (value & 1) != 0
        ? (value >>> 1) ^ 0xedb88320
        : value >>> 1;
  }
  return value;
}, growable: false);

int _fileCrc32(File file) {
  var crc = 0xffffffff;
  final reader = file.openSync();
  try {
    while (true) {
      final chunk = reader.readSync(64 * 1024);
      if (chunk.isEmpty) break;
      for (final byte in chunk) {
        crc = _crcTable[(crc ^ byte) & 0xff] ^ (crc >>> 8);
      }
    }
  } finally {
    reader.closeSync();
  }
  return (~crc) & 0xffffffff;
}

String _safeRelativePath(String original, ArchiveExtractionLimits limits) {
  if (original.isEmpty || original.length > limits.maxPathLength ||
      original.contains('\\') || original.contains('\u0000') ||
      original.startsWith('/') || original.startsWith('~') ||
      RegExp(r'^[a-zA-Z]:').hasMatch(original) ||
      Uri.tryParse(original)?.hasScheme == true) {
    throw const FormatException('Unsafe archive entry path');
  }
  // Reject mixed separators, dot segments and empty components instead of
  // silently normalizing them into another file's path.
  final name = original.endsWith('/')
      ? original.substring(0, original.length - 1)
      : original;
  final parts = name.split('/');
  if (parts.isEmpty || parts.length > limits.maxDepth ||
      parts.any((part) => part.isEmpty || part == '.' || part == '..')) {
    throw const FormatException('Unsafe archive path components');
  }
  return parts.join('/');
}

void _checkArchiveInput(String path, ArchiveExtractionLimits limits) {
  final source = File(path);
  if (FileSystemEntity.typeSync(source.path, followLinks: false) !=
      FileSystemEntityType.file || source.lengthSync() > limits.maxArchiveBytes) {
    throw const FormatException('Archive missing, linked or too large');
  }
}

/// Strict, streaming ZIP reader for the install archive subset. No ZIP64,
// multi-disk, encryption or exotic methods: our archive cap is <4GiB.
// Inspect directory and local headers before any decoder is entered.
class _ZipEntry {
  const _ZipEntry(this.name, this.offset, this.compressed, this.expanded,
      this.crc, this.method, this.directory);
  final String name;
  final int offset, compressed, expanded, crc, method;
  final bool directory;
}

Uint8List _readAt(RandomAccessFile input, int offset, int length) {
  if (offset < 0 || length < 0 || offset > input.lengthSync() - length) {
    throw const FormatException('Archive extent outside input');
  }
  input.setPositionSync(offset);
  final bytes = input.readSync(length);
  if (bytes.length != length) throw const FormatException('Truncated archive');
  return bytes;
}

int _u16(Uint8List b, int at) => ByteData.sublistView(b).getUint16(at, Endian.little);
int _u32(Uint8List b, int at) => ByteData.sublistView(b).getUint32(at, Endian.little);

List<_ZipEntry> _readZipInventory(RandomAccessFile input, ArchiveExtractionLimits limits) {
  final size = input.lengthSync();
  final tailSize = size < 65557 ? size : 65557;
  final tail = _readAt(input, size - tailSize, tailSize);
  var end = -1;
  for (var i = tail.length - 22; i >= 0; i--) {
    if (_u32(tail, i) == 0x06054b50 && i + 22 + _u16(tail, i + 20) == tail.length) {
      end = i;
      break;
    }
  }
  if (end < 0 || _u16(tail, end + 4) != 0 || _u16(tail, end + 6) != 0) {
    throw const FormatException('Missing or multi-disk ZIP directory');
  }
  final count = _u16(tail, end + 10);
  final length = _u32(tail, end + 12);
  final start = _u32(tail, end + 16);
  final endOffset = size - tailSize + end;
  if (count == 0 || count > limits.maxEntries || count != _u16(tail, end + 8) ||
      length > limits.maxMetadataBytes || start + length != endOffset) {
    throw const FormatException('ZIP inventory exceeds metadata budget or is inconsistent');
  }
  final entries = <_ZipEntry>[];
  final occupied = <(int, int)>[];
  final seen = <String>{};
  var expandedBytes = 0;
  var cursor = start;
  for (var i = 0; i < count; i++) {
    final header = _readAt(input, cursor, 46);
    if (_u32(header, 0) != 0x02014b50 || cursor + 46 > endOffset) {
      throw const FormatException('Invalid ZIP central header');
    }
    final flags = _u16(header, 8);
    final method = _u16(header, 10);
    final crc = _u32(header, 16);
    final compressed = _u32(header, 20);
    final expanded = _u32(header, 24);
    final nameLength = _u16(header, 28);
    final extraLength = _u16(header, 30);
    final commentLength = _u16(header, 32);
    final mode = _u32(header, 38) >> 16;
    final fileType = mode & 0xf000;
    final localOffset = _u32(header, 42);
    final next = cursor + 46 + nameLength + extraLength + commentLength;
    // Bit 3: descriptor. Bits 1/2: deflate tuning. Bit 11: UTF8.
    if (flags & ~0x080e != 0 || !const [0, 8, 12].contains(method) ||
        _u16(header, 34) != 0 || nameLength == 0 || nameLength > limits.maxPathLength * 4 ||
        next > endOffset || !const [0, 0x4000, 0x8000].contains(fileType) ||
        expanded > limits.maxEntryBytes || expanded > limits.maxExpandedBytes - expandedBytes) {
      throw const FormatException('Unsupported or oversized ZIP member');
    }
    final rawName = _readAt(input, cursor + 46, nameLength);
    final original = utf8.decode(rawName);
    final relative = _safeRelativePath(original, limits);
    final directory = original.endsWith('/');
    if (!seen.add(relative.toLowerCase()) || (fileType == 0x4000 && !directory) ||
        (directory && expanded != 0) || (method == 0 && compressed != expanded)) {
      throw const FormatException('Duplicate or inconsistent ZIP member');
    }
    final local = _readAt(input, localOffset, 30);
    if (_u32(local, 0) != 0x04034b50 || _u16(local, 6) != flags ||
        _u16(local, 8) != method || _u16(local, 26) != nameLength ||
        localOffset + 30 + nameLength > start ||
        !_sameBytes(rawName, _readAt(input, localOffset + 30, nameLength))) {
      throw const FormatException('ZIP local/central metadata mismatch');
    }
    final payload = localOffset + 30 + nameLength + _u16(local, 28);
    var after = payload + compressed;
    if (after > start) throw const FormatException('ZIP payload overlaps directory');
    if (flags & 8 == 0) {
      if (_u32(local, 14) != crc || _u32(local, 18) != compressed || _u32(local, 22) != expanded) {
        throw const FormatException('ZIP local size or checksum mismatch');
      }
    } else {
      if (_u32(_readAt(input, after, 4), 0) == 0x08074b50) after += 4;
      final descriptor = _readAt(input, after, 12);
      if (_u32(descriptor, 0) != crc || _u32(descriptor, 4) != compressed || _u32(descriptor, 8) != expanded) {
        throw const FormatException('Invalid ZIP data descriptor');
      }
      after += 12;
    }
    if (after > start) throw const FormatException('ZIP descriptor overlaps directory');
    occupied.add((localOffset, after));
    entries.add(_ZipEntry(relative, payload, compressed, expanded, crc, method, directory));
    expandedBytes += expanded;
    cursor = next;
  }
  if (cursor != endOffset) throw const FormatException('ZIP directory has unaccounted entries');
  occupied.sort((a, b) => a.$1.compareTo(b.$1));
  for (var i = 1; i < occupied.length; i++) {
    if (occupied[i].$1 < occupied[i - 1].$2) {
      throw const FormatException('Overlapping ZIP entries');
    }
  }
  return entries;
}

bool _sameBytes(List<int> a, List<int> b) {
  if (a.length != b.length) return false;
  for (var i = 0; i < a.length; i++) {
    if (a[i] != b[i]) return false;
  }
  return true;
}

// A ChunkedConversionSink.withCallback accumulates all chunks until close.
// This sink writes immediately and cannot retain the decoded archive in RAM.
class _ImmediateDecodeSink implements Sink<List<int>> {
  _ImmediateDecodeSink(this.output);
  final _LimitedOutputStream output;
  @override
  void add(List<int> bytes) => output.writeBytes(bytes);
  @override
  void close() => output.flush();
}

void _decodeZlibRange(RandomAccessFile source, int offset, int length,
    _LimitedOutputStream output, {required bool gzip}) {
  final converter = gzip ? GZipCodec().decoder : ZLibCodec(raw: true).decoder;
  final sink = converter.startChunkedConversion(_ImmediateDecodeSink(output));
  source.setPositionSync(offset);
  var remaining = length;
  while (remaining > 0) {
    final chunk = source.readSync(remaining < 1024 ? remaining : 1024);
    if (chunk.isEmpty) throw const FormatException('Truncated compressed stream');
    remaining -= chunk.length;
    sink.add(chunk);
  }
  sink.close();
}

// archive 4.3.0's BZIP2 decoder returns true if its outer loop sees
// input EOS before the real end marker. Override only its byte-oriented input
// boundary: every physical overread throws, and success requires consumption
// through the actual end marker and combined CRC. No synthetic zero bytes.
class _StrictBzipInput extends archive.InputFileStream {
  _StrictBzipInput(super.source, int offset, int count)
      : super.fromFileStream(position: offset, length: count, bufferSize: 65536);

  @override
  bool get isEOS => false;

  @override
  int readByte() {
    if (fileRemaining <= 0) {
      throw const FormatException('Truncated BZIP2 stream');
    }
    return super.readByte();
  }
}

void _decodeBzipRange(archive.InputFileStream source, int offset, int length,
    _LimitedOutputStream output) {
  final strict = _StrictBzipInput(source, offset, length);
  // BZIP2 block size is one of 1..9, so the pinned decoder's largest
  // Uint32List dictionary is 900000 words (3.6 MB). Reject BZh0.
  final header = strict.readBytes(4).toUint8List();
  if (header.length != 4 || header[0] != 66 || header[1] != 90 ||
      header[2] != 104 || header[3] < 49 || header[3] > 57) {
    throw const FormatException('Invalid BZIP2 block size');
  }
  strict.reset();
  if (!archive.BZip2Decoder().decodeStream(strict, output, verify: true) ||
      strict.fileRemaining != 0) {
    throw const FormatException('Invalid or trailing BZIP2 stream');
  }
}

void _extractZipStreaming(String path, Directory stage, ArchiveExtractionLimits limits) {
  final source = File(path).openSync();
  try {
    final entries = _readZipInventory(source, limits);
    for (final entry in entries) {
      if (entry.directory) {
        Directory('${stage.path}/${entry.name}').createSync(recursive: true);
        continue;
      }
      final file = File('${stage.path}/${entry.name}');
      file.parent.createSync(recursive: true);
      final output = archive.OutputFileStream(file.path, bufferSize: 65536);
      final limited = _LimitedOutputStream(output, entry.expanded);
      try {
        if (entry.method == 0) {
          source.setPositionSync(entry.offset);
          var remaining = entry.compressed;
          while (remaining > 0) {
            final chunk = source.readSync(remaining < 65536 ? remaining : 65536);
            if (chunk.isEmpty) throw const FormatException('Truncated stored ZIP entry');
            limited.writeBytes(chunk);
            remaining -= chunk.length;
          }
        } else if (entry.method == 8) {
          _decodeZlibRange(source, entry.offset, entry.compressed, limited, gzip: false);
        } else {
          final input = archive.InputFileStream(path, bufferSize: 65536);
          try {
            _decodeBzipRange(input, entry.offset, entry.compressed, limited);
          } finally {
            input.closeSync();
          }
        }
        output.flush();
        if (limited.written != entry.expanded) throw const FormatException('ZIP decoded size mismatch');
      } finally {
        output.closeSync();
      }
      if (_fileCrc32(file) != entry.crc) throw const FormatException('ZIP entry checksum mismatch');
    }
  } finally {
    source.closeSync();
  }
}

// Parse TAR as a sequence of bounded headers and file extents. The archive
// library's PAX/long-name parser materializes metadata before its callback.
String _tarString(Uint8List bytes, int start, int length) {
  var end = start;
  while (end < start + length && bytes[end] != 0) { end++; }
  return utf8.decode(Uint8List.sublistView(bytes, start, end));
}

int _tarOctal(Uint8List bytes, int start, int length) {
  final value = _tarString(bytes, start, length).trim();
  if (value.isEmpty || !RegExp(r'^[0-7]+$').hasMatch(value)) {
    throw const FormatException('Unsupported TAR numeric encoding');
  }
  return int.parse(value, radix: 8);
}

String? _paxPath(Uint8List data, int maxPathLength) {
  var at = 0;
  String? path;
  final keys = <String>{};
  while (at < data.length) {
    var space = at;
    while (space < data.length && data[space] >= 48 && data[space] <= 57) { space++; }
    if (space == at || space - at > 9 || space >= data.length || data[space] != 32) {
      throw const FormatException('Malformed TAR PAX record');
    }
    final count = int.parse(ascii.decode(data.sublist(at, space)));
    final end = at + count;
    if (end <= space + 2 || end > data.length || data[end - 1] != 10) {
      throw const FormatException('Malformed TAR PAX length');
    }
    final record = utf8.decode(data.sublist(space + 1, end - 1));
    final eq = record.indexOf('=');
    if (eq <= 0 || !keys.add(record.substring(0, eq))) {
      throw const FormatException('Duplicate or malformed TAR PAX key');
    }
    final key = record.substring(0, eq);
    final value = record.substring(eq + 1);
    if (key == 'path') {
      if (value.length > maxPathLength) throw const FormatException('Oversized PAX path');
      path = value;
    } else if (!const {'mtime','atime','ctime','uid','gid','uname','gname','comment'}.contains(key)) {
      // Do not ignore size, linkpath, sparse extents or other semantic overrides.
      throw const FormatException('Unsupported TAR PAX metadata');
    }
    at = end;
  }
  return path;
}

void _extractTarStreaming(String path, Directory stage, ArchiveExtractionLimits limits) {
  final source = File(path).openSync();
  try {
    final size = source.lengthSync();
    var at = 0, entries = 0, files = 0, total = 0, metadata = 0;
    final seen = <String>{};
    String? nextName;
    var pendingMetadata = false;
    var terminated = false;
    while (at < size) {
      final header = _readAt(source, at, 512);
      at += 512;
      if (header.every((b) => b == 0)) {
        if (pendingMetadata || !_readAt(source, at, 512).every((b) => b == 0)) {
          throw const FormatException('Incomplete TAR terminator');
        }
        at += 512;
        while (at < size) {
          final chunk = _readAt(source, at, size - at < 65536 ? size - at : 65536);
          if (chunk.any((b) => b != 0)) throw const FormatException('Trailing TAR payload');
          at += chunk.length;
        }
        terminated = true;
        break;
      }
      if (++entries > limits.maxEntries || (metadata += 512) > limits.maxMetadataBytes) {
        throw const FormatException('TAR metadata/entry limit');
      }
      var checksum = 0;
      for (var i = 0; i < 512; i++) { checksum += (i >= 148 && i < 156) ? 32 : header[i]; }
      if (checksum != _tarOctal(header, 148, 8)) throw const FormatException('TAR header checksum mismatch');
      final length = _tarOctal(header, 124, 12);
      final after = at + ((length + 511) ~/ 512) * 512;
      if (length < 0 || after > size) throw const FormatException('Truncated TAR payload');
      final type = header[156];
      if (type == 120 || type == 76) { // POSIX PAX local or GNU long name.
        if (pendingMetadata || length > 65536 || length > limits.maxMetadataBytes - metadata) {
          throw const FormatException('TAR extension metadata exceeds limit');
        }
        final data = _readAt(source, at, length);
        metadata += length;
        nextName = type == 120 ? _paxPath(data, limits.maxPathLength) : _tarString(data, 0, data.length);
        pendingMetadata = true;
        at = after;
        continue;
      }
      if (type != 0 && type != 48 && type != 53) {
        throw const FormatException('TAR links, special entries and sparse files are unsupported');
      }
      final name = _tarString(header, 0, 100);
      // POSIX ustar prefix; GNU magic uses a space, not a NUL.
      final prefix = _tarString(header, 257, 6) == 'ustar'
          ? _tarString(header, 345, 155) : '';
      final relative = _safeRelativePath(nextName ?? (prefix.isEmpty ? name : '$prefix/$name'), limits);
      nextName = null;
      pendingMetadata = false;
      if (!seen.add(relative.toLowerCase()) || length > limits.maxEntryBytes || length > limits.maxExpandedBytes - total) {
        throw const FormatException('TAR duplicate member or expanded-size limit');
      }
      if (type == 53) {
        if (length != 0) throw const FormatException('Nonempty TAR directory');
        Directory('${stage.path}/$relative').createSync(recursive: true);
      } else {
        final file = File('${stage.path}/$relative');
        file.parent.createSync(recursive: true);
        final output = file.openSync(mode: FileMode.write);
        try {
          var written = 0;
          while (written < length) {
            final count = length - written < 65536 ? length - written : 65536;
            final chunk = _readAt(source, at + written, count);
            output.writeFromSync(chunk);
            written += count;
          }
          output.flushSync();
        } finally {
          output.closeSync();
        }
        total += length;
        files++;
      }
      at = after;
    }
    if (!terminated || files == 0) throw const FormatException('Incomplete or empty TAR');
  } finally {
    source.closeSync();
  }
}

// The pinned archive 4.3.0 XZ decoder derives its dictionary cap from each
// attacker-supplied block and uses a temporary whole-block buffer for verify
// or BCJ. Preflight the *actual* LZMA2 chunk boundaries, not just the index,
// refuse non-LZMA2 filters, bound the dictionary, then verify each block check
// from the streamed TAR file independently. No decoded whole-block buffer.
class _XzBlockCheck {
  const _XzBlockCheck(this.offset, this.length, this.type, this.expected);
  final int offset, length, type;
  final Uint8List expected;
}

(int, int) _xzVli(Uint8List bytes, int start, int end) {
  var value = 0;
  for (var n = 0; n < 9 && start + n < end; n++) {
    final b = bytes[start + n];
    value |= (b & 127) << (7 * n);
    if (b & 128 == 0) {
      if (n != 0 && b == 0) throw const FormatException('Noncanonical XZ integer');
      return (value, start + n + 1);
    }
  }
  throw const FormatException('Oversized XZ integer');
}

List<_XzBlockCheck> _preflightXz(String path, ArchiveExtractionLimits limits) {
  final input = File(path).openSync();
  try {
    final size = input.lengthSync();
    var at = 0, total = 0, metadata = 0, streams = 0;
    final checks = <_XzBlockCheck>[];
    while (at < size) {
      if (++streams > limits.maxEntries) {
        throw const FormatException('XZ concatenated-stream budget exceeded');
      }
      final origin = at;
      final stream = _readAt(input, at, 12);
      if (!_sameBytes(stream.sublist(0, 6), const [253,55,122,88,90,0]) || stream[6] != 0) {
        throw const FormatException('Invalid XZ stream header');
      }
      final checkType = stream[7];
      final checkSize = switch (checkType) { 1 => 4, 4 => 8, 10 => 32, _ => 0 };
      if (checkSize == 0) throw const FormatException('Unsupported XZ integrity check');
      at += 12;
      final records = <(int, int)>[];
      while (true) {
        final code = _readAt(input, at, 1).single;
        if (code == 0) break;
        final start = at;
        final headerSize = (code + 1) * 4;
        final header = _readAt(input, at, headerSize);
        final end = headerSize - 4;
        final flags = header[1];
        if (flags & 0x3f != 0 || checks.length >= limits.maxEntries) {
          throw const FormatException('Unsupported XZ filters or block budget');
        }
        metadata += headerSize;
        if (metadata > limits.maxMetadataBytes) throw const FormatException('XZ metadata limit');
        var p = 2;
        int? compressed, expanded;
        if (flags & 0x40 != 0) { final v = _xzVli(header, p, end); compressed = v.$1; p = v.$2; }
        if (flags & 0x80 != 0) { final v = _xzVli(header, p, end); expanded = v.$1; p = v.$2; }
        final id = _xzVli(header, p, end); p = id.$2;
        final props = _xzVli(header, p, end); p = props.$2;
        if (id.$1 != 0x21 || props.$1 != 1 || p >= end || header[p] > 24) {
          // 24 encodes a 16 MiB dictionary; pin this hard maximum independent
          // of the expanded output budget and caller-supplied limits.
          throw const FormatException('XZ dictionary/filter memory limit');
        }
        p++;
        if (header.sublist(p, end).any((b) => b != 0)) throw const FormatException('Invalid XZ header padding');
        at += headerSize;
        final payloadStart = at;
        var outputLength = 0;
        while (true) {
          final control = _readAt(input, at++, 1).single;
          if (control == 0) break;
          int chunkBytes, decodedBytes;
          if (control == 1 || control == 2) {
            final h = _readAt(input, at, 2); at += 2;
            chunkBytes = (h[0] << 8 | h[1]) + 1;
            decodedBytes = chunkBytes;
          } else if (control >= 128) {
            final propertyByte = control >= 192;
            final h = _readAt(input, at, propertyByte ? 5 : 4);
            at += h.length;
            decodedBytes = ((control & 31) << 16 | h[0] << 8 | h[1]) + 1;
            chunkBytes = (h[2] << 8 | h[3]) + 1;
            if (propertyByte && (h[4] > 224 || (h[4] % 45) ~/ 9 + h[4] % 9 > 4)) {
              throw const FormatException('Invalid LZMA2 properties');
            }
          } else {
            throw const FormatException('Invalid LZMA2 chunk');
          }
          if (at > size - chunkBytes || decodedBytes > limits.maxExpandedBytes - total - outputLength) {
            throw const FormatException('XZ compressed or expanded extent exceeds budget');
          }
          outputLength += decodedBytes;
          at += chunkBytes;
        }
        if ((compressed != null && compressed != at - payloadStart) ||
            (expanded != null && expanded != outputLength)) {
          throw const FormatException('XZ block length mismatch');
        }
        final unpadded = at - start + checkSize;
        while ((at - origin) % 4 != 0) {
          if (_readAt(input, at++, 1).single != 0) throw const FormatException('Invalid XZ block padding');
        }
        final expected = _readAt(input, at, checkSize);
        at += checkSize;
        checks.add(_XzBlockCheck(total, outputLength, checkType, expected));
        records.add((unpadded, outputLength));
        total += outputLength;
      }
      // Index fields are small, canonical VLIs, with a known block count.
      final indexStart = at++;
      int readVli() {
        final bytes = _readAt(input, at, size - at < 9 ? size - at : 9);
        final v = _xzVli(bytes, 0, bytes.length); at += v.$2; return v.$1;
      }
      if (readVli() != records.length) throw const FormatException('XZ index block count mismatch');
      for (final record in records) {
        if (readVli() != record.$1 || readVli() != record.$2) throw const FormatException('XZ index mismatch');
      }
      while ((at - origin) % 4 != 0) {
        if (_readAt(input, at++, 1).single != 0) throw const FormatException('Invalid XZ index padding');
      }
      at += 4; // The pinned decoder independently checks the index CRC.
      final footer = _readAt(input, at, 12);
      if ((_u32(footer, 4) + 1) * 4 != at - indexStart || footer[8] != 0 || footer[9] != checkType || footer[10] != 89 || footer[11] != 90) {
        throw const FormatException('XZ footer mismatch');
      }
      at += 12;
      final paddingStart = at;
      while (at < size && _readAt(input, at, 1).single == 0) { at++; }
      if ((at - paddingStart) % 4 != 0) throw const FormatException('Invalid XZ stream padding');
    }
    if (checks.isEmpty || total == 0) throw const FormatException('Empty XZ stream');
    return checks;
  } finally {
    input.closeSync();
  }
}

class _DigestSink implements Sink<Digest> {
  Digest? digest;
  @override
  void add(Digest data) { digest = data; }
  @override
  void close() {}
}

void _verifyXzChecks(String path, List<_XzBlockCheck> checks) {
  final file = File(path).openSync();
  try {
    if (file.lengthSync() != checks.last.offset + checks.last.length) throw const FormatException('XZ decoded length mismatch');
    for (final block in checks) {
      var crc32 = 0xffffffff, crc64 = -1;
      final digests = _DigestSink();
      final hash = block.type == 10 ? sha256.startChunkedConversion(digests) : null;
      var offset = block.offset, remaining = block.length;
      while (remaining > 0) {
        final bytes = _readAt(file, offset, remaining < 65536 ? remaining : 65536);
        if (block.type == 1) {
          for (final byte in bytes) { crc32 = _crcTable[(crc32 ^ byte) & 255] ^ (crc32 >>> 8); }
        } else if (block.type == 4) {
          for (final byte in bytes) {
            crc64 ^= byte;
            for (var bit = 0; bit < 8; bit++) {
              crc64 = (crc64 >>> 1) ^ ((crc64 & 1) != 0 ? 0xc96c5795d7870f42 : 0);
            }
          }
        } else { hash!.add(bytes); }
        offset += bytes.length; remaining -= bytes.length;
      }
      hash?.close();
      final List<int> actual;
      if (block.type == 1) {
        final data = ByteData(4)..setUint32(0, (~crc32) & 0xffffffff, Endian.little);
        actual = data.buffer.asUint8List();
      } else if (block.type == 4) {
        final data = ByteData(8)..setUint64(0, ~crc64, Endian.little);
        actual = data.buffer.asUint8List();
      } else {
        actual = digests.digest!.bytes;
      }
      if (!_sameBytes(actual, block.expected)) throw const FormatException('XZ block checksum mismatch');
    }
  } finally {
    file.closeSync();
  }
}

// Worker-side decoding. The caller owns staging and publication.
void _extractArchive(
  String path,
  String work, {
  required bool tarball,
  required ArchiveExtractionLimits limits,
}) {
  limits.validate();
  _checkArchiveInput(path, limits);
  final stage = Directory('$work/output')..createSync();
  if (!tarball) {
    _extractZipStreaming(path, stage, limits);
    return;
  }
  final input = archive.InputFileStream(path, bufferSize: 65536);
  try {
    final signature = input.peekBytes(6).toUint8List();
    final gzip = signature.length >= 2 && signature[0] == 0x1f && signature[1] == 0x8b;
    final bzip = signature.length >= 3 && signature[0] == 0x42 && signature[1] == 0x5a && signature[2] == 0x68;
    final xz = signature.length >= 6 && _sameBytes(signature, const [253,55,122,88,90,0]);
    if (!gzip && !bzip && !xz) {
      _extractTarStreaming(path, stage, limits);
      return;
    }
    final temporaryTar = Directory('$work/decoded')..createSync();
    final tarPath = '${temporaryTar.path}/archive.tar';
    final xzChecks = xz ? _preflightXz(path, limits) : null;
    final output = archive.OutputFileStream(tarPath, bufferSize: 65536);
    try {
      final bounded = _LimitedOutputStream(output, limits.maxExpandedBytes);
      if (gzip) {
        final gzipInput = File(path).openSync();
        try {
          _decodeZlibRange(gzipInput, 0, gzipInput.lengthSync(), bounded, gzip: true);
        } finally {
          gzipInput.closeSync();
        }
      } else if (bzip) {
        _decodeBzipRange(input, 0, input.length, bounded);
      } else {
        if (!archive.XZDecoder().decodeStream(input, bounded, verify: false)) {
          throw const FormatException('Invalid XZ archive');
        }
      }
    } finally {
      output.closeSync();
    }
    if (xzChecks != null) _verifyXzChecks(tarPath, xzChecks);
    _extractTarStreaming(tarPath, stage, limits);
  } finally {
    input.closeSync();
  }
}
