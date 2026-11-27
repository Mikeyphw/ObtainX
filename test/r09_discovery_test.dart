import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/folders/app_folder.dart';
import 'package:obtainium/providers/source_provider.dart';
import 'package:obtainium/services/r09_discovery.dart';

void main() {
  test('search combines name, package, source and category without URL secrets', () {
    bool matches(String query) => r09MatchesSearch(query, name: 'Reader Beta',
      packageId: 'org.example.reader', source: 'GitHub',
      sourceUrl: 'https://username:secret@github.com/o/r?token=private',
      categories: ['Books', 'Tools']);
    expect(matches('reader org.example github books'), isTrue);
    expect(matches('READER tools'), isTrue);
    expect(matches('  '), isTrue);
    expect(matches('secret'), isFalse);
    expect(matches('private'), isFalse);
    expect(matches('unrelated'), isFalse);
  });
  test('smart folder search round trips without changing old criteria', () {
    const app = App(id: 'org.example.reader', url: 'https://github.com/o/r',
      author: 'Example', name: 'Reader', latestVersion: '1',
      preferredApkIndex: 0, additionalSettings: {}, categories: ['Books']);
    final criteria = FolderCriteria(searchQuery: 'org.example books');
    final restored = FolderCriteria.fromJson(criteria.toJson());
    expect(restored.activeConditionCount, 1);
    expect(restored.matches(app, sourceIdentifier: 'GitHub', isUpToDate: false), isTrue);
    expect(FolderCriteria.fromJson({}).isEmpty, isTrue);
    expect(FolderCriteria().toJson().containsKey('searchQuery'), isFalse);
  });
  test('package groups preserve stable order and all listing indices', () {
    expect(r09PackageGroups(['a', 'b', 'a', 'c']), {'a': [0, 2], 'b': [1], 'c': [3]});
  });
  test('competing installable sources cannot be selected automatically', () {
    const packages = {'stable': 'a', 'nightly': 'a', 'reader': 'b'};
    expect(r09SafeBulkSelection(['stable','nightly','reader','track'], packages), {'reader','track'});
    expect(r09SelectListing({'stable','reader','track'}, 'nightly', packages), {'nightly','reader','track'});
    expect(r09SelectListing({'stable'}, 'track', packages), {'stable','track'});
  });
  test('known wrong ABI and configuration splits are not standalone choices', () {
    const abis = ['arm64-v8a', 'armeabi-v7a'];
    expect(r09ArtifactChoice('reader-x86_64.apk', abis).eligible, isFalse);
    expect(r09ArtifactChoice('reader-x86_64.apk', abis).reason, 'r09AbiMismatch');
    expect(r09ArtifactChoice('split_config.arm64_v8a.apk', abis).eligible, isFalse);
    expect(r09ArtifactChoice('split_config.arm64_v8a.apk', abis, downloadOnly: true).eligible, isTrue);
    expect(r09ArtifactChoice('reader.apks', abis).reason, 'r09MetadataPending');
    expect(r09ArtifactChoice('reader.apk', abis).eligible, isTrue);
  });
  test('safe default respects eligible explicit selection and rejects stale choice', () {
    const x86 = MapEntry('reader-x86.apk', 'x86');
    const arm32 = MapEntry('reader-armeabi-v7a.apk', 'arm32');
    const arm64 = MapEntry('reader-arm64-v8a.apk', 'arm64');
    const assets = [x86, arm32, arm64];
    const abis = ['armeabi-v7a', 'arm64-v8a'];
    expect(r09ChooseArtifact(assets, abis, x86), arm64);
    expect(r09ChooseArtifact(assets, abis, arm32), arm32);
    expect(r09ChooseArtifact(assets, abis, null, allowed: (_) => false), isNull);
  });
  test('empty and non-actionable states distinguish actual recorded facts', () {
    String state({bool attention = false, bool noSource = false,
      bool checked = true, bool trackOnly = false, bool update = false,
      bool installed = true, bool same = true}) => r09ListingState(
        needsAttention: attention, noSource: noSource, checked: checked,
        trackOnly: trackOnly, updateAvailable: update, installed: installed,
        equivalentVersion: same);
    expect(state(attention: true), 'r09NeedsAttention');
    expect(state(noSource: true), 'r09NoSource');
    expect(state(checked: false), 'r09NotChecked');
    expect(state(trackOnly: true), 'r09OnlyTrack');
    expect(state(update: true), 'r09UpdateAvailable');
    expect(state(installed: false), 'notInstalled');
    expect(state(same: false), 'r09StateUncertain');
    expect(state(), 'r09Current');
  });
  test('Actions artifact selection shares exact repository, identity and expiry gate', () {
    const source = 'https://github.com/o/r';
    const asset = MapEntry('android-apk.zip', 'https://api.github.com/repos/o/r/actions/artifacts/5/zip');
    final now = DateTime.utc(2026, 11, 25);
    final evidence = <String, dynamic>{'sourceUrl': source, 'archiveName': asset.key,
      'archiveUrl': asset.value, 'artifactId': 5, 'runId': 3, 'runAttempt': 1,
      'workflowId': 2, 'archiveSha256': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'commitSha': 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
      'expiresAt': now.add(const Duration(hours: 1)).toIso8601String()};
    final settings = <String, dynamic>{'r04GitHubSourceMode': 'actions',
      'r04ActionsArchiveEvidence': evidence};
    expect(r09ActionsEligible(asset, settings, source, now), isTrue);
    expect(r09ActionsEligible(asset, settings, 'https://github.com/o/other', now), isFalse);
    expect(r09ActionsEligible(asset, settings, source, now.add(const Duration(hours: 1))), isFalse);
    evidence['artifactId'] = 6;
    expect(r09ActionsEligible(asset, settings, source, now), isFalse);
    expect(r09ActionsEligible(asset, {}, source, now), isTrue);
  });
}
