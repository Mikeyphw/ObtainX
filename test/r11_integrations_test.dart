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

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
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
      packageId: 'com.example.app', backend: 'system', kind: 'apk', fileNames: ['base.apk']);
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
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
    final root = await Directory.systemTemp.createTemp('r11-schedule-');
    addTearDown(() async { await root.delete(recursive: true); });
    final path = '${root.path}/schedule.db';
    final now = DateTime(2026, 1, 1, 12);
    expect(await r11ClaimAutomaticRun(15, now, databasePath: path), isTrue);
    expect(await r11ClaimAutomaticRun(15, now, databasePath: path), isFalse);
    expect(await r11ClaimAutomaticRun(15, now.add(const Duration(minutes: 15)), databasePath: path), isTrue);
  });
}
