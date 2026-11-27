import 'dart:async';
import 'dart:convert';
import 'dart:isolate';

import 'package:easy_localization/easy_localization.dart';
import 'package:flutter/material.dart';
import 'package:obtainium/custom_errors.dart';
import 'package:obtainium/providers/source_provider.dart';

/// A preview is an observation of bounded sample strings, not a release search
/// or a claim about the next install. Never send credentials or download URLs.
class R10RegexPreviewRequest {
  R10RegexPreviewRequest({
    required this.pattern,
    required this.group,
    required this.extraction,
    required this.apkNames,
    required this.invert,
    required Iterable<String> samples,
  }) : samples = List.unmodifiable(samples.where((s) => s.isNotEmpty &&
            s.length <= 2048).take(40));

  final String pattern;
  final String group;
  final bool extraction;
  final bool apkNames;
  final bool invert;
  final List<String> samples;

  String get identity => jsonEncode([
    pattern, group, extraction, apkNames, invert, samples,
  ]);
}

class R10RegexPreviewRow {
  const R10RegexPreviewRow(this.sample, this.matches, this.extracted);
  final String sample;
  final bool matches;
  final String? extracted;
}

enum R10RegexPreviewStatus { ready, invalid, limited, timeout, unavailable }

class R10RegexPreviewResult {
  const R10RegexPreviewResult(this.status, [this.rows = const []]);
  final R10RegexPreviewStatus status;
  final List<R10RegexPreviewRow> rows;
}

/// Run only in a worker isolate for arbitrary user regexes. The worker can be
/// killed even during catastrophic backtracking; no pattern runs on the UI.
R10RegexPreviewResult evaluateR10RegexPreview(R10RegexPreviewRequest request) {
  if (request.pattern.length > 2048 || request.group.length > 256) {
    return const R10RegexPreviewResult(R10RegexPreviewStatus.limited);
  }
  try {
    final pattern = RegExp(request.pattern);
    final rows = <R10RegexPreviewRow>[];
    for (final sample in request.samples) {
      if (request.extraction) {
        try {
          final version = extractVersion(request.pattern, request.group, sample);
          rows.add(R10RegexPreviewRow(sample, true, version ?? sample));
        } on NoVersionError {
          rows.add(R10RegexPreviewRow(sample, false, null));
        }
      } else {
        final matches = request.apkNames
            ? filterApks([MapEntry(sample, '')], request.pattern, request.invert)
                  .isNotEmpty
            : request.pattern.isEmpty || pattern.hasMatch(sample);
        rows.add(R10RegexPreviewRow(sample, matches, null));
      }
    }
    return R10RegexPreviewResult(R10RegexPreviewStatus.ready, rows);
  } on FormatException {
    return const R10RegexPreviewResult(R10RegexPreviewStatus.invalid);
  }
}

void _evaluateWorker((SendPort, R10RegexPreviewRequest) message) {
  message.$1.send(evaluateR10RegexPreview(message.$2));
}

class R10RegexPreviewJob {
  final ReceivePort _port = ReceivePort();
  Isolate? _isolate;
  bool _cancelled = false;
  bool _portClosed = false;

  Future<R10RegexPreviewResult> run(R10RegexPreviewRequest request) async {
    try {
      _isolate = await Isolate.spawn(
        _evaluateWorker,
        (_port.sendPort, request),
        onError: _port.sendPort,
        onExit: _port.sendPort,
      );
      if (_cancelled) {
        return const R10RegexPreviewResult(R10RegexPreviewStatus.unavailable);
      }
      final result = await _port.first.timeout(const Duration(seconds: 1));
      return result is R10RegexPreviewResult
          ? result
          : const R10RegexPreviewResult(R10RegexPreviewStatus.unavailable);
    } on TimeoutException {
      return const R10RegexPreviewResult(R10RegexPreviewStatus.timeout);
    } catch (_) {
      return const R10RegexPreviewResult(R10RegexPreviewStatus.unavailable);
    } finally {
      cancel();
    }
  }

  void cancel() {
    _cancelled = true;
    _isolate?.kill(priority: Isolate.immediate);
    _isolate = null;
    if (!_portClosed) {
      _portClosed = true;
      _port.close();
    }
  }
}

class R10RegexPreview extends StatefulWidget {
  const R10RegexPreview({
    super.key,
    required this.request,
    required this.hasFetchedSamples,
  });
  final R10RegexPreviewRequest? request;
  final bool hasFetchedSamples;

  @override
  State<R10RegexPreview> createState() => _R10RegexPreviewState();
}

class _R10RegexPreviewState extends State<R10RegexPreview> {
  Timer? _debounce;
  R10RegexPreviewJob? _job;
  R10RegexPreviewResult? _result;
  int _generation = 0;

  @override
  void initState() {
    super.initState();
    _schedule();
  }

  @override
  void didUpdateWidget(covariant R10RegexPreview oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.request?.identity != widget.request?.identity) {
      _schedule();
    }
  }

  void _schedule() {
    _debounce?.cancel();
    _job?.cancel();
    _job = null;
    _result = null;
    final generation = ++_generation;
    final request = widget.request;
    if (request == null) return;
    _debounce = Timer(const Duration(milliseconds: 180), () async {
      final job = R10RegexPreviewJob();
      _job = job;
      final result = await job.run(request);
      if (!mounted || generation != _generation) return;
      setState(() => _result = result);
    });
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _job?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final request = widget.request;
    final result = _result;
    final String summary;
    if (request == null) {
      summary = tr('r10RegexChooseExpression');
    } else if (result == null) {
      summary = tr('r10RegexEvaluating');
    } else {
      summary = switch (result.status) {
        R10RegexPreviewStatus.invalid => tr('invalidRegEx'),
        R10RegexPreviewStatus.limited => tr('r10RegexLimit'),
        R10RegexPreviewStatus.timeout => tr('r10RegexTimeout'),
        R10RegexPreviewStatus.unavailable => tr('r10RegexUnavailable'),
        R10RegexPreviewStatus.ready => result.rows.isEmpty
            ? tr('r10RegexNoSamples')
            : tr('r10RegexCount', args: [
                result.rows.where((row) => row.matches).length.toString(),
                result.rows.length.toString(),
              ]),
      };
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(tr(widget.hasFetchedSamples
            ? 'r10RegexFetchedSamples' : 'r10RegexManualSamples')),
        if (request?.apkNames == true && request?.invert == true)
          Text(tr('r10RegexInverted')),
        Semantics(
          liveRegion: true,
          child: Text(summary, key: const ValueKey('r10-regex-result')),
        ),
        if (result?.status == R10RegexPreviewStatus.ready)
          for (final row in result!.rows)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                '${tr(row.matches ? 'r10RegexKept' : 'r10RegexRejected')}: '
                '${row.sample}'
                '${row.extracted == null ? '' : ' → ${row.extracted}'}',
              ),
            ),
      ],
    );
  }
}
