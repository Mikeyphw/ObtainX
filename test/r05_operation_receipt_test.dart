import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/services/r05_operation_receipt.dart';

void main() {
  const digest = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
  R05OperationReceipt begin() => R05OperationReceipt.start(
    id: 'r05_12345678_123456789abcdef0', listingKey: 'store:package',
    packageId: 'com.example.app', backend: 'system', kind: 'apk',
    fileNames: <String>['base.apk'], sourceHost: 'api.github.com',
    commitSha: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    downloadSha256: digest, expectedVersionCode: 123,
    selectedApkSha256: [digest], archiveSignerSet: [digest],
    now: DateTime.utc(2026, 11, 16),
  );
  test('pending, approval, handoff and unknown are distinct durable states', () {
    final pending = begin();
    final review = pending.transition(R05InstallStage.awaitingApproval,
        now: DateTime.utc(2026, 11, 16, 0, 1));
    final handed = review.transition(R05InstallStage.handedOff,
        now: DateTime.utc(2026, 11, 16, 0, 2));
    final unknown = handed.transition(R05InstallStage.unknown,
        now: DateTime.utc(2026, 11, 16, 0, 3));
    expect(R05OperationReceipt.decode(unknown.encode()).stage, R05InstallStage.unknown);
    expect(unknown.verifiedUtc, isNull);
    expect(unknown.revision, 3);
    expect(() => unknown.transition(R05InstallStage.cancelled), throwsStateError);
  });
  test('installer success and timer are never independent Android proof', () {
    final pending = begin();
    expect(() => pending.transition(R05InstallStage.confirmed), throwsStateError);
    expect(() => pending.transition(R05InstallStage.confirmed,
      evidence: const R05AndroidEvidence(packageName: 'com.example.app',
        exactAttemptMatches: false, versionCode: 123)), throwsStateError);
    expect(() => pending.transition(R05InstallStage.confirmed,
      evidence: const R05AndroidEvidence(packageName: 'com.other',
        exactAttemptMatches: true, versionCode: 123)), throwsStateError);
    expect(() => pending.transition(R05InstallStage.confirmed,
      evidence: const R05AndroidEvidence(packageName: 'com.example.app',
        exactAttemptMatches: true, versionCode: 124)), throwsStateError);
  });
  test('verified exact package and source release can confirm', () {
    final done = begin().transition(R05InstallStage.confirmed,
      now: DateTime.utc(2026, 11, 16, 0, 1),
      evidence: const R05AndroidEvidence(packageName: 'com.example.app',
        exactAttemptMatches: true, versionCode: 123, installedSignerSha256: digest,
        attemptId: 'r05_12345678_123456789abcdef0', installedApkSha256: [digest], installedSignerSet: [digest]));
    expect(done.stage, R05InstallStage.confirmed);
    expect(done.verifiedUtc, isNotNull);
    expect(done.installedSignerSha256, digest);
    expect(() => done.transition(R05InstallStage.unknown), throwsStateError);
  });
  test('known APK signer requires matching installed signer to confirm', () {
    final signed = R05OperationReceipt.start(
      id: 'r05_signed_123456789abcdef0', listingKey: 'store:package',
      packageId: 'com.example.app', backend: 'system', kind: 'apk',
      fileNames: <String>['base.apk'], expectedVersionCode: 123,
      archiveSignerSha256: digest, selectedApkSha256: [digest], archiveSignerSet: [digest], now: DateTime.utc(2026, 11, 16),
    );
    expect(() => signed.transition(R05InstallStage.confirmed,
      evidence: const R05AndroidEvidence(packageName: 'com.example.app',
        exactAttemptMatches: true, versionCode: 123)), throwsStateError);
    expect(() => signed.transition(R05InstallStage.confirmed,
      evidence: const R05AndroidEvidence(packageName: 'com.example.app',
        exactAttemptMatches: true, versionCode: 123,
        attemptId: 'r05_signed_123456789abcdef0', installedApkSha256: [digest],
        installedSignerSet: ['bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'],
        installedSignerSha256: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb')),
      throwsStateError);
    final result = signed.transition(R05InstallStage.confirmed,
      evidence: const R05AndroidEvidence(packageName: 'com.example.app',
        exactAttemptMatches: true, versionCode: 123, installedSignerSha256: digest,
        attemptId: 'r05_signed_123456789abcdef0', installedApkSha256: [digest], installedSignerSet: [digest]));
    expect(result.stage, R05InstallStage.confirmed);
  });

  test('same-version substituted bytes, stale attempt and unknown signers cannot confirm', () {
    final pending = begin();
    for (final evidence in [
      const R05AndroidEvidence(packageName: 'com.example.app', exactAttemptMatches: true,
        attemptId: 'r05_12345678_123456789abcdef0', versionCode: 123,
        installedApkSha256: ['bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'],
        installedSignerSet: [digest]),
      const R05AndroidEvidence(packageName: 'com.example.app', exactAttemptMatches: true,
        attemptId: 'r05_older_123456789abcdef0', versionCode: 123,
        installedApkSha256: [digest], installedSignerSet: [digest]),
      const R05AndroidEvidence(packageName: 'com.example.app', exactAttemptMatches: true,
        attemptId: 'r05_12345678_123456789abcdef0', versionCode: 123, installedApkSha256: [digest]),
    ]) {
      expect(() => pending.transition(R05InstallStage.confirmed, evidence: evidence), throwsStateError);
    }
  });
  test('legacy confirmed receipt stays historical, never exact byte evidence', () {
    final legacy = begin().toJson()..remove('selectedApkSha256')..remove('archiveSignerSet');
    legacy['stage'] = 'confirmed'; legacy['verifiedUtc'] = legacy['updatedUtc'];
    expect(R05OperationReceipt.fromJson(legacy).exactBytesConfirmed, isFalse);
  });

  test('reject malformed JSON, signed URLs, unsafe filenames and forged timestamps', () {
    final good = begin();
    for (final change in <void Function(Map<String, dynamic>)>[
      (v) => v['sourceHost'] = 'https://github.com/?token=secret',
      (v) => v['fileNames'] = <String>['../secret.apk'],
      (v) => v['downloadSha256'] = 'f',
      (v) => v['schema'] = 2,
      (v) => v['stage'] = 'confirmed',
      (v) => v['commitSha'] = 'not-sha',
      (v) => v['unexpected'] = 'field',
      (v) => v['revision'] = -1,
      (v) => v['updatedUtc'] = '2000-01-01T00:00:00Z',
    ]) {
      final bad = Map<String, dynamic>.from(good.toJson());
      change(bad);
      expect(() => R05OperationReceipt.decode(jsonEncode(bad)), throwsFormatException);
    }
  });
}
