/// APKMirror request ownership shared by foreground and background engines.
/// No alternate identities, bypass, automatic retries, or network fallback
/// when private coordination state cannot be obtained.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:obtainium/services/r07_journal_guard.dart';
import 'package:path_provider/path_provider.dart';

class ApkMirrorRequestDeferred implements Exception {
  const ApkMirrorRequestDeferred(this.message);
  final String message;
  @override
  String toString() => message;
}

class ApkMirrorRequestBudget {
  ApkMirrorRequestBudget({
    this.spacing = const Duration(seconds: 2),
    this.maxQueued = 32,
    DateTime Function()? clock,
    Future<void> Function(Duration)? wait,
    this._privateRoot,
  }) : _clock = clock ?? DateTime.now,
       _wait = wait ?? ((duration) => Future<void>.delayed(duration));

  static final shared = ApkMirrorRequestBudget(
    privateRoot: getApplicationSupportDirectory,
  );
  // The transport requires this lease as well as a verified public HTTPS
  // request; generic streaming/redirect paths cannot bypass ownership.
  static final _leaseKey = Object();
  static bool get ownsRequest => Zone.current[_leaseKey] == true;
  final Duration spacing;
  final int maxQueued;
  final DateTime Function() _clock;
  final Future<void> Function(Duration) _wait;
  final Future<Directory> Function()? _privateRoot;
  Future<void> _tail = Future<void>.value();
  DateTime? _nextStart;
  DateTime? _blockedUntil;
  int _queued = 0;

  static bool appliesTo(Uri uri) =>
      uri.scheme == 'https' && uri.port == 443 && uri.userInfo.isEmpty &&
      const {'apkmirror.com', 'www.apkmirror.com'}.contains(uri.host);

  static bool isMirrorHost(Uri uri) =>
      const {'apkmirror.com', 'www.apkmirror.com'}.contains(uri.host);

  Future<void> _readState(File file) async {
    final type = await FileSystemEntity.type(file.path, followLinks: false);
    if (type == FileSystemEntityType.notFound) {
      _nextStart = null;
      _blockedUntil = null;
      return;
    }
    if (type != FileSystemEntityType.file || await file.length() > 1024) {
      throw const FormatException('Unsafe APKMirror budget state');
    }
    final value = jsonDecode(await file.readAsString());
    if (value is! Map || value['schema'] != 1) {
      throw const FormatException('Invalid APKMirror budget state');
    }
    DateTime? readTime(String key) {
      final raw = value[key];
      if (raw == null) return null;
      if (raw is! String || DateTime.tryParse(raw) == null) {
        throw const FormatException('Invalid APKMirror budget timestamp');
      }
      return DateTime.parse(raw).toUtc();
    }
    _nextStart = readTime('nextStart');
    _blockedUntil = readTime('blockedUntil');
  }

  Future<void> _writeState(File file) async {
    final temporary = File('${file.path}.tmp');
    final type = await FileSystemEntity.type(temporary.path, followLinks: false);
    if (type != FileSystemEntityType.notFound && type != FileSystemEntityType.file) {
      throw const FormatException('Unsafe APKMirror budget temporary file');
    }
    await temporary.writeAsString(jsonEncode({
      'schema': 1,
      'nextStart': _nextStart?.toUtc().toIso8601String(),
      'blockedUntil': _blockedUntil?.toUtc().toIso8601String(),
    }), flush: true);
    await temporary.rename(file.path);
  }

  Future<http.Response> _perform(Future<http.Response> Function() load,
      {File? state}) async {
    if (state != null) await _readState(state);
    final blocked = _blockedUntil;
    if (blocked != null && blocked.isAfter(_clock())) {
      throw const ApkMirrorRequestDeferred(
        'APKMirror is rate-limited or unavailable; wait before checking again.',
      );
    }
    final next = _nextStart;
    if (next != null && next.isAfter(_clock())) {
      final remaining = next.difference(_clock());
      if (remaining > spacing) {
        throw const ApkMirrorRequestDeferred('APKMirror budget clock changed; retry later.');
      }
      await _wait(remaining);
    }
    _nextStart = _clock().add(spacing);
    // Persist the reservation before issuing network traffic, including when
    // the process dies or a connection fails. No request on storage failure.
    if (state != null) {
      // A dead owner or failed response-state write must not erase a possible
      // server cooldown. A normal successful response clears this reservation.
      _blockedUntil = _clock().add(const Duration(minutes: 5));
      await _writeState(state);
    }
    final response = await runZoned(load, zoneValues: {_leaseKey: true});
    _blockedUntil = null;
    if (const {403, 429, 503}.contains(response.statusCode)) {
      final now = _clock();
      var until = now.add(Duration(seconds: response.statusCode == 403 ? 300 : 60));
      final retry = response.headers['retry-after'];
      if (retry != null) {
        final seconds = int.tryParse(retry);
        DateTime? requested;
        if (seconds != null && seconds >= 0) {
          requested = now.add(Duration(seconds: seconds.clamp(0, 31536000).toInt()));
        } else {
          try {
            requested = HttpDate.parse(retry);
          } on FormatException {
            // Keep conservative default if the server's header is invalid.
          } on HttpException {
            // Same fallback for malformed HTTP dates.
          }
        }
        if (requested != null && requested.isAfter(until)) {
          until = requested;
        }
      }
      _blockedUntil = until;
    }
    if (state != null) await _writeState(state);
    return response;
  }

  Future<http.Response> _coordinated(Future<http.Response> Function() load) async {
    final root = _privateRoot;
    if (root == null) return _perform(load);
    final directory = Directory('${(await root()).path}/apkmirror-budget-v1');
    final type = await FileSystemEntity.type(directory.path, followLinks: false);
    if (type != FileSystemEntityType.notFound && type != FileSystemEntityType.directory) {
      throw const FormatException('Unsafe APKMirror budget directory');
    }
    await directory.create(recursive: true);
    try {
      return await withR07JournalGuard(directory, 'apkmirror.com', () async {
        if (await FileSystemEntity.type(directory.path, followLinks: false) !=
            FileSystemEntityType.directory) {
          throw const FormatException('Unsafe APKMirror budget directory');
        }
        return _perform(load, state: File('${directory.path}/state.json'));
      });
    } on R07JournalBusy {
      throw const ApkMirrorRequestDeferred('APKMirror request ownership is busy; retry later.');
    }
  }

  Future<http.Response> request(Future<http.Response> Function() load) async {
    if (_queued >= maxQueued) {
      throw const ApkMirrorRequestDeferred(
        'APKMirror request queue is full; retry later, not immediately.',
      );
    }
    _queued++;
    final previous = _tail;
    final done = Completer<void>();
    _tail = done.future;
    try {
      await previous;
      return await _coordinated(load);
    } finally {
      _queued--;
      done.complete();
    }
  }
}
