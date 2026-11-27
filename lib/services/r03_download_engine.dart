// R03: persisted, validator-bound, resumable downloads. No trusted remote
// attestation is inferred from a locally computed content hash.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:obtainium/services/r07_journal_guard.dart';

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

/// Thrown only after the exact partial file and durable paused receipt exist.
class R03PausedException implements Exception {
  const R03PausedException(this.jobId);
  final String jobId;
}

/// A persistent receipt contains no bearer tokens, URL query strings, or
/// authorization headers. The actual URL and credentials are re-resolved from
/// the tracked source on each operation, including after application restart.
/// Optional exact history owner; absent on legacy or non-library transfers.
class R03HistoryBinding {
  R03HistoryBinding(this.listingKey, this.packageId, this.channel,
      {this.releaseFingerprint}) {
    if (listingKey.isEmpty || listingKey.length > 1000 ||
        listingKey.contains(RegExp(r'[\x00-\x1f/\\]')) ||
        !RegExp(r'^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$').hasMatch(packageId) ||
        packageId.length > 255 || !RegExp(r'^[a-f0-9]{64}$').hasMatch(channel) ||
        (releaseFingerprint != null && !RegExp(r'^[a-f0-9]{64}$').hasMatch(releaseFingerprint!))) {
      throw const FormatException('Invalid R03 history owner');
    }
  }
  final String listingKey, packageId, channel;
  final String? releaseFingerprint;
  Map<String, String> toJson() => {'listingKey': listingKey, 'packageId': packageId, 'channel': channel,
    'releaseFingerprint': ?releaseFingerprint};
  static R03HistoryBinding? decode(Object? value) {
    if (value == null) return null;
    if (value is! Map || value.keys.any((key) => !const {'listingKey', 'packageId', 'channel', 'releaseFingerprint'}.contains(key)) ||
        value['listingKey'] is! String || value['packageId'] is! String || value['channel'] is! String ||
        (value.containsKey('releaseFingerprint') && value['releaseFingerprint'] is! String)) {
      throw const FormatException('Invalid R03 history binding');
    }
    return R03HistoryBinding(value['listingKey'] as String, value['packageId'] as String,
        value['channel'] as String, releaseFingerprint: value['releaseFingerprint'] as String?);
  }
  @override
  bool operator ==(Object other) => other is R03HistoryBinding &&
      other.listingKey == listingKey && other.packageId == packageId && other.channel == channel &&
      other.releaseFingerprint == releaseFingerprint;
  @override
  int get hashCode => Object.hash(listingKey, packageId, channel, releaseFingerprint);
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
    this.originObserved = false,
    this.cacheRootFingerprint,
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
  final bool originObserved;
  final String? cacheRootFingerprint;

  bool get explicitlyResumable => historyBinding?.releaseFingerprint != null &&
      cacheRootFingerprint != null && ifRange != null && totalBytes != null &&
      validatedBytes > 0 && validatedBytes < totalBytes! && finalDigest == null &&
      const {R03Stage.paused, R03Stage.failed, R03Stage.cancelled,
        R03Stage.retrying, R03Stage.downloading}.contains(stage);

  int get validatedBytes => blocks.length * r03ChunkBytes;
  String? get ifRange => etag ?? lastModified;

  Map<String, Object?> toJson() => {
    'schema': 'obtainx.r03.download.v1',
    if (historyBinding != null) 'historyBinding': historyBinding!.toJson(),
    'jobId': jobId,
    'sourceFingerprint': sourceFingerprint,
    'origin': origin,
    'finalOrigin': finalOrigin,
    if (originObserved) 'originObserved': true,
    if (cacheRootFingerprint != null) 'cacheRootFingerprint': cacheRootFingerprint,
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
    final cacheRoot = input['cacheRootFingerprint'];
    if (cacheRoot != null && (cacheRoot is! String || !RegExp(r'^[a-f0-9]{64}$').hasMatch(cacheRoot))) {
      throw const FormatException('Invalid R03 cache root identity');
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
      originObserved: input['originObserved'] == true,
      cacheRootFingerprint: cacheRoot as String?,
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
    historyBinding: historyBinding, originObserved: originObserved,
    cacheRootFingerprint: cacheRootFingerprint,
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

String r03FinalOrigin(HttpClientResponse response, Uri source, {Uri? resolved}) {
  // The HttpService's redirect policy still owns authorization forwarding.
  // A receipt records only the final origin, never a presigned URL/query.
  Uri current = resolved ?? source;
  if (resolved == null) {
    for (final redirect in response.redirects) {
      current = current.resolveUri(redirect.location);
    }
  }
  return '${current.scheme}://${current.host}${current.hasPort ? ':${current.port}' : ''}';
}

/// Real transfer state survives process termination in an atomic private
/// journal. A committed .part block has a SHA-256 hash in that journal; an
/// uncommitted trailing fragment is truncated on recovery.
class R03DownloadEngine {
  R03DownloadEngine({required this.journalDirectory, this.maxBytes = r03MaximumBytes,
      this.maxWallTime = const Duration(hours: 2), this.ensureCapacity}) {
    if (maxBytes <= 0 || maxBytes > r03MaximumBytes ||
        maxWallTime <= Duration.zero || maxWallTime > const Duration(hours: 2)) {
      throw const R03InvalidEntityException('invalid transfer bound');
    }
  }
  final Directory journalDirectory;
  final int maxBytes;
  final Duration maxWallTime;
  final Future<void> Function(String, int)? ensureCapacity;
  static final Map<String, Future<({File file, R03DownloadRecord receipt})>> _active = {};
  // A caller with different trusted-byte requirements must never inherit a
  // transfer owned by another caller, even when URL and destination match.
  static final Map<String, String?> _activeExpectedDigest = {};
  static final Map<String, int> _activeMaxBytes = {};
  static final Map<String, R03HistoryBinding?> _activeHistory = {};
  static final Map<String, bool> _activeOriginObserved = {};

  static String jobKey(Uri url, File destination, Map<String, String> headers,
      {R03HistoryBinding? historyBinding}) {
    final sorted = headers.entries.toList()
      ..sort((a, b) => a.key.toLowerCase().compareTo(b.key.toLowerCase()));
    // Including a digest of the request headers prevents cross-account cache
    // aliasing without ever persisting the secrets themselves.
    return sha256.convert(utf8.encode(jsonEncode([
      url.toString(), destination.absolute.path,
      for (final h in sorted) [h.key.toLowerCase(), h.value],
      if (historyBinding?.releaseFingerprint != null) historyBinding!.toJson(),
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
    bool Function()? isPauseRequested,
    void Function(bool)? onPauseAvailable,
    R03HistoryBinding? historyBinding,
    R03DownloadRecord? resumeRecord,
    Uri? Function(HttpClientResponse)? resolvedUri,
    void Function(R03DownloadRecord)? onVerified,
  }) {
    if (expectedSha256 != null && !RegExp(r'^[a-f0-9]{64}$').hasMatch(expectedSha256)) {
      unawaited(firstResponse.listen((_) {}).cancel());
      return Future<File>.error(const R03InvalidEntityException('invalid expected digest'));
    }
    final key = jobKey(source, destination, headers, historyBinding: historyBinding);
    final existing = _active[key];
    if (existing != null) {
      unawaited(firstResponse.listen((_) {}).cancel());
      if (resumeRecord != null || _activeExpectedDigest[key] != expectedSha256 || _activeMaxBytes[key] != maxBytes ||
          _activeHistory[key] != historyBinding || _activeOriginObserved[key] != (resolvedUri != null)) {
        return Future<File>.error(const R03InvalidEntityException(
          'conflicting trusted digest for active transfer'));
      }
      return existing.then((result) { onVerified?.call(result.receipt); return result.file; });
    }
    Future<({File file, R03DownloadRecord receipt})> guarded() async {
      var entered = false;
      try {
        return await withR07JournalGuard(journalDirectory,
          'destination:${destination.absolute.path}', () {
          entered = true;
          return _run(source: source, destination: destination, headers: headers,
            firstResponse: firstResponse, fetch: fetch,
            isCancelled: isCancelled, onProgress: onProgress,
            isPauseRequested: isPauseRequested, onPauseAvailable: onPauseAvailable,
            useExisting: useExisting, expectedSha256: expectedSha256,
            jobId: key, historyBinding: historyBinding, resolvedUri: resolvedUri,
            resumeRecord: resumeRecord);
        });
      } catch (_) {
        if (!entered) await firstResponse.listen((_) {}).cancel();
        rethrow;
      }
    }
    final next = guarded();
    _active[key] = next;
    _activeExpectedDigest[key] = expectedSha256;
    _activeMaxBytes[key] = maxBytes;
    _activeHistory[key] = historyBinding;
    _activeOriginObserved[key] = resolvedUri != null;
    void clearActive() {
      if (identical(_active[key], next)) {
        _active.remove(key);
        _activeExpectedDigest.remove(key);
        _activeMaxBytes.remove(key);
        _activeHistory.remove(key);
        _activeOriginObserved.remove(key);
      }
    }
    // Consume completion and failure without returning the failed Future from
    // cleanup (a returned Future can re-emit its error into the cleanup chain).
    unawaited(next.then<void>((_) { clearActive(); },
      onError: (Object error, StackTrace trace) { clearActive(); }));
    return next.then((result) { onVerified?.call(result.receipt); return result.file; });
  }

  Future<({File file, R03DownloadRecord receipt})> _run({
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
    bool Function()? isPauseRequested,
    void Function(bool)? onPauseAvailable,
    R03HistoryBinding? historyBinding,
    R03DownloadRecord? resumeRecord,
    Uri? Function(HttpClientResponse)? resolvedUri,
  }) async {
    final journal = File('${journalDirectory.path}/$jobId.json');
    final part = File('${destination.path}.part');
    final origin = '${source.scheme}://${source.host}${source.hasPort ? ':${source.port}' : ''}';
    final R03DownloadRecord initial = R03DownloadRecord(
      jobId: jobId, sourceFingerprint: jobId, origin: origin,
      finalOrigin: origin, fileName: destination.uri.pathSegments.last,
      stage: R03Stage.queued, blocks: const [], historyBinding: historyBinding,
      originObserved: resolvedUri != null,
      cacheRootFingerprint: r07JournalFingerprint(destination.parent.absolute.path),
    );
    R03DownloadRecord? previous;
    try {
      final journalType = await FileSystemEntity.type(journalDirectory.path, followLinks: false);
      if (journalType != FileSystemEntityType.notFound && journalType != FileSystemEntityType.directory) {
        throw const R03InvalidEntityException('Unsafe transfer journal directory');
      }
      await journalDirectory.create(recursive: true);
      for (final path in [destination.path, part.path, journal.path]) {
        final type = await FileSystemEntity.type(path, followLinks: false);
        if (type != FileSystemEntityType.notFound && type != FileSystemEntityType.file) {
          throw const R03InvalidEntityException('Unsafe transfer file path');
        }
      }
      if (await part.exists()) {
        await _refuseForeignPartial(initial);
      }
      if (await journal.exists()) {
        try {
          final candidate = await _readCheckpoint(journal);
          if (candidate.jobId == jobId && candidate.sourceFingerprint == jobId &&
              candidate.fileName == initial.fileName && candidate.origin == origin &&
              (resolvedUri == null || candidate.originObserved) &&
              (candidate.totalBytes ?? 0) <= maxBytes &&
              (candidate.completedBytes ?? 0) <= maxBytes && candidate.validatedBytes <= maxBytes) {
            previous = candidate;
          } else if (historyBinding != null && await part.exists()) {
            throw const R03InvalidEntityException('Existing partial checkpoint identity differs');
          }
        } catch (_) {
          // Unknown owned partial bytes must be preserved, not reclassified as
          // an empty checkpoint. Legacy non-library orphans remain untrusted.
          if (historyBinding != null && await part.exists()) rethrow;
        }
      }
      if (previous?.historyBinding != null && previous?.historyBinding != historyBinding) {
        throw const R03InvalidEntityException('conflicting historical owner for transfer');
      }
      if (!useExisting && previous?.explicitlyResumable == true && await part.exists()) {
        throw const R03InvalidEntityException('A recoverable transfer owns these bytes; resume it instead');
      }
      if (!useExisting) previous = null;
      if (resumeRecord != null && (!useExisting || previous == null ||
          !resumeRecord.explicitlyResumable || resumeRecord.jobId != jobId ||
          previous.cacheRootFingerprint != initial.cacheRootFingerprint ||
          jsonEncode(previous.toJson()) != jsonEncode(resumeRecord.toJson()))) {
        throw const R03InvalidEntityException('Exact paused transfer no longer available');
      }
    } catch (_) {
      try { await firstResponse.listen((_) {}).cancel(); } catch (_) { /* primary refusal */ }
      rethrow;
    }
    final elapsed = Stopwatch()..start();
    var response = firstResponse;
    final effectiveInitial = previous != null && previous.historyBinding == null
        ? R03DownloadRecord(jobId: initial.jobId, sourceFingerprint: initial.sourceFingerprint,
          origin: initial.origin, finalOrigin: initial.finalOrigin, fileName: initial.fileName,
          stage: R03Stage.queued, blocks: const [], originObserved: initial.originObserved) : initial;
    var active = effectiveInitial;
    var committed = <String>[];
    var acceptedBytes = 0;
    int? total;
    String? etag;
    String? lastModified;
    String responseOrigin(HttpClientResponse value) {
      final resolved = resolvedUri?.call(value);
      if (resolvedUri != null && resolved == null) {
        throw const R03InvalidEntityException('transport did not establish final origin');
      }
      return r03FinalOrigin(value, source, resolved: resolved);
    }
    var currentOrigin = responseOrigin(firstResponse);
    bool eligibleForResume = false;
    var startedWrite = false;

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
          return (file: destination, receipt: previous);
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
      if (resumeRecord != null && !eligibleForResume) {
        await response.listen((_) {}).cancel();
        throw const R03InvalidEntityException('Resume requires the same origin, validator and verified blocks');
      }
      if (eligibleForResume) {
        final checkpoint = previous!;
        committed = List<String>.of(checkpoint.blocks);
        acceptedBytes = checkpoint.validatedBytes;
        await response.listen((_) {}).cancel();
        final resumableHeaders = Map<String, String>.from(headers)
          ..removeWhere((key, _) => key.toLowerCase() == 'range' ||
              key.toLowerCase() == 'if-range')
          ..['range'] = 'bytes=$acceptedBytes-'
          ..['if-range'] = checkpoint.ifRange!;
        response = await fetch(resumableHeaders);
        currentOrigin = responseOrigin(response);
        final range = r03ContentRange(response.headers.value(HttpHeaders.contentRangeHeader));
        final correct206 = response.statusCode == HttpStatus.partialContent &&
            range != null && range.start == acceptedBytes &&
            range.total == checkpoint.totalBytes &&
            range.end == range.total - 1 &&
            response.contentLength == range.end - range.start + 1 &&
            response.compressionState != HttpClientResponseCompressionState.decompressed &&
            currentOrigin == checkpoint.finalOrigin &&
            _responseValidatorMatches(checkpoint, response);
        if (!correct206) {
          if (resumeRecord != null) {
            await response.listen((_) {}).cancel();
            throw const R03InvalidEntityException('Explicit resume requires an exact validated range');
          }
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
          currentOrigin = responseOrigin(response);
        } else {
          // Truncate only after the exact 206 is established. A refused
          // explicit resume must preserve the previous checkpoint and bytes.
          await _truncateTo(part, acceptedBytes);
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
      await destination.parent.create(recursive: true);
      await ensureCapacity?.call(destination.parent.path,
        total == null ? min(maxBytes, 8 * r03ChunkBytes) : total - acceptedBytes);
      await _save(journal, active);
      startedWrite = true;
      final output = await part.open(
        mode: acceptedBytes > 0 ? FileMode.append : FileMode.write);
      final partial = <int>[];
      var received = acceptedBytes;
      var capacityCheckedAt = acceptedBytes;
      try {
        onPauseAvailable?.call(active.explicitlyResumable);
        await for (final incoming in response.timeout(const Duration(seconds: 45))) {
          if (isCancelled()) throw const R03InvalidEntityException('cancelled');
          if (isPauseRequested?.call() == true) {
            throw const R03InvalidEntityException('pause requested');
          }
          if (elapsed.elapsed >= maxWallTime) throw TimeoutException('Artifact transfer deadline exceeded');
          if (incoming.isEmpty) continue;
          if (received + incoming.length > maxBytes ||
              (total != null && received + incoming.length > total)) {
            throw const R03InvalidEntityException('response exceeds expected length');
          }
          if (received - capacityCheckedAt + incoming.length >= 8 * r03ChunkBytes) {
            await ensureCapacity?.call(destination.parent.path,
              min((total ?? maxBytes) - received, max(incoming.length, 8 * r03ChunkBytes)));
            capacityCheckedAt = received;
          }
          // Disable new pause requests before committing the final full block.
          // A previously accepted pause is serviced against the last checkpoint.
          if (total != null && received + incoming.length >= total) {
            onPauseAvailable?.call(false);
          }
          if (isPauseRequested?.call() == true) {
            throw const R03InvalidEntityException('pause requested');
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
              if (isPauseRequested?.call() == true) {
                throw const R03InvalidEntityException('pause requested');
              }
              await output.flush();
              committed.add(sha256.convert(partial).toString());
              partial.clear();
              active = active.copyWith(blocks: List<String>.of(committed));
              await _save(journal, active);
              onPauseAvailable?.call(active.explicitlyResumable && (total == null || received < total));
              if (isPauseRequested?.call() == true) {
                throw const R03InvalidEntityException('pause requested');
              }
            }
          }
          onProgress?.call(total == null ? null : (received * 100 / total).clamp(0, 100).toDouble(), received, total);
        }
        await output.flush();
      } finally {
        onPauseAvailable?.call(false);
        await output.close();
      }
      if (isPauseRequested?.call() == true) {
        throw const R03InvalidEntityException('pause requested');
      }
      if (isCancelled()) throw const R03InvalidEntityException('cancelled');
      if (total != null && received != total) {
        throw const R03InvalidEntityException('incomplete response body');
      }
      if (elapsed.elapsed >= maxWallTime) throw TimeoutException('Artifact transfer deadline exceeded');
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
      return (file: destination, receipt: active);
    } catch (error) {
      onPauseAvailable?.call(false);
      if (isPauseRequested?.call() == true && startedWrite) {
        // Use the exact last committed inventory, not a trailing fragment or
        // the in-memory list if the last journal update did not complete.
        final saved = await _readCheckpoint(journal);
        if (!saved.explicitlyResumable || saved.jobId != jobId ||
            saved.stage != R03Stage.downloading || !await _verifyBlocks(part, saved.blocks)) {
          throw const R03InvalidEntityException('pause checkpoint could not be verified');
        }
        await _truncateTo(part, saved.validatedBytes);
        await _save(journal, saved.copyWith(stage: R03Stage.paused));
        throw R03PausedException(saved.jobId);
      }
      final status = isCancelled() ? R03Stage.cancelled :
          error is R03DownloadHttpException && r03CanRetryHttpStatus(error.statusCode)
              ? R03Stage.retrying : R03Stage.failed;
      try {
        if (startedWrite || (resumeRecord == null && previous?.explicitlyResumable != true)) {
          await _save(journal, active.copyWith(stage: status,
            blocks: List<String>.of(committed)));
        }
      } catch (_) { /* Preserve original failure. */ }
      rethrow;
    }
  }

  static Future<R03DownloadRecord> _readCheckpoint(File file) async {
    if (await FileSystemEntity.type(file.path, followLinks: false) != FileSystemEntityType.file ||
        await file.length() > 320 * 1024) {
      throw const FormatException('Unsafe transfer checkpoint');
    }
    final bytes = await file.readAsBytes();
    if (bytes.length > 320 * 1024) throw const FormatException('Oversize transfer checkpoint');
    final value = jsonDecode(utf8.decode(bytes));
    if (value is! Map<String, dynamic>) throw const FormatException('Invalid transfer checkpoint');
    final record = R03DownloadRecord.fromJson(value);
    if (file.uri.pathSegments.last != '${record.jobId}.json' || record.sourceFingerprint != record.jobId) {
      throw const FormatException('Transfer checkpoint identity mismatch');
    }
    return record;
  }

  Future<void> _refuseForeignPartial(R03DownloadRecord expected) async {
    await for (final entry in journalDirectory.list(followLinks: false)) {
      final name = entry.uri.pathSegments.last;
      if (name == '${expected.jobId}.json') { continue; }
      if (RegExp(r'^[a-f0-9]{64}\.json\.tmp$').hasMatch(name) && entry is File) { continue; }
      if (entry is! File || !RegExp(r'^[a-f0-9]{64}\.json$').hasMatch(name)) {
        throw const R03InvalidEntityException('Unknown partial transfer ownership');
      }
      final record = await _readCheckpoint(entry);
      if (record.fileName == expected.fileName &&
          (record.cacheRootFingerprint == null || record.cacheRootFingerprint == expected.cacheRootFingerprint)) {
        throw const R03InvalidEntityException('Another transfer identity owns this partial file');
      }
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
