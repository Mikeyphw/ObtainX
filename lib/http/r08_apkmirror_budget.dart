/// Respectful APKMirror request budget; scoped to one Dart isolate.
/// No alternate hosts, CAPTCHA bypass, fabricated headers or automatic retries.
library;

import 'dart:async';
import 'dart:io';

import 'package:http/http.dart' as http;

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
  }) : _clock = clock ?? DateTime.now,
       _wait = wait ?? ((duration) => Future<void>.delayed(duration));

  static final shared = ApkMirrorRequestBudget();
  final Duration spacing;
  final int maxQueued;
  final DateTime Function() _clock;
  final Future<void> Function(Duration) _wait;
  Future<void> _tail = Future<void>.value();
  DateTime? _nextStart;
  DateTime? _blockedUntil;
  int _queued = 0;

  static bool appliesTo(Uri uri) =>
      uri.scheme == 'https' &&
      const {'apkmirror.com', 'www.apkmirror.com'}.contains(uri.host);

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
      final blocked = _blockedUntil;
      if (blocked != null && blocked.isAfter(_clock())) {
        throw const ApkMirrorRequestDeferred(
          'APKMirror is rate-limited or unavailable; wait before checking again.',
        );
      }
      final next = _nextStart;
      if (next != null && next.isAfter(_clock())) {
        await _wait(next.difference(_clock()));
      }
      _nextStart = _clock().add(spacing);
      final response = await load();
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
      return response;
    } finally {
      _queued--;
      done.complete();
    }
  }
}
