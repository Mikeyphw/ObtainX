// R03: persisted, validator-bound, resumable downloads. No trusted remote
// attestation is inferred from a locally computed content hash.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:crypto/crypto.dart';

const int r03ChunkBytes = 1024 * 1024;
const int r03MaximumBytes = 4 * 1024 * 1024 * 1024;

enum R03Stage {
  queued, checking, downloading, downloaded, verifying, extracting, ready,
  awaitingApproval, installing, confirming, completed, paused, cancelled,
  retrying, failed,
}

class R03DownloadHttpException implements Exception {
  const R03DownloadHttpException(this.statusCode, {this.retryAfterSeconds});
  final int statusCode;
  final int? retryAfterSeconds;

  @override
  String toString() => 'R03 HTTP $statusCode';
}

class R03InvalidEntityException implements Exception {
  const R03InvalidEntityException(this.reason);
  final String reason;

  @override
  String toString() => 'R03 invalid download entity: $reason';
}

/// A persistent receipt contains no bearer tokens, URL query strings, or
/// authorization headers. The actual URL and credentials are re-resolved from
/// the tracked source on each operation, including after application restart.
/// Optional exact history owner; absent on legacy or non-library transfers.
class R03HistoryBinding {
  R03HistoryBinding(this.listingKey, this.packageId, this.channel) {
    if (listingKey.isEmpty || listingKey.length > 1000 ||
        listingKey.contains(RegExp(r'[\x00-\x1f/\\]')) ||
        !RegExp(r'^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$').hasMatch(packageId) ||
        packageId.length > 255 || !RegExp(r'^[a-f0-9]{64}$').hasMatch(channel)) {
      throw const FormatException('Invalid R03 history owner');
    }
  }
  final String listingKey, packageId, channel;
  Map<String, String> toJson() => {'listingKey': listingKey, 'packageId': packageId, 'channel': channel};
  static R03HistoryBinding? decode(Object? value) {
    if (value == null) return null;
    if (value is! Map || value.length != 3 || value['listingKey'] is! String ||
        value['packageId'] is! String || value['channel'] is! String) {
      throw const FormatException('Invalid R03 history binding');
    }
    return R03HistoryBinding(value['listingKey'] as String, value['packageId'] as String,
        value['channel'] as String);
  }
  @override
  bool operator ==(Object other) => other is R03HistoryBinding &&
      other.listingKey == listingKey && other.packageId == packageId && other.channel == channel;
  @override
  int get hashCode => Object.hash(listingKey, packageId, channel);
}

class R03DownloadRecord {
  const R03DownloadRecord({
    required this.jobId,
    required this.sourceFingerprint,
    required this.origin,
    required this.finalOrigin,
    required this.fileName,
    required this.stage,
    required this.blocks,
    this.totalBytes,
    this.etag,
    this.lastModified,
    this.finalDigest,
    this.completedBytes,
    this.historyBinding,
  });

  final String jobId;
  final String sourceFingerprint;
  final String origin;
  final String finalOrigin;
  final String fileName;
  final R03Stage stage;
  final List<String> blocks;
  final int? totalBytes;
  final String? etag;
  final String? lastModified;
  final String? finalDigest;
  final int? completedBytes;
  final R03HistoryBinding? historyBinding;

  int get validatedBytes => blocks.length * r03ChunkBytes;
  String? get ifRange => etag ?? lastModified;

  Map<String, Object?> toJson() => {
    'schema': 'obtainx.r03.download.v1',
    if (historyBinding != null) 'historyBinding': historyBinding!.toJson(),
    'jobId': jobId,
    'sourceFingerprint': sourceFingerprint,
    'origin': origin,
    'finalOrigin': finalOrigin,
    'fileName': fileName,
    'stage': stage.name,
    'blocks': blocks,
    'validatedBytes': validatedBytes,
    'totalBytes': totalBytes,
    'etag': etag,
    'lastModified': lastModified,
    'finalDigest': finalDigest,
    'completedBytes': completedBytes,
  };

  factory R03DownloadRecord.fromJson(Map<String, dynamic> input) {
    if (input['schema'] != 'obtainx.r03.download.v1') {
      throw const FormatException('Unknown R03 download journal schema');
    }
    final rawBlocks = input['blocks'];
    if (rawBlocks is! List || rawBlocks.length > 4096 ||
        rawBlocks.any((b) => b is! String ||
          !RegExp(r'^[a-f0-9]{64}$').hasMatch(b))) {
      throw const FormatException('R03 download journal block inventory invalid');
    }
    final blocks = rawBlocks.cast<String>();
    if (input['validatedBytes'] != blocks.length * r03ChunkBytes) {
      throw const FormatException('R03 download journal offset mismatch');
    }
    final state = R03Stage.values.firstWhere(
      (value) => value.name == input['stage'],
      orElse: () => throw const FormatException('R03 invalid operation stage'),
    );
    final total = input['totalBytes'];
    final completed = input['completedBytes'];
    if ((total != null && (total is! int || total < 0 || total > r03MaximumBytes)) ||
        (completed != null && (completed is! int || completed < 0 ||
          completed > r03MaximumBytes))) {
      throw const FormatException('R03 invalid size metadata');
    }
    return R03DownloadRecord(
      jobId: _requiredString(input, 'jobId'),
      sourceFingerprint: _requiredString(input, 'sourceFingerprint'),
      origin: _requiredString(input, 'origin'),
      finalOrigin: _requiredString(input, 'finalOrigin'),
      fileName: _requiredString(input, 'fileName'),
      stage: state,
      blocks: List<String>.unmodifiable(blocks),
      totalBytes: total as int?,
      etag: input['etag'] as String?,
      lastModified: input['lastModified'] as String?,
      finalDigest: input['finalDigest'] as String?,
      completedBytes: completed as int?,
      historyBinding: R03HistoryBinding.decode(input['historyBinding']),
    );
  }

  R03DownloadRecord copyWith({
    R03Stage? stage,
    List<String>? blocks,
    int? totalBytes,
    String? etag,
    String? lastModified,
    String? finalOrigin,
    String? finalDigest,
    int? completedBytes,
  }) => R03DownloadRecord(
    jobId: jobId,
    sourceFingerprint: sourceFingerprint,
    origin: origin,
    finalOrigin: finalOrigin ?? this.finalOrigin,
    fileName: fileName,
    stage: stage ?? this.stage,
    blocks: blocks ?? this.blocks,
    totalBytes: totalBytes ?? this.totalBytes,
    etag: etag ?? this.etag,
    lastModified: lastModified ?? this.lastModified,
    finalDigest: finalDigest ?? this.finalDigest,
    completedBytes: completedBytes ?? this.completedBytes,
    historyBinding: historyBinding,
  );
}

String _requiredString(Map<String, dynamic> map, String key) {
  final value = map[key];
  if (value is! String || value.isEmpty || value.length > 1000) {
    throw FormatException('Invalid R03 field: $key');
  }
  return value;
}

bool r03CanRetryHttpStatus(int statusCode) =>
    statusCode == 408 || statusCode == 429 ||
    (statusCode >= 500 && statusCode <= 599);

int? r03RetryAfterSeconds(String? value, DateTime now) {
  if (value == null) return null;
  final numeric = int.tryParse(value.trim());
  if (numeric != null) return max(0, min(120, numeric));
  final asDate = HttpDate.parse(value.trim());
  return max(0, min(120, asDate.difference(now.toUtc()).inSeconds));
}

String? r03StrongEtag(String? value) {
  if (value == null) return null;
  final tag = value.trim();
  return RegExp(r'^"[^"\r\n]{1,200}"$').hasMatch(tag) ? tag : null;
}

({int start, int end, int total})? r03ContentRange(String? raw) {
  if (raw == null) return null;
  final match = RegExp(r'^bytes (\d+)-(\d+)/(\d+)$').firstMatch(raw.trim());
  if (match == null) return null;
  final start = int.tryParse(match.group(1)!);
  final end = int.tryParse(match.group(2)!);
  final total = int.tryParse(match.group(3)!);
  if (start == null || end == null || total == null || start > end ||
      total < 1 || total > r03MaximumBytes || end >= total) {
    return null;
  }
  return (start: start, end: end, total: total);
}

String r03FinalOrigin(HttpClientResponse response, Uri source) {
  // The HttpService's redirect policy still owns authorization forwarding.
  // A receipt records only the final origin, never a presigned URL/query.
  Uri current = source;
  for (final redirect in response.redirects) {
    current = current.resolveUri(redirect.location);
  }
  return '${current.scheme}://${current.host}${current.hasPort ? ':${current.port}' : ''}';
}

/// Real transfer state survives process termination in an atomic private
/// journal. A committed .part block has a SHA-256 hash in that journal; an
/// uncommitted trailing fragment is truncated on recovery.
class R03DownloadEngine {
  R03DownloadEngine({required this.journalDirectory, this.maxBytes = r03MaximumBytes}) {
    if (maxBytes <= 0 || maxBytes > r03MaximumBytes) {
      throw const R03InvalidEntityException('invalid transfer bound');
    }
  }
  final Directory journalDirectory;
  final int maxBytes;
  static final Map<String, Future<File>> _active = {};
  // A caller with different trusted-byte requirements must never inherit a
  // transfer owned by another caller, even when URL and destination match.
  static final Map<String, String?> _activeExpectedDigest = {};
  static final Map<String, int> _activeMaxBytes = {};
  static final Map<String, R03HistoryBinding?> _activeHistory = {};

  static String jobKey(Uri url, File destination, Map<String, String> headers) {
    final sorted = headers.entries.toList()
      ..sort((a, b) => a.key.toLowerCase().compareTo(b.key.toLowerCase()));
    // Including a digest of the request headers prevents cross-account cache
    // aliasing without ever persisting the secrets themselves.
    return sha256.convert(utf8.encode(jsonEncode([
      url.toString(), destination.absolute.path,
      for (final h in sorted) [h.key.toLowerCase(), h.value],
    ]))).toString();
  }

  Future<File> download({
    required Uri source,
    required File destination,
    required Map<String, String> headers,
    required HttpClientResponse firstResponse,
    required Future<HttpClientResponse> Function(Map<String, String>) fetch,
    required bool Function() isCancelled,
    required void Function(double?, int?, int?)? onProgress,
    bool useExisting = true,
    String? expectedSha256,
    R03HistoryBinding? historyBinding,
  }) {
    final key = jobKey(source, destination, headers);
    final existing = _active[key];
    if (existing != null) {
      unawaited(firstResponse.listen((_) {}).cancel());
      if (_activeExpectedDigest[key] != expectedSha256 || _activeMaxBytes[key] != maxBytes ||
          _activeHistory[key] != historyBinding) {
        return Future<File>.error(const R03InvalidEntityException(
          'conflicting trusted digest for active transfer'));
      }
      return existing;
    }
    final next = _run(
      source: source, destination: destination, headers: headers,
      firstResponse: firstResponse, fetch: fetch,
      isCancelled: isCancelled, onProgress: onProgress,
      useExisting: useExisting, expectedSha256: expectedSha256,
      jobId: key, historyBinding: historyBinding,
    );
    _active[key] = next;
    _activeExpectedDigest[key] = expectedSha256;
    _activeMaxBytes[key] = maxBytes;
    _activeHistory[key] = historyBinding;
    void clearActive() {
      if (identical(_active[key], next)) {
        _active.remove(key);
        _activeExpectedDigest.remove(key);
        _activeMaxBytes.remove(key);
        _activeHistory.remove(key);
      }
    }
    // Consume completion and failure without returning the failed Future from
    // cleanup (a returned Future can re-emit its error into the cleanup chain).
    unawaited(next.then<void>((_) { clearActive(); },
      onError: (Object error, StackTrace trace) { clearActive(); }));
    return next;
  }

  Future<File> _run({
    required Uri source,
    required File destination,
    required Map<String, String> headers,
    required HttpClientResponse firstResponse,
    required Future<HttpClientResponse> Function(Map<String, String>) fetch,
    required bool Function() isCancelled,
    required void Function(double?, int?, int?)? onProgress,
    required bool useExisting,
    required String jobId,
    String? expectedSha256,
    R03HistoryBinding? historyBinding,
  }) async {
    await journalDirectory.create(recursive: true);
    final journal = File('${journalDirectory.path}/$jobId.json');
    final part = File('${destination.path}.part');
    final origin = '${source.scheme}://${source.host}${source.hasPort ? ':${source.port}' : ''}';
    if (await FileSystemEntity.type(destination.path, followLinks: false) ==
            FileSystemEntityType.link ||
        await FileSystemEntity.type(part.path, followLinks: false) ==
            FileSystemEntityType.link ||
        await FileSystemEntity.type(journal.path, followLinks: false) ==
            FileSystemEntityType.link) {
      throw const R03InvalidEntityException('symlink path rejected');
    }
    final R03DownloadRecord initial = R03DownloadRecord(
      jobId: jobId, sourceFingerprint: jobId, origin: origin,
      finalOrigin: origin, fileName: destination.uri.pathSegments.last,
      stage: R03Stage.queued, blocks: const [], historyBinding: historyBinding,
    );
    R03DownloadRecord? previous;
    if (useExisting && await journal.exists()) {
      try {
        final decoded = jsonDecode(await journal.readAsString());
        if (decoded is! Map<String, dynamic>) throw const FormatException('journal map');
        final candidate = R03DownloadRecord.fromJson(decoded);
        if (candidate.jobId == jobId && candidate.sourceFingerprint == jobId &&
            candidate.fileName == initial.fileName && candidate.origin == origin &&
            (candidate.totalBytes ?? 0) <= maxBytes &&
            (candidate.completedBytes ?? 0) <= maxBytes && candidate.validatedBytes <= maxBytes) {
          previous = candidate;
        }
      } catch (_) {
        // A damaged journal must never authorize reusing stale bytes.
      }
    }
    if (previous?.historyBinding != null && previous?.historyBinding != historyBinding) {
      await firstResponse.listen((_) {}).cancel();
      throw const R03InvalidEntityException('conflicting historical owner for transfer');
    }
    var response = firstResponse;
    final effectiveInitial = previous != null && previous.historyBinding == null
        ? R03DownloadRecord(jobId: initial.jobId, sourceFingerprint: initial.sourceFingerprint,
          origin: initial.origin, finalOrigin: initial.finalOrigin, fileName: initial.fileName,
          stage: R03Stage.queued, blocks: const []) : initial;
    var active = effectiveInitial;
    var committed = <String>[];
    var acceptedBytes = 0;
    int? total;
    String? etag;
    String? lastModified;
    var currentOrigin = r03FinalOrigin(firstResponse, source);
    bool eligibleForResume = false;

    try {
      if (isCancelled()) throw const R03InvalidEntityException('cancelled');
      if (previous != null && previous.stage == R03Stage.ready &&
          previous.finalDigest != null && previous.completedBytes != null &&
          await destination.exists() &&
          await destination.length() == previous.completedBytes) {
        final digest = await _sha256File(destination);
        if (digest == previous.finalDigest &&
            (expectedSha256 == null || digest == expectedSha256)) {
          await response.listen((_) {}).cancel();
          return destination;
        }
      }
      if (useExisting && previous != null &&
          previous.ifRange != null && previous.totalBytes != null &&
          previous.totalBytes! > previous.validatedBytes &&
          previous.validatedBytes > 0 && await part.exists() &&
          currentOrigin == previous.finalOrigin &&
          _responseValidatorMatches(previous, firstResponse)) {
        try {
          eligibleForResume = await _verifyBlocks(part, previous.blocks);
        } catch (_) {
          eligibleForResume = false;
        }
      }
      if (eligibleForResume) {
        // Keep only journal-committed, SHA-verified bytes. Never reuse an
        // uncheckpointed fragment left by a terminated process.
        await _truncateTo(part, previous!.validatedBytes);
        committed = List<String>.of(previous.blocks);
        acceptedBytes = previous.validatedBytes;
        await response.listen((_) {}).cancel();
        final resumableHeaders = Map<String, String>.from(headers)
          ..removeWhere((key, _) => key.toLowerCase() == 'range' ||
              key.toLowerCase() == 'if-range')
          ..['range'] = 'bytes=$acceptedBytes-'
          ..['if-range'] = previous.ifRange!;
        response = await fetch(resumableHeaders);
        currentOrigin = r03FinalOrigin(response, source);
        final range = r03ContentRange(response.headers.value(HttpHeaders.contentRangeHeader));
        final correct206 = response.statusCode == HttpStatus.partialContent &&
            range != null && range.start == acceptedBytes &&
            range.total == previous.totalBytes &&
            range.end == range.total - 1 &&
            response.contentLength == range.end - range.start + 1 &&
            response.compressionState != HttpClientResponseCompressionState.decompressed &&
            currentOrigin == previous.finalOrigin &&
            _responseValidatorMatches(previous, response);
        if (!correct206) {
          // Any ignored, invalid or changed range restarts from byte zero;
          // never append these bytes, even when the server returns 206.
          committed.clear();
          acceptedBytes = 0;
          if (response.statusCode != HttpStatus.ok) {
            await response.listen((_) {}).cancel();
            response = await fetch(Map<String, String>.from(headers)
              ..removeWhere((key, _) => key.toLowerCase() == 'range' ||
                  key.toLowerCase() == 'if-range'));
          }
          currentOrigin = r03FinalOrigin(response, source);
        }
      }
      if (response.statusCode != HttpStatus.ok &&
          !(eligibleForResume && acceptedBytes > 0 &&
            response.statusCode == HttpStatus.partialContent)) {
        throw R03DownloadHttpException(response.statusCode,
          retryAfterSeconds: _safeRetryAfter(response.headers.value(HttpHeaders.retryAfterHeader)));
      }
      final responseTotal = response.statusCode == HttpStatus.partialContent
          ? r03ContentRange(response.headers.value(HttpHeaders.contentRangeHeader))?.total
          : (response.contentLength < 0 ||
              response.compressionState == HttpClientResponseCompressionState.decompressed
              ? null : response.contentLength);
      if (responseTotal != null && (responseTotal < acceptedBytes ||
          responseTotal > maxBytes)) {
        throw const R03InvalidEntityException('invalid expected length');
      }
      total = responseTotal;
      etag = r03StrongEtag(response.headers.value(HttpHeaders.etagHeader));
      lastModified = response.headers.value(HttpHeaders.lastModifiedHeader);
      active = effectiveInitial.copyWith(
        stage: R03Stage.downloading, blocks: committed,
        totalBytes: total, etag: etag, lastModified: lastModified,
        finalOrigin: currentOrigin,
      );
      await _save(journal, active);
      await destination.parent.create(recursive: true);
      final output = await part.open(
        mode: acceptedBytes > 0 ? FileMode.append : FileMode.write);
      final partial = <int>[];
      var received = acceptedBytes;
      try {
        await for (final incoming in response.timeout(const Duration(seconds: 45))) {
          if (isCancelled()) throw const R03InvalidEntityException('cancelled');
          if (incoming.isEmpty) continue;
          if (received + incoming.length > maxBytes ||
              (total != null && received + incoming.length > total)) {
            throw const R03InvalidEntityException('response exceeds expected length');
          }
          await output.writeFrom(incoming);
          received += incoming.length;
          var index = 0;
          while (index < incoming.length) {
            final remaining = r03ChunkBytes - partial.length;
            final end = min(incoming.length, index + remaining);
            partial.addAll(incoming.sublist(index, end));
            index = end;
            if (partial.length == r03ChunkBytes) {
              await output.flush();
              committed.add(sha256.convert(partial).toString());
              partial.clear();
              active = active.copyWith(blocks: List<String>.of(committed));
              await _save(journal, active);
            }
          }
          onProgress?.call(total == null ? null : (received * 100 / total).clamp(0, 100).toDouble(), received, total);
        }
        await output.flush();
      } finally {
        await output.close();
      }
      if (isCancelled()) throw const R03InvalidEntityException('cancelled');
      if (total != null && received != total) {
        throw const R03InvalidEntityException('incomplete response body');
      }
      // Unknown Content-Length is valid only after a clean stream EOF and
      // digest verification. A dropped connection is not a successful EOF.
      active = active.copyWith(stage: R03Stage.verifying, blocks: List<String>.of(committed));
      await _save(journal, active);
      final digest = await _sha256File(part);
      if (expectedSha256 != null && digest != expectedSha256) {
        throw const R03InvalidEntityException('trusted digest mismatch');
      }
      if (await part.length() != received) {
        throw const R03InvalidEntityException('file changed during verification');
      }
      // POSIX rename is atomic; no delete-before-replace of a usable cache.
      await part.rename(destination.path);
      active = active.copyWith(
        stage: R03Stage.ready, blocks: List<String>.of(committed),
        finalDigest: digest, completedBytes: received,
      );
      await _save(journal, active);
      onProgress?.call(null, null, null);
      return destination;
    } catch (error) {
      final status = isCancelled() ? R03Stage.cancelled :
          error is R03DownloadHttpException && r03CanRetryHttpStatus(error.statusCode)
              ? R03Stage.retrying : R03Stage.failed;
      try {
        await _save(journal, active.copyWith(stage: status,
          blocks: List<String>.of(committed)));
      } catch (_) { /* Preserve original failure. */ }
      rethrow;
    }
  }

  static bool _responseValidatorMatches(R03DownloadRecord journal, HttpClientResponse response) {
    final etag = r03StrongEtag(response.headers.value(HttpHeaders.etagHeader));
    if (journal.etag != null) return etag == journal.etag;
    if (journal.lastModified != null) {
      return response.headers.value(HttpHeaders.lastModifiedHeader) == journal.lastModified;
    }
    return false;
  }

  static int? _safeRetryAfter(String? header) {
    try { return r03RetryAfterSeconds(header, DateTime.now()); }
    catch (_) { return null; }
  }

  static Future<bool> _verifyBlocks(File file, List<String> blocks) async {
    if (await file.length() < blocks.length * r03ChunkBytes) return false;
    final raf = await file.open();
    try {
      for (final expected in blocks) {
        final bytes = await raf.read(r03ChunkBytes);
        if (bytes.length != r03ChunkBytes ||
            sha256.convert(bytes).toString() != expected) {
          return false;
        }
      }
      return true;
    } finally {
      await raf.close();
    }
  }

  static Future<void> _truncateTo(File file, int length) async {
    final raf = await file.open(mode: FileMode.append);
    try { await raf.truncate(length); }
    finally { await raf.close(); }
  }

  static Future<String> _sha256File(File file) async =>
      (await sha256.bind(file.openRead()).first).toString();

  static Future<void> _save(File file, R03DownloadRecord state) async {
    final tmp = File('${file.path}.tmp');
    if (await FileSystemEntity.type(tmp.path, followLinks: false) ==
        FileSystemEntityType.link) {
      throw const R03InvalidEntityException('journal symlink rejected');
    }
    await tmp.writeAsString(jsonEncode(state.toJson()), flush: true);
    await tmp.rename(file.path);
  }
}
