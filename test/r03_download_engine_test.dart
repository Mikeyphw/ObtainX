import 'dart:io';
import 'dart:math';
import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/services/r03_download_engine.dart';

// Flutter's test binding is already initialized by the test runner.
// Avoid instantiating a second binding. An isolated HttpOverrides zone creates
// the one real HttpClient owned by these loopback-only HTTP test fixtures.
// The production HTTP implementation and Flutter's global test mock are unchanged.
class _R03RealLoopbackHttpOverrides extends HttpOverrides {}

void main() {
  group('R03 source identity and response policy', () {
    test('strict 206 Content-Range including invalid and overflow', () {
      expect(r03ContentRange('bytes 10-19/20'), (start: 10, end: 19, total: 20));
      expect(r03ContentRange('bytes 10-20/20'), isNull);
      expect(r03ContentRange('bytes */20'), isNull);
      expect(r03ContentRange('bytes 5-4/20'), isNull);
      expect(r03ContentRange('bytes 0-9/*'), isNull);
      expect(r03ContentRange('bytes 0-999/10'), isNull);
      expect(r03ContentRange('bytes 0-9/999999999999999999999999'), isNull);
    });
    test('strong ETag required for resume', () {
      expect(r03StrongEtag('"release-a"'), '"release-a"');
      expect(r03StrongEtag('W/"release-a"'), isNull);
      expect(r03StrongEtag('"bad\r\nvalue"'), isNull);
    });
    test('HTTP retry policy does not retry auth/corruption', () {
      for (final status in [408, 429, 500, 502, 503, 599]) {
        expect(r03CanRetryHttpStatus(status), isTrue);
      }
      for (final status in [200, 206, 302, 400, 401, 403, 404, 410, 416]) {
        expect(r03CanRetryHttpStatus(status), isFalse);
      }
      expect(r03RetryAfterSeconds('4', DateTime.utc(2026)), 4);
      expect(r03RetryAfterSeconds('9999', DateTime.utc(2026)), 120);
    });
    test('journal schema refuses forged progress and unknown state', () {
      const receipt = R03DownloadRecord(
        jobId: 'a', sourceFingerprint: 'a', origin: 'https://example.org',
        finalOrigin: 'https://example.org', fileName: 'a.apk',
        stage: R03Stage.downloading, blocks: [],
      );
      final m = receipt.toJson();
      expect(R03DownloadRecord.fromJson(Map<String, dynamic>.from(m)).validatedBytes, 0);
      expect(() => R03DownloadRecord.fromJson(Map<String, dynamic>.from(m)
        ..['validatedBytes'] = 1), throwsFormatException);
      expect(() => R03DownloadRecord.fromJson(Map<String, dynamic>.from(m)
        ..['stage'] = 'pretend-success'), throwsFormatException);
      expect(() => R03DownloadRecord.fromJson(Map<String, dynamic>.from(m)
        ..['blocks'] = ['bad']), throwsFormatException);
    });
    test('job identity separates credentials without writing them', () {
      final url = Uri.parse('https://example.org/update.apk?temporary=secret');
      final f = File('/tmp/test.apk');
      expect(R03DownloadEngine.jobKey(url, f, {'Authorization': 'a'}),
        isNot(R03DownloadEngine.jobKey(url, f, {'Authorization': 'b'})));
      expect(R03DownloadEngine.jobKey(url, f, {}),
        matches(RegExp(r'^[a-f0-9]{64}$')));
    });
  });

  group('R03 deterministic mock HTTP transfer lifecycle', () {
    late Directory sandbox;
    late HttpServer server;
    late HttpClient client;
    late Uint8List payload;
    late String etag;
    late bool supportsRange;
    late bool ignoresRange;
    late bool invalidRange;
    late bool force416;
    late bool redirectInitial;
    late int? rejection;
    late bool omitLength;
    late List<String> ranges;
    late List<String> ifRanges;
    late int requests;

    setUp(() async {
      sandbox = await Directory.systemTemp.createTemp('obtainx-r03-test-');
      client = HttpOverrides.runWithHttpOverrides(
        () => HttpClient(),
        _R03RealLoopbackHttpOverrides(),
      );
      payload = Uint8List.fromList(List<int>.generate(2 * 1024 * 1024 + 97, (i) => i % 251));
      etag = '"r03-v1"';
      supportsRange = true;
      ignoresRange = false;
      invalidRange = false;
      force416 = false;
      redirectInitial = false;
      rejection = null;
      omitLength = false;
      requests = 0;
      ranges = [];
      ifRanges = [];
      server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      server.listen((request) async {
        requests++;
        final range = request.headers.value('range');
        if (range != null) ranges.add(range);
        final ifRange = request.headers.value('if-range');
        if (ifRange != null) ifRanges.add(ifRange);
        final reply = request.response;
        if (request.uri.path == '/redirect') {
          await reply.redirect(Uri.parse('http://127.0.0.1:${server.port}/asset.apk'));
          return;
        }
        reply.headers.set('etag', etag);
        reply.headers.set('accept-ranges', 'bytes');
        if (rejection != null) {
          reply.statusCode = rejection!;
          if (rejection == 429) reply.headers.set('retry-after', '2');
          await reply.close();
          return;
        }
        if (range != null && force416) {
          reply.statusCode = 416;
          await reply.close();
          return;
        }
        int offset = 0;
        if (range != null && supportsRange && !ignoresRange) {
          final match = RegExp(r'^bytes=(\d+)-$').firstMatch(range);
          if (match == null) {
            reply.statusCode = 416;
            await reply.close();
            return;
          }
          offset = int.parse(match.group(1)!);
          if (offset >= payload.length) {
            reply.statusCode = 416;
            await reply.close();
            return;
          }
          reply.statusCode = 206;
          reply.headers.set('content-range', invalidRange
              ? 'bytes 0-${payload.length - 1}/${payload.length}'
              : 'bytes $offset-${payload.length - 1}/${payload.length}');
        }
        if (!omitLength) reply.contentLength = payload.length - offset;
        try {
          for (var index = offset; index < payload.length; index += 65536) {
            final end = min(index + 65536, payload.length);
            reply.add(payload.sublist(index, end));
            await reply.flush();
          }
          await reply.close();
        } on SocketException {
          // Cancellation deliberately closes a live transfer. A server-side
          // broken pipe is expected; it is not an extra failed test.
        } on HttpException {
          // HttpServerResponse may also report a disconnected HTTP client.
        }
      });
    });

    tearDown(() async {
      client.close(force: true);
      await server.close(force: true);
      await sandbox.delete(recursive: true);
    });

    Uri source() => Uri.parse('http://127.0.0.1:${server.port}/${redirectInitial ? 'redirect' : 'asset.apk'}');
    File target() => File('${sandbox.path}/downloads/app.apk');
    R03DownloadEngine engine() => R03DownloadEngine(
      journalDirectory: Directory('${sandbox.path}/private-receipts'));
    Future<HttpClientResponse> fetch(Map<String, String> headers) async {
      final req = await client.getUrl(source());
      for (final entry in headers.entries) {
        req.headers.set(entry.key, entry.value);
      }
      return req.close();
    }
    Future<File> transfer({bool Function()? cancelled,
      void Function(double?, int?, int?)? progress,
      bool useExisting = true, String? expectedSha256}) async {
      final first = await fetch(const {});
      return engine().download(
        source: source(), destination: target(),
        headers: const {}, firstResponse: first, fetch: fetch,
        isCancelled: cancelled ?? () => false,
        onProgress: progress, useExisting: useExisting,
        expectedSha256: expectedSha256,
      );
    }

    Future<int> validatedResumeOffset() async {
      final jobId = R03DownloadEngine.jobKey(source(), target(), const {});
      final journal = File('${sandbox.path}/private-receipts/$jobId.json');
      final record = R03DownloadRecord.fromJson(
        Map<String, dynamic>.from(jsonDecode(await journal.readAsString())));
      expect(record.stage, R03Stage.cancelled);
      expect(record.validatedBytes, greaterThanOrEqualTo(r03ChunkBytes));
      expect(record.validatedBytes % r03ChunkBytes, 0);
      expect(record.validatedBytes, lessThan(payload.length));
      expect(await File('${target().path}.part').length(),
        greaterThanOrEqualTo(record.validatedBytes));
      return record.validatedBytes;
    }

    test('200 with known length publishes exact verified bytes and receipt', () async {
      final output = await transfer();
      expect(await output.readAsBytes(), payload);
      expect(requests, 1);
      final receipts = Directory('${sandbox.path}/private-receipts').listSync();
      expect(receipts.length, 1);
      final json = jsonDecode(await File(receipts.single.path).readAsString());
      expect(json['stage'], 'ready');
      expect(json['completedBytes'], payload.length);
      expect(json['finalDigest'], sha256.convert(payload).toString());
      expect(json['sourceFingerprint'], matches(RegExp(r'^[a-f0-9]{64}$')));
      expect(jsonEncode(json), isNot(contains('asset.apk?temporary=')));
    });
    test('cached output must be locally hash-verified, not length-trusted', () async {
      await transfer();
      final bytes = await target().readAsBytes();
      bytes[0] ^= 0xff;
      await target().writeAsBytes(bytes);
      final output = await transfer();
      expect(await output.readAsBytes(), payload);
    });
    test('no content-length still verifies clean stream EOF', () async {
      omitLength = true;
      final output = await transfer();
      expect(await output.readAsBytes(), payload);
    });
    test('401/403/410/416/429/5xx classified and never published', () async {
      for (final status in [401, 403, 410, 416, 429, 503]) {
        rejection = status;
        await expectLater(transfer(useExisting: false),
          throwsA(isA<R03DownloadHttpException>().having(
            (e) => e.statusCode, 'statusCode', status)));
        expect(await target().exists(), isFalse);
      }
    });
    test('after cancellation, strong validator resumes with Range and If-Range', () async {
      var stop = false;
      await expectLater(transfer(cancelled: () => stop,
        progress: (_, received, _) { if ((received ?? 0) >= r03ChunkBytes) stop = true; }),
        throwsA(isA<R03InvalidEntityException>()));
      expect(await target().exists(), isFalse);
      expect(await File('${target().path}.part').exists(), isTrue);
      final resumeOffset = await validatedResumeOffset();
      final file = await transfer();
      expect(await file.readAsBytes(), payload);
      expect(ranges, contains('bytes=$resumeOffset-'));
      expect(ifRanges, contains('"r03-v1"'));
    });
    test('changed ETag restarts safely; never appends old bytes', () async {
      var stop = false;
      await expectLater(transfer(cancelled: () => stop,
        progress: (_, received, _) { if ((received ?? 0) >= r03ChunkBytes) stop = true; }),
        throwsA(isA<R03InvalidEntityException>()));
      await validatedResumeOffset();
      etag = '"r03-v2"';
      final output = await transfer();
      expect(await output.readAsBytes(), payload);
      expect(ranges, isEmpty);
    });
    test('ignored Range response starts over without duplicate bytes', () async {
      var stop = false;
      await expectLater(transfer(cancelled: () => stop,
        progress: (_, received, _) { if ((received ?? 0) >= r03ChunkBytes) stop = true; }),
        throwsA(isA<R03InvalidEntityException>()));
      final resumeOffset = await validatedResumeOffset();
      ignoresRange = true;
      final output = await transfer();
      expect(await output.length(), payload.length);
      expect(await output.readAsBytes(), payload);
      expect(ranges, contains('bytes=$resumeOffset-'));
    });
    test('invalid Content-Range starts over rather than combining entities', () async {
      var stop = false;
      await expectLater(transfer(cancelled: () => stop,
        progress: (_, received, _) { if ((received ?? 0) >= r03ChunkBytes) stop = true; }),
        throwsA(isA<R03InvalidEntityException>()));
      await validatedResumeOffset();
      invalidRange = true;
      final output = await transfer();
      expect(await output.readAsBytes(), payload);
    });
    test('416 on resumed range restarts cleanly with a full GET', () async {
      var stop = false;
      await expectLater(transfer(cancelled: () => stop,
        progress: (_, received, _) { if ((received ?? 0) >= r03ChunkBytes) stop = true; }),
        throwsA(isA<R03InvalidEntityException>()));
      final resumeOffset = await validatedResumeOffset();
      force416 = true;
      final output = await transfer();
      expect(await output.readAsBytes(), payload);
      expect(ranges, contains('bytes=$resumeOffset-'));
    });
    test('302 redirect completes with final origin evidence', () async {
      redirectInitial = true;
      final output = await transfer();
      expect(await output.readAsBytes(), payload);
      expect(requests, 2);
    });
    test('expected digest mismatch never publishes a completed file', () async {
      await expectLater(transfer(expectedSha256: List<String>.filled(64, '0').join()),
        throwsA(isA<R03InvalidEntityException>()));
      expect(await target().exists(), isFalse);
    });
    test('two clients for same job coalesce into one owned transfer', () async {
      final first = await fetch(const {});
      final second = await fetch(const {});
      final a = engine().download(source: source(), destination: target(),
        headers: const {}, firstResponse: first, fetch: fetch,
        isCancelled: () => false, onProgress: null);
      final b = engine().download(source: source(), destination: target(),
        headers: const {}, firstResponse: second, fetch: fetch,
        isCancelled: () => false, onProgress: null);
      expect(await a, await b);
      expect(await target().readAsBytes(), payload);
    });

    test('conflicting concurrent trusted digests never share a transfer', () async {
      final first = await fetch(const {});
      final second = await fetch(const {});
      final validDigest = sha256.convert(payload).toString();
      final trusted = engine().download(
        source: source(), destination: target(), headers: const {},
        firstResponse: first, fetch: fetch, isCancelled: () => false,
        onProgress: null, expectedSha256: validDigest);
      final conflicting = engine().download(
        source: source(), destination: target(), headers: const {},
        firstResponse: second, fetch: fetch, isCancelled: () => false,
        onProgress: null, expectedSha256: List<String>.filled(64, '0').join());
      await expectLater(conflicting, throwsA(isA<R03InvalidEntityException>()
        .having((e) => e.reason, 'reason', contains('conflicting trusted digest'))));
      expect(await (await trusted).readAsBytes(), payload);
    });

    test('unverified in-flight transfer cannot satisfy a trusted caller', () async {
      final first = await fetch(const {});
      final second = await fetch(const {});
      final validDigest = sha256.convert(payload).toString();
      final unverified = engine().download(
        source: source(), destination: target(), headers: const {},
        firstResponse: first, fetch: fetch, isCancelled: () => false,
        onProgress: null);
      final trusted = engine().download(
        source: source(), destination: target(), headers: const {},
        firstResponse: second, fetch: fetch, isCancelled: () => false,
        onProgress: null, expectedSha256: validDigest);
      await expectLater(trusted, throwsA(isA<R03InvalidEntityException>()));
      expect(await (await unverified).readAsBytes(), payload);
      // A later trusted request independently verifies the completed digest;
      // it never borrows a transfer started without trusted bytes.
      expect(await (await transfer(expectedSha256: validDigest)).readAsBytes(),
        payload);
    });
  });
}
