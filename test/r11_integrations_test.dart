import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/providers/apps_provider.dart';
import 'package:obtainium/providers/settings_provider.dart';
import 'package:obtainium/providers/source_provider.dart';
import 'package:obtainium/services/r03_download_engine.dart';
import 'package:obtainium/services/r05_operation_journal.dart';
import 'package:obtainium/services/r05_operation_receipt.dart';
import 'package:obtainium/services/r11_automation.dart';
import 'package:obtainium/services/r07_operation_timeline.dart';
import 'package:obtainium/services/r07_activity_catalog.dart';
import 'package:obtainium/services/r11_external_requests.dart';
import 'package:obtainium/services/r11_history.dart';
import 'package:obtainium/services/r11_schedule.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

App listing({String? key, String url = 'https://github.com/example/project'}) => App(
  id: 'com.example.app', listingId: key, url: url, name: 'Example', author: 'Example',
  latestVersion: '1', installedVersion: '1', preferredApkIndex: 0, additionalSettings: const {},
);

class _NoProvider implements AppsProvider {
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _AutomationProvider implements AppsProvider {
  @override
  final AppListings apps = AppListings();
  @override
  bool isForeground = true;
  @override
  Completer<List<App>>? get updateCheckCompleter => null;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _RevokingTimeline extends R07OperationTimeline {
  _RevokingTimeline({required super.testingRoot, required this.onWritten});
  final void Function() onWritten;
  @override
  Future<List<R07TimelineEntry>> enqueue(List<R07OperationIntent> intents) async {
    final rows = await super.enqueue(intents);
    onWritten();
    return rows;
  }
}

void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  TestWidgetsFlutterBinding.ensureInitialized();
  test('history export streams across pages with scope and atomic failure', () async {
    final root = await Directory.systemTemp.createTemp('ox-audit02-export-');
    try {
      final timeline = R07OperationTimeline(testingRoot: root);
      final app = listing();
      final channel = List.filled(64, 'a').join();
      final release = List.filled(64, 'b').join();
      await timeline.enqueue(List.generate(225, (i) => R07OperationIntent(kind: 'check',
        listingKey: i == 224 ? 'other:listing' : app.listingKey,
        packageId: app.id, channel: channel, release: release)));
      final catalog = R07ActivityCatalog(testingRoot: root,
        installJournal: R05OperationJournal(testingRoot: root));
      Future<void> visit(Future<void> Function(R07ActivityRecord) append) =>
        catalog.visitForExport(append, listingKey: app.listingKey);
      final destination = File('${root.path}/history.json');
      await writeR11PublicHistory(destination, visit);
      final value = jsonDecode(await destination.readAsString()) as Map;
      expect(value['historicalOnly'], isTrue);
      final records = value['records'] as List;
      expect(records.length, 224);
      expect(records.map((row) => (row as Map)['id']).toSet().length, 224);
      expect(records.every((row) => (row as Map)['listing'] == r11HistoryKey(app.listingKey)), isTrue);
      final refused = File('${root.path}/refused.json');
      await expectLater(writeR11PublicHistory(refused, visit, maxBytes: 100), throwsA(isA<FileSystemException>()));
      expect(await refused.exists(), isFalse);
      expect(await File('${refused.path}.part').exists(), isFalse);
      var calls = 0;
      await expectLater(writeR11PublicHistory(refused, visit, checkCancellation: () {
        if (++calls == 5) throw StateError('Interrupted');
      }), throwsStateError);
      expect(await refused.exists(), isFalse);
      expect(await File('${refused.path}.part').exists(), isFalse);
    } finally {
      await root.delete(recursive: true);
    }
  });
  test('external links have one bounded exact package and no caller extras', () {
    expect(r11PackageFromLink(Uri.parse('obtainium://open?id=com.example.app')), 'com.example.app');
    for (final value in ['obtainium://open?id=com.example.app&id=com.other.app',
      'obtainium://open?id=com.example.app&install=true', 'obtainium://open?id=com.example.app%2Fbad',
      'obtainium://open?id=bad', 'obtainium://user@open?id=com.example.app',
      'obtainium://open:9?id=com.example.app', 'obtainium://open?id=com.example.app#x']) {
      expect(r11PackageFromLink(Uri.parse(value)), isNull, reason: value);
    }
  });
  test('multi-source selection cannot silently fall back after removal or source swap', () {
    final apps = AppListings();
    final first = listing();
    final second = listing(key: 'com.example.app@GitHub', url: 'https://github.com/example/other');
    apps[first.listingKey] = AppInMemory(first, null, null, null);
    apps[second.listingKey] = AppInMemory(second, null, null, null);
    expect(r11PackageListings(apps, first.id).length, 2);
    final selected = r11PackageListings(apps, first.id).first;
    apps.remove(first.listingKey);
    expect(apps[first.id]?.app.listingKey, second.listingKey); // legacy fallback
    expect(r11ExactLiveListing(apps, selected), isNull);
    apps[second.listingKey] = AppInMemory(second.copyWith(url: first.url), null, null, null);
    expect(r11ExactLiveListing(apps, second), isNull);
  });
  test('automation accepts only four known actions and a bounded correlation ID', () {
    for (final action in R11AutomationAction.values) {
      final request = R11AutomationRequest.parse(Uri.parse('obtainium://automation?id=com.example.app&action=${action.name}&request=req_123'));
      expect(request?.action, action);
    }
    for (final value in ['action=install&request=x', 'action=check&request=x&recipient=com.other',
      'action=check&request=x&request=y', 'action=state&request=%0A']) {
      expect(R11AutomationRequest.parse(Uri.parse('obtainium://automation?id=com.example.app&$value')), isNull);
    }
  });
  test('automation defaults to off and disabled requests cannot execute provider work', () async {
    SharedPreferences.setMockInitialValues({});
    final settings = SettingsProvider()..prefs = await SharedPreferences.getInstance();
    addTearDown(settings.dispose);
    final provider = _NoProvider();
    expect(settings.r11AutomationEnabled, isFalse);
    final app = listing();
    final request = R11AutomationRequest(app.id, R11AutomationAction.download, 'r1');
    expect(await r11RunAutomation(provider, settings, request, app), {'status': 'refused'});
  });
  group('GAP-05 enabled automation dispatch', () {
    late Directory root;
    late SettingsProvider settings;
    late _AutomationProvider provider;
    late App app;
    late R07OperationTimeline timeline;
    setUp(() async {
      root = await Directory.systemTemp.createTemp('r11-automation-');
      SharedPreferences.setMockInitialValues({'r11AutomationEnabled': true});
      settings = SettingsProvider()..prefs = await SharedPreferences.getInstance();
      provider = _AutomationProvider();
      app = listing().copyWith(apkUrls: const [MapEntry('base.apk', 'https://example.org/base.apk')]);
      provider.apps[app.listingKey] = AppInMemory(app, null, null, null);
      timeline = R07OperationTimeline(testingRoot: root);
    });
    tearDown(() async {
      settings.dispose();
      await root.delete(recursive: true);
    });
    R11AutomationRequest request(R11AutomationAction action) => R11AutomationRequest(app.id, action, 'r1');
    test('download persists exact release without entering a provider transfer', () async {
      final result = await r11RunAutomation(provider, settings,
        request(R11AutomationAction.download), app, timeline: timeline);
      expect(result['status'], 'queuedNotInstalled');
      final rows = await R07OperationTimeline(testingRoot: root).readActivity();
      final row = rows.single;
      expect(result['operation'], row.id);
      expect(row.stage, 'queued');
      expect(row.intent.matches(R07OperationIntent(kind: 'download',
        listingKey: app.listingKey, packageId: app.id, channel: r11ChannelFingerprint(app),
        release: downloadReleaseCacheKey(InstallReleaseSnapshot.fromApp(app)))), isTrue);
      expect(row.attemptId, isNull);
      expect(row.transferId, isNull);
    });
    test('revoked consent cancels only the newly queued intent', () async {
      final first = await r11RunAutomation(provider, settings,
        request(R11AutomationAction.download), app, timeline: timeline);
      final revoking = _RevokingTimeline(testingRoot: root,
        onWritten: () { settings.r11AutomationEnabled = false; });
      expect(await r11RunAutomation(provider, settings, request(R11AutomationAction.download),
        app, timeline: revoking), {'status': 'refused'});
      final rows = await timeline.readActivity();
      expect(rows.length, 2);
      expect(rows.singleWhere((row) => row.id == first['operation']).stage, 'queued');
      expect(rows.singleWhere((row) => row.id != first['operation']).stage, 'cancelled');
    });
    test('release change during enqueue cancels old intent', () async {
      final revoking = _RevokingTimeline(testingRoot: root, onWritten: () {
        provider.apps[app.listingKey] = AppInMemory(app.copyWith(latestVersion: '2'), null, null, null);
      });
      expect(await r11RunAutomation(provider, settings, request(R11AutomationAction.download),
        app, timeline: revoking), {'status': 'refused'});
      expect((await timeline.readActivity()).single.stage, 'cancelled');
    });
    test('check and state return only current observation and revalidate consent', () async {
      final checked = await r11RunAutomation(provider, settings, request(R11AutomationAction.check),
        app, checkSource: (_) async => app.copyWith(latestVersion: '2'));
      expect(checked['status'], 'ok');
      expect(checked['persisted'], isFalse);
      expect(checked['updateAvailable'], isTrue);
      expect(provider.apps[app.listingKey]!.app.latestVersion, '1');
      final state = await r11RunAutomation(provider, settings, request(R11AutomationAction.state), app);
      expect(state['status'], 'ok');
      expect(state['observedFrom'], 'currentLibrary');
      expect(state['installed'], isFalse);
      final changed = await r11RunAutomation(provider, settings, request(R11AutomationAction.check),
        app, checkSource: (_) async => app.copyWith(url: 'https://example.org/other'));
      expect(changed['status'], 'notAvailable');
      final revoked = await r11RunAutomation(provider, settings, request(R11AutomationAction.check),
        app, checkSource: (_) async { settings.r11AutomationEnabled = false; return app; });
      expect(revoked['status'], 'notAvailable');
    });
    test('receipt ignores newer wrong-channel and unknown-channel attempts', () async {
      final journal = R05OperationJournal(testingRoot: root);
      Future<R05OperationReceipt> begin(String? channel) => journal.begin(listingKey: app.listingKey,
        packageId: app.id, backend: 'system', kind: 'apk', fileNames: ['private.apk'],
        channelFingerprint: channel);
      final current = await begin(r11ChannelFingerprint(app));
      await begin('b' * 64);
      await begin(null);
      final result = await r11RunAutomation(provider, settings, request(R11AutomationAction.receipt),
        app, journal: journal);
      expect(result['status'], 'ok');
      expect(result['receipt'], r11PublicReceipt(current));
      expect(jsonEncode(result), isNot(contains('private.apk')));
    });
  });
  test('last scheduling observation survives reopening and replaces previous reason', () async {
    final root = await Directory.systemTemp.createTemp('r11-observation-');
    addTearDown(() async { await root.delete(recursive: true); });
    final path = '${root.path}/observation.db';
    final start = DateTime.utc(2026, 11, 26, 12);
    expect(await r11ReadScheduleObservation(databasePath: path), isNull);
    await r11RecordScheduleObservation(R11ScheduleReason.quietHours, start, databasePath: path);
    final quiet = await r11ReadScheduleObservation(databasePath: path);
    expect(quiet?.reason, R11ScheduleReason.quietHours);
    expect(quiet?.observedUtc, start);
    final next = start.add(const Duration(minutes: 30));
    await r11RecordScheduleObservation(R11ScheduleReason.allowed, next, databasePath: path);
    final allowed = await r11ReadScheduleObservation(databasePath: path);
    expect(allowed?.reason, R11ScheduleReason.allowed);
    expect(allowed?.observedUtc, next);
  });
  test('receipt projection excludes raw metadata and separates old channel from current', () {
    final app = listing();
    final digest = r11ChannelFingerprint(app);
    final changed = app.copyWith(url: 'https://github.com/example/new');
    expect(r11ChannelFingerprint(changed), isNot(digest));
    final receipt = R05OperationReceipt.start(id: 'r05_12345678_123456789abcdef0',
      listingKey: app.listingKey, packageId: app.id, backend: 'system', kind: 'apk',
      fileNames: ['PRIVATE.apk'], sourceHost: 'private.example', sourceBranch: 'SECRET_BRANCH',
      channelFingerprint: digest);
    final decoded = R05OperationReceipt.decode(receipt.encode());
    expect(decoded.channelFingerprint, digest);
    final shared = r11PublicReceipt(decoded);
    expect(shared['historicalOnly'], isTrue);
    expect(jsonEncode(shared), isNot(contains('PRIVATE.apk')));
    expect(jsonEncode(shared), isNot(contains('SECRET_BRANCH')));
    expect(jsonEncode(shared), isNot(contains('private.example')));
    expect(R05OperationReceipt.fromJson({...receipt.toJson()}..remove('channelFingerprint')).channelFingerprint, isNull);
  });
  test('R03 history owner survives persisted records and refuses malformed bindings', () {
    final app = listing();
    final binding = R03HistoryBinding(app.listingKey, app.id, r11ChannelFingerprint(app));
    final record = R03DownloadRecord(jobId: 'a' * 64, sourceFingerprint: 'a' * 64,
      origin: 'https://example.org', finalOrigin: 'https://example.org', fileName: 'test.apk',
      stage: R03Stage.queued, blocks: const [], historyBinding: binding);
    expect(R03DownloadRecord.fromJson(record.toJson()).historyBinding, binding);
    expect(record.copyWith(stage: R03Stage.downloading).historyBinding, binding);
    expect(R03DownloadRecord.fromJson({...record.toJson()}..remove('historyBinding')).historyBinding, isNull);
    expect(() => R03HistoryBinding('../x', app.id, 'x'), throwsFormatException);
  });
  test('retention removes only terminal receipts in the requested listing', () async {
    final root = await Directory.systemTemp.createTemp('r11-history-');
    addTearDown(() async { await root.delete(recursive: true); });
    final journal = R05OperationJournal(testingRoot: root);
    Future<R05OperationReceipt> start(String key) => journal.begin(listingKey: key,
      packageId: 'com.example.app', backend: 'system', kind: 'apk', fileNames: ['base.apk'],
      channelFingerprint: 'a' * 64);
    final failed = await start('a');
    final pending = await start('a');
    final other = await start('b');
    await journal.transition(failed.id, R05InstallStage.failed);
    await journal.transition(other.id, R05InstallStage.failed);
    expect(await journal.pruneTerminalBefore(DateTime.now().add(const Duration(days: 1)), listingKey: 'a'), 1);
    expect((await journal.list()).map((r) => r.id).toSet(), {pending.id, other.id});
  });
  test('quiet windows span midnight; clock rollback cannot bypass rate limit', () {
    expect(r11InQuietHours(DateTime(2026, 1, 1, 23), 22 * 60, 7 * 60), isTrue);
    expect(r11InQuietHours(DateTime(2026, 1, 1, 6), 22 * 60, 7 * 60), isTrue);
    expect(r11InQuietHours(DateTime(2026, 1, 1, 7), 22 * 60, 7 * 60), isFalse);
    expect(r11InQuietHours(DateTime(2026, 1, 1, 12), 0, 0), isFalse);
    expect(r11RateLimited(100, 1000, 15), isTrue);
    expect(r11RateLimited(100, 1000, 0), isFalse);
  });
  test('SQLite scheduling claim is durable and rejects duplicate starts', () async {
    final root = await Directory.systemTemp.createTemp('r11-schedule-');
    addTearDown(() async { await root.delete(recursive: true); });
    final path = '${root.path}/schedule.db';
    final now = DateTime(2026, 1, 1, 12);
    expect(await r11ClaimAutomaticRun(15, now, databasePath: path), isTrue);
    expect(await r11ClaimAutomaticRun(15, now, databasePath: path), isFalse);
    expect(await r11ClaimAutomaticRun(15, now.add(const Duration(minutes: 15)), databasePath: path), isTrue);
  });
}
