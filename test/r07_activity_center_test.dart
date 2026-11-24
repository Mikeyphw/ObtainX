import 'dart:convert';
import 'dart:io';
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:obtainium/widgets/r07_activity_center_page.dart';
import 'package:obtainium/providers/apps_provider.dart';
import 'package:obtainium/providers/source_provider.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/services/r03_download_engine.dart';
import 'package:obtainium/services/r05_operation_journal.dart';
import 'package:obtainium/services/r05_operation_receipt.dart';
import 'package:obtainium/services/r07_activity_catalog.dart';

class _R07FakeApps extends ChangeNotifier implements AppsProvider {
  @override
  final AppListings apps = AppListings();
  @override
  Completer<List<App>>? get updateCheckCompleter => null;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  late Directory root;
  late R05OperationJournal journal;
  late R07ActivityCatalog catalog;
  const digest = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
  setUp(() async {
    root = await Directory.systemTemp.createTemp('r07-activity-fixture-');
    journal = R05OperationJournal(testingRoot: root);
    catalog = R07ActivityCatalog(testingRoot: root, installJournal: journal);
  });
  tearDown(() async {
    if (await root.exists()) await root.delete(recursive: true);
  });

  Future<R05OperationReceipt> begin(String listing) => journal.begin(
    listingKey: listing, packageId: 'com.example', backend: 'stock',
    kind: 'single', fileNames: const ['example.apk'],
    downloadSha256: digest,
  );
  Future<void> putDownload({
    R03Stage stage = R03Stage.downloading,
    String filename = 'store:one-build.apk',
    String? hash,
    int? total = r03ChunkBytes,
  }) async {
    final folder = Directory('${root.path}/r03-download-journal');
    await folder.create(recursive: true);
    final entry = R03DownloadRecord(
      jobId: digest, sourceFingerprint: digest,
      origin: 'https://example.org', finalOrigin: 'https://example.org',
      fileName: filename, stage: stage,
      blocks: const [digest], totalBytes: total,
      completedBytes: hash == null ? null : r03ChunkBytes,
      finalDigest: hash,
    );
    await File('${folder.path}/$digest.json').writeAsString(jsonEncode(entry.toJson()));
  }

  testWidgets('Activity Center renders its real journal without phantom actions',
    (tester) async {
      final fake = _R07FakeApps();
      addTearDown(fake.dispose);
      await tester.pumpWidget(ChangeNotifierProvider<AppsProvider>.value(
        value: fake,
        child: MaterialApp(home: R07ActivityCenterPage(catalog: catalog)),
      ));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 250));
      expect(find.text('Activity Center'), findsOneWidget);
      expect(find.textContaining('No matching activity records'), findsOneWidget);
      expect(find.text('Retry'), findsNothing);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );

  test('interruption becomes unknown, never confirmed', () async {
    final attempt = await begin('store:one');
    await journal.recoverInterruptedOnce(); // simulate app restart
    final restored = await catalog.load(trackedPackages: {'store:one':'com.example'});
    final item = restored.single;
    expect(item.id, 'install:${attempt.id}');
    expect(item.stage, 'unknown');
    expect(item.needsReview, true);
    expect(item.isFinished, false);
    expect(r07AllowedActions(item, listingMatches:true, liveDownload:false,
      cancellableInstall:false, independentlyInstalled:false),
      contains(R07ActivityAction.review));
    expect(r07AllowedActions(item, listingMatches:false, liveDownload:false,
      cancellableInstall:false, independentlyInstalled:false),
      isNot(contains(R07ActivityAction.retry)));
  });

  test('opening Activity Center does not convert a live pending install into unknown', () async {
    await begin('store:one');
    expect((await catalog.load()).single.stage, 'pending');
    expect((await journal.list()).single.stage, R05InstallStage.pending);
  });

  test('concurrent attempts have distinct durable IDs', () async {
    await Future.wait([begin('store:one'), begin('store:two')]);
    final all = await catalog.load();
    expect(all.length, 2);
    expect(all.map((x) => x.id).toSet().length, 2);
  });

  test('approval remains reviewable after restart, not retryable', () async {
    final r = await begin('store:one');
    await journal.transition(r.id, R05InstallStage.awaitingApproval);
    final entries = await R07ActivityCatalog(testingRoot:root,
      installJournal: R05OperationJournal(testingRoot:root)).load();
    final actions = r07AllowedActions(entries.single, listingMatches:true,
      liveDownload:false, cancellableInstall:false,
      independentlyInstalled:false);
    expect(entries.single.stage, 'awaitingApproval');
    expect(actions, contains(R07ActivityAction.review));
    expect(actions, isNot(contains(R07ActivityAction.retry)));
    expect(actions, isNot(contains(R07ActivityAction.open)));
  });

  test('handoff does not provide Open, even with an installed package', () async {
    final r = await begin('store:one');
    await journal.transition(r.id, R05InstallStage.handedOff);
    final e = (await catalog.load()).single;
    final actions = r07AllowedActions(e, listingMatches:true,
      liveDownload:false, cancellableInstall:false,
      independentlyInstalled:true);
    expect(actions, contains(R07ActivityAction.review));
    expect(actions, isNot(contains(R07ActivityAction.open)));
  });

  test('competing install receipts cannot cancel one another', () async {
    await begin('store:one');
    await begin('store:one');
    final entries = await catalog.load();
    for (final entry in entries) {
      expect(entry.uniquePendingOwnership, isFalse);
      expect(r07AllowedActions(entry,listingMatches:true,liveDownload:false,
        cancellableInstall:true,independentlyInstalled:false),
        isNot(contains(R07ActivityAction.cancel)));
    }
  });

  test('failed install retry requires same listing identity', () async {
    final r = await begin('store:one');
    await journal.transition(r.id, R05InstallStage.failed);
    final e = (await catalog.load()).single;
    expect(r07AllowedActions(e, listingMatches:true, liveDownload:false,
      cancellableInstall:false, independentlyInstalled:false),
      contains(R07ActivityAction.retry));
    expect(r07AllowedActions(e, listingMatches:false, liveDownload:false,
      cancellableInstall:false, independentlyInstalled:false),
      isNot(contains(R07ActivityAction.retry)));
  });

  test('unverified transfer is clamped below 100%', () async {
    await putDownload();
    final e = (await catalog.load(trackedPackages: {'store:one':'com.example'})).single;
    expect(e.progress, lessThan(1.0));
    expect(e.verifiedBytes, r03ChunkBytes);
    expect(e.listingKey, 'store:one');
  });

  test('only digest-finalized download can display 100%', () async {
    await putDownload(stage:R03Stage.ready, hash:digest);
    final e = (await catalog.load()).single;
    expect(e.progress, 1.0);
    expect(e.stage, 'ready');
    expect(e.kind, 'download');
  });

  test('R03 in-progress atomic .tmp file never becomes a completed operation', () async {
    final folder = Directory('${root.path}/r03-download-journal');
    await folder.create();
    await File('${folder.path}/$digest.json.tmp').writeAsString('{}');
    expect(await catalog.load(), isEmpty);
  });

  test('forged R03 final digest is not 100% progress', () async {
    await putDownload(stage:R03Stage.ready,hash:'INVALID');
    final e = (await catalog.load()).single;
    expect(e.progress, lessThan(1.0));
  });

  test('unknown total stays indeterminate', () async {
    await putDownload(total:null);
    expect((await catalog.load()).single.progress, null);
  });

  test('two overlapping listing IDs prevent cross-source attribution', () {
    expect(r07UniqueListingForFile('a-long-build.apk', ['a', 'a-long']), null);
    expect(r07UniqueListingForFile('a-long-build.apk', ['a-long']), 'a-long');
    expect(r07UniqueListingForFile('any-build.apk', ['different']), null);
  });

  test('R03 cancellation requires exact matching active provider state', () async {
    await putDownload();
    final e = (await catalog.load(trackedPackages:{'store:one':'com.example'})).single;
    final none = r07AllowedActions(e, listingMatches:false, liveDownload:true,
      cancellableInstall:false, independentlyInstalled:false);
    expect(none, isNot(contains(R07ActivityAction.cancel)));
    final live = r07AllowedActions(e, listingMatches:true, liveDownload:true,
      cancellableInstall:false, independentlyInstalled:false);
    expect(live, isNot(contains(R07ActivityAction.cancel)));
    // A live provider token, unlike a historical R03 job, may be cancelled.
    final current = R07ActivityRecord(
      id:'live:store:one',kind:'live',stage:'downloading',
      title:'Example',updatedUtc:DateTime.utc(2026),
      listingKey:'store:one',packageId:'com.example');
    expect(r07AllowedActions(current,listingMatches:true,liveDownload:true,
      cancellableInstall:false,independentlyInstalled:false),
      contains(R07ActivityAction.cancel));
  });

  test('symlink or oversized journal is refused without deleting evidence', () async {
    final folder = Directory('${root.path}/r03-download-journal');
    await folder.create();
    final suspicious = File('${root.path}/private');
    await suspicious.writeAsString('private');
    await Link('${folder.path}/$digest.json').create(suspicious.path);
    await expectLater(catalog.load(), throwsFormatException);
    expect(await suspicious.readAsString(), 'private');
  });

  test('bad fingerprint cannot be attributed as a valid transfer', () async {
    final folder = Directory('${root.path}/r03-download-journal');
    await folder.create();
    await File('${folder.path}/$digest.json').writeAsString(jsonEncode({
      'schema':'obtainx.r03.download.v1',
      'jobId':'different', 'sourceFingerprint':'different',
      'origin':'https://example.org', 'finalOrigin':'https://example.org',
      'fileName':'a.apk','stage':'ready','blocks':[],
      'validatedBytes':0, 'totalBytes':null, 'etag':null,
      'lastModified':null, 'finalDigest':null,'completedBytes':null,
    }));
    await expectLater(catalog.load(), throwsFormatException);
  });
}
