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
  });

  final int maxArchiveBytes;
  final int maxExpandedBytes;
  final int maxEntryBytes;
  final int maxEntries;
  final int maxDepth;
  final int maxPathLength;

  void validate() {
    if (maxArchiveBytes <= 0 || maxExpandedBytes <= 0 ||
        maxEntryBytes <= 0 || maxEntries <= 0 ||
        maxDepth <= 0 || maxPathLength <= 0 ||
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
}) => Isolate.run(
  () => _extractArchive(path, destination, tarball: false, limits: limits),
  debugName: 'artifact-zip-extraction',
);

Future<void> extractTarballOffIsolate(
  String path,
  String destination, {
  ArchiveExtractionLimits limits = const ArchiveExtractionLimits(),
}) => Isolate.run(
  () => _extractArchive(path, destination, tarball: true, limits: limits),
  debugName: 'artifact-tar-extraction',
);

/// Enforces actual bytes sent to the file, not only potentially forged archive
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
  void clear() => output.clear();

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
    final buffer = Uint8List(chunkBytes);
    try {
      while (!stream.isEOS) {
        final got = stream.readInto(buffer, 0, buffer.length);
        if (got <= 0) break;
        writeBytes(buffer, length: got);
      }
    } finally {
      stream.setPosition(start);
    }
  }

  @override
  Uint8List subset(int start, [int? end]) => output.subset(start, end);
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

/// Only writes to a fresh private sibling directory. It is renamed into the
/// destination after every file has been validated and fully extracted.
void _extractArchive(
  String path,
  String destination, {
  required bool tarball,
  required ArchiveExtractionLimits limits,
}) {
  limits.validate();
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
  final stage = parent.createTempSync('.obtainx-extract-');
  archive.InputFileStream? input;
  archive.InputFileStream? decodedInput;
  Directory? temporaryTar;
  bool published = false;
  try {
    input = archive.InputFileStream(path);
    if (tarball) {
      final signature = input.peekBytes(6).toUint8List();
      final gzip = signature.length >= 2 &&
          signature[0] == 0x1f && signature[1] == 0x8b;
      final bzip = signature.length >= 3 &&
          signature[0] == 0x42 && signature[1] == 0x5a && signature[2] == 0x68;
      final xz = signature.length >= 6 &&
          signature[0] == 0xfd && signature[1] == 0x37 &&
          signature[2] == 0x7a && signature[3] == 0x58 &&
          signature[4] == 0x5a && signature[5] == 0x00;
      if (gzip || bzip || xz) {
        temporaryTar = Directory.systemTemp.createTempSync('obtainx-decoded-');
        final tarPath = '${temporaryTar.path}/archive.tar';
        final output = archive.OutputFileStream(tarPath);
        try {
          final bounded = _LimitedOutputStream(output, limits.maxExpandedBytes);
          if (gzip) {
            const archive.GZipDecoder().decodeStream(input, bounded);
          } else if (bzip) {
            archive.BZip2Decoder().decodeStream(input, bounded);
          } else {
            archive.XZDecoder().decodeStream(input, bounded);
          }
        } finally {
          output.closeSync();
        }
        decodedInput = archive.InputFileStream(tarPath);
      }
    }
    late final archive.Archive contents;
    if (tarball) {
      var decodedEntries = 0;
      contents = archive.TarDecoder().decodeStream(
        decodedInput ?? input,
        callback: (entry) {
          if (++decodedEntries > limits.maxEntries) {
            throw const FormatException('Too many TAR entries');
          }
        },
      );
    } else {
      final decoder = archive.ZipDecoder();
      contents = decoder.decodeStream(input);
      // archive v4 coalesces duplicate ZIP filenames in its Archive model.
      // Inspect the original central-directory headers to reject them instead.
      final headerNames = <String>{};
      for (final header in decoder.directory.fileHeaders) {
        if (headerNames.length >= limits.maxEntries) {
          throw const FormatException('Too many ZIP entries');
        }
        final rawName = header.file?.filename;
        if (rawName == null ||
            !headerNames.add(_safeRelativePath(rawName, limits).toLowerCase())) {
          throw const FormatException('Duplicate or malformed ZIP entry');
        }
      }
    }
    final seen = <String>{};
    var fileCount = 0;
    var totalBytes = 0;
    for (final entry in contents) {
      if (++fileCount > limits.maxEntries) {
        throw const FormatException('Too many archive entries');
      }
      // Reject links rather than following or silently skipping them.
      if (entry.isSymbolicLink || (entry.mode & 0xf000) == 0xa000) {
        throw const FormatException('Archive contains a symbolic link');
      }
      final relative = _safeRelativePath(entry.name, limits);
      if (!seen.add(relative.toLowerCase())) {
        throw const FormatException('Duplicate archive entry');
      }
      if (!entry.isFile) continue;
      if (entry.size < 0 || entry.size > limits.maxEntryBytes ||
          entry.size > limits.maxExpandedBytes - totalBytes) {
        throw const FormatException('Archive expanded-size budget exceeded');
      }
      final file = File('${stage.path}/$relative');
      file.parent.createSync(recursive: true);
      final output = archive.OutputFileStream(file.path);
      final limited = _LimitedOutputStream(
        output,
        limits.maxEntryBytes < limits.maxExpandedBytes - totalBytes
            ? limits.maxEntryBytes
            : limits.maxExpandedBytes - totalBytes,
      );
      try {
        entry.writeContent(limited);
        output.flush();
        if (limited.written != entry.size) {
          throw const FormatException('Archive entry size mismatch');
        }
      } finally {
        output.closeSync();
      }
      if (!tarball && entry.crc32 != null &&
          _fileCrc32(file) != entry.crc32) {
        throw const FormatException('ZIP entry checksum mismatch');
      }
      totalBytes += limited.written;
    }
    if (fileCount == 0) {
      throw const FormatException('Empty archive');
    }
    if (FileSystemEntity.typeSync(target.path, followLinks: false) !=
        FileSystemEntityType.notFound) {
      throw const FormatException('Extraction destination changed');
    }
    stage.renameSync(target.path);
    published = true;
  } finally {
    decodedInput?.closeSync();
    input?.closeSync();
    if (temporaryTar != null && temporaryTar.existsSync()) {
      temporaryTar.deleteSync(recursive: true);
    }
    if (!published && stage.existsSync()) stage.deleteSync(recursive: true);
  }
}
