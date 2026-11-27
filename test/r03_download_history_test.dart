import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/services/r03_download_engine.dart';
import 'package:obtainium/services/r03_download_history.dart';
import 'package:obtainium/services/r07_journal_guard.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  late Directory root, cache, live;
  late R03DownloadHistory history;
  const channel = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
  const other = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
  final cutoff = DateTime.utc(2026, 2);
  setUp(() async {
    root = await Directory.systemTemp.createTemp('ox-gap03-transfer-history-');
    cache = await Directory('${root.path}/cache').create();
    live = await Directory('${root.path}/r03-download-journal').create();
    history = R03DownloadHistory(cache: cache, testingRoot: root);
  });
  tearDown(() async { await root.delete(recursive: true); });
  Future<File> record(String key, String fileName, {String? ownerChannel = channel,
      R03Stage stage = R03Stage.failed, String? listing = 'source:one'}) async {
    final id = r07JournalFingerprint(key);
    final receipt = R03DownloadRecord(jobId: id, sourceFingerprint: id,
      origin: 'https://example.org', finalOrigin: 'https://example.org', fileName: fileName,
      stage: stage, blocks: const [], cacheRootFingerprint: r07JournalFingerprint(cache.absolute.path),
      historyBinding: ownerChannel == null || listing == null ? null :
        R03HistoryBinding(listing, 'com.example', ownerChannel, releaseFingerprint: channel));
    final file = File('${live.path}/$id.json');
    await file.writeAsString(jsonEncode(receipt.toJson()));
    await file.setLastModified(DateTime.utc(2026, 1));
    return file;
  }
  test('archive and retention preserve recovery bytes, unknown and other channel', () async {
    final eligible = await record('eligible', 'one.apk');
    final otherChannel = await record('other', 'two.apk', ownerChannel: other);
    final retained = await record('retained', 'three.apk');
    final unknown = await record('unknown', 'four.apk', ownerChannel: null);
    final partial = await File('${cache.path}/three.apk.part').writeAsString('retain');
    expect(await history.archiveTerminalWithoutBytes(), 2);
    expect(await eligible.exists(), isFalse);
    expect(await otherChannel.exists(), isFalse);
    expect(await retained.exists(), isTrue);
    expect(await unknown.exists(), isTrue);
    final preview = await history.previewTerminalBefore(cutoff, channel: channel, listingKey: 'source:one');
    expect(preview.entries.length, 1);
    expect(await history.prune(preview), 1);
    expect(await partial.readAsString(), 'retain');
    expect(await unknown.exists(), isTrue);
    expect((await R03DownloadHistory.archiveOf(live).list().toList()).length, 1);
  });
  test('stale preview refuses deletion if a partial appears', () async {
    final original = await record('one', 'one.apk');
    final preview = await history.previewTerminalBefore(cutoff, channel: channel);
    expect(preview.entries.length, 1);
    await File('${cache.path}/one.apk.part').writeAsString('recovery');
    await expectLater(history.prune(preview), throwsStateError);
    expect(await original.exists(), isTrue);
  });
  test('more than 512 terminal entries and staging files cannot block scoped retention', () async {
    for (var i = 0; i < 520; i++) {
      await record('history-$i', 'archive-$i.apk', ownerChannel: i.isEven ? channel : other);
    }
    final recovery = await record('recovery', 'recovery.apk');
    await File('${cache.path}/recovery.apk.part').writeAsString('preserve');
    await File('${live.path}/${r07JournalFingerprint('staging')}.json.tmp').writeAsString('staging');
    final preview = await history.previewTerminalBefore(cutoff, channel: channel);
    expect(preview.entries.length, 260);
    expect(await recovery.exists(), isTrue);
    final rival = R03DownloadHistory(cache: cache, testingRoot: root);
    final outcomes = await Future.wait([for (final owner in [history, rival]) () async {
      try { return await owner.prune(preview); }
      on StateError { return -1; }
      on R07JournalBusy { return -1; }
    }()]);
    expect(outcomes.toSet(), {260, -1});
    expect((await history.previewTerminalBefore(cutoff, channel: channel)).entries, isEmpty);
    expect((await history.previewTerminalBefore(cutoff, channel: other)).entries.length, 260);
    expect(await recovery.exists(), isTrue);
  });

  test('corrupt individual receipt cannot authorize destructive retention', () async {
    final good = await record('good', 'one.apk');
    final corrupt = await File('${live.path}/${r07JournalFingerprint('corrupt')}.json').writeAsString('{');
    await expectLater(history.previewTerminalBefore(cutoff), throwsFormatException);
    expect(await good.exists(), isTrue);
    expect(await corrupt.readAsString(), '{');
  });
}
