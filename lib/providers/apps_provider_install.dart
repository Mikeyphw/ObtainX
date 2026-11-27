import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:android_intent_plus/android_intent.dart';
import 'package:android_intent_plus/flag.dart';
import 'package:android_package_manager/android_package_manager.dart';
import 'package:device_info_plus/device_info_plus.dart';
import 'package:easy_localization/easy_localization.dart';
import 'package:flutter/foundation.dart' show kDebugMode, visibleForTesting;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_fgbg/flutter_fgbg.dart';
import 'package:obtainium/app_sources/fdroid.dart';
import 'package:obtainium/app_sources/fdroidrepo.dart';
import 'package:obtainium/app_sources/github.dart';
import 'package:obtainium/app_sources/izzyondroid.dart';
import 'package:obtainium/components/app_detail_widgets.dart';
import 'package:obtainium/custom_errors.dart';
import 'package:obtainium/installers/dhizuku_installer.dart';
import 'package:obtainium/installers/external_installer.dart';
import 'package:obtainium/installers/installer.dart';
import 'package:obtainium/installers/shizuku_installer.dart';
import 'package:obtainium/installers/stock_installer.dart';
import 'package:obtainium/main.dart';
import 'package:obtainium/providers/apps_provider.dart';
import 'package:obtainium/providers/installer_provider.dart';
import 'package:obtainium/providers/logs_provider.dart';
import 'package:obtainium/providers/notifications_provider.dart';
import 'package:obtainium/providers/settings_provider.dart';
import 'package:obtainium/providers/source_provider.dart';
import 'package:obtainium/providers/virustotal_provider.dart';
import 'package:obtainium/services/artifact_file_work.dart';
import 'package:obtainium/services/r04_actions_archive_integrity.dart';
import 'package:obtainium/services/r05_operation_receipt.dart';
import 'package:obtainium/services/r05_operation_journal.dart';
import 'package:obtainium/services/r07_operation_timeline.dart';
import 'package:obtainium/services/r07_process_owner.dart';
import 'package:obtainium/services/r07_journal_guard.dart';
import 'package:obtainium/services/r11_external_requests.dart';
import 'package:obtainium/services/r03_download_engine.dart' show R03HistoryBinding, R03DownloadRecord;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:obtainium/services/install_bundle_plan.dart';
import 'package:obtainium/services/r09_discovery.dart';
import 'package:obtainium/services/r09_artifact_inspection.dart';
import 'package:path_provider/path_provider.dart';
import 'package:obtainium/services/install_precommit_gate.dart';
import 'package:obtainium/services/r02f_p05_device_profile.dart';
import 'package:obtainium/services/verified_obb_delivery.dart';
import 'package:obtainium/theme/app_dialog_theme.dart';
import 'package:obtainium/widgets/app_toast.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:shared_storage/shared_storage.dart' as saf;

// NOTE: This provider extension is intentionally UX-coupled. Interactive calls
// use the app-level navigator for dialogs and receive an explicit interaction
// flag internally, so an async operation never retains a page BuildContext.

// Named constants for magic numbers and hardcoded values
const int _androidApiLevelR = 30;
// downloadProgress sentinels for the busy states the UI renders instead of a
// percentage: -1 "Installing", -2 "Scanning with VirusTotal", -3 "Flagged"
// (AppPage's download control reads all three; the list tile reads -1/-2).
const double _installingProgressSentinel = -1;
const double _scanningProgressSentinel = -2;
const double _flaggedProgressSentinel = -3;
// -4 "Installing", but for a third-party installer that accepted the APK without
// reporting a result. Rendered exactly like -1; kept distinct because it must not
// count as work in flight (see [AppsProviderInstall.areDownloadsRunning]).
const double _awaitingThirdPartyInstallSentinel = -4;
const double _recoveredNativeInstallSentinel = -5;
// How long that indicator survives without a confirming package broadcast. Purely
// cosmetic - the install is confirmed independently and never waits on this - so
// it only stops a dismissed installer from leaving the row spinning forever.
const Duration _awaitingThirdPartyInstallTimeout = Duration(seconds: 60);
const int _downloadCompleteProgress = 100;
const int _remainingStepsProgress = 90;

// A silent background install can't report completion synchronously — the
// platform install API's result never arrives while backgrounded (#896). The
// session still commits, so we poll (via waitForPackageInstall) for a short
// window to confirm the install actually landed.
const int _bgInstallConfirmAttempts = 20; // 20 × 500ms = 10 seconds

/// A package-change broadcast is not independent proof of this attempted
/// release. The exact listing/source snapshot, package ID and package metadata
/// must all match before the pending release is promoted to confirmed.
@visibleForTesting
bool p04PendingMatchesInstalledPackage(
  App app,
  InstallReleaseSnapshot? pending,
  PackageInfo installedInfo,
) =>
    pending != null &&
    pending.belongsTo(app) &&
    installedInfo.packageName == app.id &&
    pending.matchesPackage(installedInfo);

@visibleForTesting
bool isCleartextDownloadUrl(String url) {
  return Uri.tryParse(url)?.scheme.toLowerCase() == 'http';
}

@visibleForTesting
bool shouldRetryGitHubDownloadWithoutAuthorization({
  required AppSource source,
  required Map<String, String>? headers,
  required Object error,
}) {
  if (source is! GitHub ||
      headers?[HttpHeaders.authorizationHeader]?.isNotEmpty != true ||
      error is! ObtainiumError) {
    return false;
  }
  return error.data['statusCode'] == HttpStatus.unauthorized;
}

/// Processes completed downloads one at a time, in the order they finish.
/// Entries selected by [deferUntilEnd] still download concurrently but are not
/// processed until every other entry has completed. This keeps app installs
/// serialized while avoiding a wait for the slowest download, and lets a
/// self-update remain last so it cannot terminate the rest of the batch.
@visibleForTesting
Future<void> processDownloadResultsAsReady<T>({
  required List<({String id, Future<T> result})> downloads,
  required bool Function(String id) deferUntilEnd,
  required Future<void> Function(T result) process,
}) async {
  Future<void> processChain = Future<void>.value();

  Future<void> processWhenReady(
    ({String id, Future<T> result}) download,
  ) async {
    final T result = await download.result;
    final Completer<void> processed = Completer<void>();
    processChain = processChain.then((_) async {
      try {
        await process(result);
        processed.complete();
      } catch (error, stackTrace) {
        processed.completeError(error, stackTrace);
      }
    });
    await processed.future;
  }

  final deferredDownloads = downloads.where(
    (download) => deferUntilEnd(download.id),
  );
  await Future.wait(
    downloads
        .where((download) => !deferUntilEnd(download.id))
        .map(processWhenReady),
  );
  for (final download in deferredDownloads) {
    await process(await download.result);
  }
}

// Outcome of the pre-install VirusTotal gate (see _handleMalwareScanResult).
enum _MalwareScanGateDecision { proceed, declined, retryScan }

class _InstallResult {
  final String id;
  final bool willBeSilent;
  final DownloadedApk? downloadedFile;
  final DownloadedDir? downloadedDir;
  const _InstallResult({
    required this.id,
    required this.willBeSilent,
    this.downloadedFile,
    this.downloadedDir,
  });
}

/// MANUAL TEST HOOK - flip to `true` to force every VirusTotal scan to resolve
/// as `flagged` (fake detail/report URL, no network call), so the flagged
/// dialog/skip/notification paths can be exercised without a real API key or a
/// real flagged APK. Gated on [kDebugMode] as a safety net. Revert to `false`.
const bool debugForceFlaggedMalwareScan = false;

// ── Build-verification enforcement (reproducible builds + GitHub attestation) ──
// Pure predicates/messages that decide whether an install must be blocked
// because the source did not meet an enabled verification requirement. The
// status constants, reproducibleBuildStatusFromBool() and
// reproducibleBuildStatusForEnforcement() live in source_provider.

bool reproducibleBuildVerificationApplies(AppSource source) {
  return source is FDroid || source is FDroidRepo || source is IzzyOnDroid;
}

bool reproducibleBuildEnforcementApplies(App app, AppSource source) {
  return app.additionalSettings['enforceReproducibleBuilds'] == true &&
      reproducibleBuildVerificationApplies(source);
}

bool reproducibleBuildEnforcementBlocksInstall(App app, AppSource source) {
  return reproducibleBuildEnforcementApplies(app, source) &&
      reproducibleBuildStatusForEnforcement(app) !=
          reproducibleBuildStatusVerified;
}

String reproducibleBuildEnforcedBlockedMessage() {
  return tr('reproducibleBuildEnforcedButBlocked');
}

bool githubAttestationEnforcementBlocksInstall(
  App app,
  AppSource source,
  SettingsProvider settingsProvider,
) {
  return source is GitHub &&
      source.shouldEnforceAttestations(
        app.additionalSettings,
        settingsProvider,
      );
}

String githubAttestationEnforcedBlockedMessage(String? attestationStatus) {
  return tr(
    attestationStatus == githubAttestationStatusUnsupported
        ? 'gap01AttestationAbsent'
        : 'gap01AttestationBlocked',
  );
}

bool buildVerificationEnforcementBlocksInstall(
  App app,
  AppSource source,
  SettingsProvider settingsProvider,
) {
  return reproducibleBuildEnforcementBlocksInstall(app, source) ||
      githubAttestationEnforcementBlocksInstall(app, source, settingsProvider);
}

String buildVerificationEnforcedBlockedMessage(
  App app,
  AppSource source,
  SettingsProvider settingsProvider,
) {
  if (reproducibleBuildEnforcementBlocksInstall(app, source)) {
    return reproducibleBuildEnforcedBlockedMessage();
  }
  return githubAttestationEnforcedBlockedMessage(app.latestAttestationStatus);
}

/// Sanitizes a proposed display name for a saved APK copy (SAF createFile).
String sanitizeApkSaveDisplayName(String raw) {
  final name = raw.replaceAll(RegExp(r'[\\/:*?"<>|]'), '_').trim();
  if (name.isEmpty) {
    return 'download.apk';
  }
  return name;
}

/// Same label as the release asset (e.g. GitHub attachment filename) when
/// possible, for the user-facing saved-APK copy.
String storeFacingDownloadDisplayNameForApp(
  App app, {
  InstallReleaseSnapshot? release,
}) {
  if (release != null) {
    app = app.copyWith(
      apkUrls: [MapEntry(release.assetName, release.assetUrl)],
      preferredApkIndex: 0,
    );
  }
  if (app.apkUrls.isEmpty) {
    return 'download.apk';
  }
  final int preferredIdx =
      app.preferredApkIndex >= 0 && app.preferredApkIndex < app.apkUrls.length
      ? app.preferredApkIndex
      : 0;
  String key = app.apkUrls[preferredIdx].key.trim();
  if (key.isEmpty) {
    try {
      final Uri uri = Uri.parse(app.apkUrls[preferredIdx].value);
      if (uri.pathSegments.isNotEmpty) {
        key = uri.pathSegments.last;
      }
    } catch (_) {
      key = 'download.apk';
    }
  }
  if (key.isEmpty) {
    key = 'download.apk';
  }
  return sanitizeApkSaveDisplayName(key);
}

/// True when the stock Android installer is being asked to install a lower
/// version code. Other installers are not pre-checked: a third-party installer
/// may be able to downgrade, and Shizuku/Dhizuku get Android's own refusal.
bool isStockInstallerDowngrade({
  required int? installedVersionCode,
  required int? newVersionCode,
  required String installerModeKey,
}) {
  return installerModeKey == 'system' &&
      installedVersionCode != null &&
      newVersionCode != null &&
      newVersionCode < installedVersionCode;
}

/// Package ids of LSPosed modules that lift Android's version-downgrade block:
/// Let Me Downgrade, and CorePatch under its legacy and "Core Patch N" ids
/// (#327). They patch the system package manager itself (root + LSPosed), so an
/// install needs nothing from ObtainX beyond skipping its own downgrade check.
/// CorePatch's other bypasses (mismatched signatures, modified APKs) need not
/// even that: ObtainX never blocks those before handing the install to Android.
const List<String> downgradeModulePackageIds = [
  'com.berdik.letmedowngrade',
  'com.coderstory.toolkit',
  'org.lsposed.corepatch',
];

/// Whether any of [downgradeModulePackageIds] is installed. Only installation
/// is visible from here: a module that is installed but not enabled in LSPosed
/// still counts, and Android then rejects the downgrade itself.
Future<bool> isDowngradeModuleInstalled() async {
  final List<PackageInfo?> modules = await Future.wait(
    downgradeModulePackageIds.map(getInstalledInfo),
  );
  return modules.any((PackageInfo? info) => info != null);
}

/// Whether the installer in [installerModeKey] can put an older version over a
/// newer one. A third-party installer decides for itself (a root one such as
/// InstallerX can), so ObtainX lets it try. The stock installer, Shizuku and
/// Dhizuku never request a downgrade, so Android refuses one unless a
/// downgrade module is usable.
bool installerCanDowngrade({
  required String installerModeKey,
  required bool downgradeModuleUsable,
}) => installerModeKey == 'external' || downgradeModuleUsable;

/// App download, install, and on-device package operations for [AppsProvider].
// A review is a transient selection, not a new installed-state authority.
final _r09Selections = Expando<Map<String, R09ReviewBinding>>('r09-reviewed-selection');

String _r09ReleaseKey(App app) => jsonEncode([
  app.listingKey, app.id, downloadReleaseCacheKey(InstallReleaseSnapshot.fromApp(app)),
  app.allowIdChange, app.settings.getStringOrNull('zippedApkFilterRegEx'),
  app.settings.getStringOrNull('tarballedApkFilterRegEx'),
  app.additionalSettings['r04ActionsArchiveEvidence'],
]);

extension AppsProviderInstall on AppsProvider {
  /// R05 journal is the single durable state authority; Android/release
  /// reconciliation remains independent and cannot be replaced by a timer.
  Future<String> _ensureInstallTimeline(String listingKey, File original,
      R05DownloadProvenance? provenance, String? existing) async {
    final app = apps[listingKey]?.app;
    if (!apps.containsListingKey(listingKey) || app == null || app.listingKey != listingKey) {
      throw StateError('Exact tracked installation listing is missing');
    }
    final channel = r11ChannelFingerprint(app);
    if (provenance != null && (provenance.channelFingerprint != channel ||
        provenance.releaseFingerprint != downloadReleaseCacheKey(InstallReleaseSnapshot.fromApp(app)))) {
      throw StateError('Install source or release changed after download');
    }
    final release = provenance?.releaseFingerprint ??
        r07JournalFingerprint('local-install:${await sha256FileOffIsolate(original.path)}');
    final timeline = R07OperationTimeline.instance;
    if (existing != null) {
      final prior = await timeline.read(existing);
      if (const {'install', 'localArchive'}.contains(prior.intent.kind)) {
        await timeline.validateInstallBinding(existing, listingKey: listingKey,
          packageId: app.id, channel: channel, release: release);
        return existing;
      }
      if (prior.stage != 'downloadReady' || prior.intent.release != release ||
          prior.intent.channel != channel ||
          (prior.resolvedListingKey ?? prior.intent.listingKey) != listingKey ||
          (prior.resolvedPackageId ?? prior.intent.packageId) != app.id) {
        throw StateError('Historical download does not belong to this reviewed installation');
      }
    }
    // Local files have their own domain-separated byte identity; this does
    // not grant remote-release provenance or historical source retry rights.
    final entry = await timeline.beginPreparation(R07OperationIntent(kind: 'install',
      listingKey: listingKey, packageId: app.id, channel: channel, release: release,
      parentId: existing));
    return entry.id;
  }

  Future<R05OperationReceipt> _r05BeginAttempt(
    String listingKey, File primary, PackageInfo packageInfo, {
    required String kind,
    List<File> selected = const <File>[],
    InstallReleaseSnapshot? release,
    R05DownloadProvenance? provenance,
    File? container,
    InstallBundlePlan? plan,
    String? timelineId,
  }) async {
    final app = apps[listingKey]?.app;
    if (app == null || app.listingKey != listingKey || packageInfo.packageName != app.id || packageInfo.versionCode == null ||
        (release != null && !release.belongsTo(app))) {
      throw StateError('Exact tracked release identity is missing');
    }
    if (provenance != null && (release == null ||
        provenance.releaseFingerprint != downloadReleaseCacheKey(release) ||
        provenance.channelFingerprint != r11ChannelFingerprint(app))) {
      throw StateError('Download provenance does not belong to this release');
    }
    if (release != null && app.additionalSettings[GitHub.r04SourceModeKey] == GitHub.r04ModeActions &&
        (provenance == null || provenance.artifactId == null)) {
      throw StateError('Actions installation requires original archive provenance');
    }
    final digest = await sha256FileOffIsolate(primary.path);
    final hashes = [digest, ...await Future.wait(selected.map((f) => sha256FileOffIsolate(f.path)))];
    if (plan == null || plan.selectedMembers.length != hashes.length ||
        plan.packageName != app.id || plan.versionCode != packageInfo.versionCode) {
      throw StateError('Missing manifest-bound APK selection');
    }
    final plannedMembers = plan.selectedMembers;
    final signers = plannedMembers.first.signers.toSet().toList()..sort();
    if (signers.isEmpty) throw StateError('Current APK signing evidence unavailable');
    for (var i = 0; i < hashes.length; i++) {
      if (plannedMembers[i].sha256 != hashes[i]) {
        throw StateError('Planned APK bytes changed');
      }
      final memberSigners = plannedMembers[i].signers.toSet();
      if (memberSigners.length != signers.length || !memberSigners.containsAll(signers)) {
        throw StateError('Selected APK signer evidence missing or mismatched');
      }
    }
    final containerDigest = container == null ? null : await sha256FileOffIsolate(container.path);
    if (provenance != null && provenance.archiveSha256 != (containerDigest ?? digest)) {
      throw StateError('Downloaded artifact bytes no longer match provenance');
    }
    final intentId = timelineId ?? provenance?.timelineId;
    final intentRelease = provenance?.releaseFingerprint ??
        r07JournalFingerprint('local-install:${containerDigest ?? digest}');
    if (intentId != null) {
      await R07OperationTimeline.instance.validateInstallBinding(intentId,
        listingKey: listingKey, packageId: app.id, channel: r11ChannelFingerprint(app),
        release: intentRelease);
    }
    final receipt = await R05OperationJournal.instance.begin(
      listingKey: listingKey, packageId: app.id,
      backend: getInstaller().modeKey, kind: kind,
      fileNames: <String>[primary.uri.pathSegments.last,
        ...selected.map((f) => f.uri.pathSegments.last)],
      channelFingerprint: r11ChannelFingerprint(app),
      sourceHost: provenance?.sourceHost,
      workflowId: provenance?.workflowId, sourceRepository: provenance?.repository,
      sourceBranch: provenance?.branch, finalOrigin: provenance?.finalOrigin,
      runId: provenance?.runId, runAttempt: provenance?.runAttempt,
      artifactId: provenance?.artifactId, commitSha: provenance?.commitSha,
      downloadSha256: digest,
      archiveSignerSha256: signers.first,
      selectedApkSha256: hashes, archiveSignerSet: signers,
      releaseFingerprint: provenance?.releaseFingerprint,
      parentAttemptId: provenance?.parentAttemptId,
      containerSha256: containerDigest,
      expectedVersionCode: packageInfo.versionCode,
      timelineId: intentId,
      processOwner: (await R07ProcessOwner.capture()).encode(),
    );
    if (intentId != null) {
      try {
        await R07OperationTimeline.instance.linkAttempt(intentId, receipt.id,
          listingKey: listingKey, packageId: app.id,
          channel: r11ChannelFingerprint(app), release: intentRelease);
      } catch (_) {
        // No Android mutation has occurred. Do not leave a fresh receipt
        // falsely owning a handoff which was refused by the timeline.
        try {
          await R05OperationJournal.instance.settleIfOpen(receipt.id,
            R05InstallStage.failed, reason: 'Operation timeline binding refused before handoff');
        } catch (_) { /* preserve the primary binding refusal */ }
        rethrow;
      }
    }
    return receipt;
  }

  bool _r05ListingStillBound(R05OperationReceipt attempt) {
    final app = apps[attempt.listingKey]?.app;
    return app != null && app.id == attempt.packageId &&
        app.listingKey == attempt.listingKey &&
        r11ChannelFingerprint(app) == attempt.channelFingerprint &&
        (attempt.releaseFingerprint == null ||
            downloadReleaseCacheKey(InstallReleaseSnapshot.fromApp(app)) == attempt.releaseFingerprint);
  }

  /// Persist an exact confirmation only while the original listing remains
  /// current. A refresh or replacement during the queued save is conservative:
  /// the historical receipt stays confirmed, but cannot update another listing.
  Future<void> _r05PersistBoundConfirmation(R05OperationReceipt attempt,
      InstallReleaseSnapshot? release, PackageInfo info) async {
    final current = apps[attempt.listingKey]?.app;
    if (current == null || !_r05ListingStillBound(attempt)) return;
    await saveApps([recordConfirmedInstall(current, release, info)],
        attemptToCorrectInstallStatus: false,
        commitGuard: () => identical(apps[attempt.listingKey]?.app, current) &&
            _r05ListingStillBound(attempt));
  }

  Future<void> _r05CheckHandoff(R05OperationReceipt attempt, List<String> paths,
      {File? container}) async {
    if (getInstaller().modeKey != attempt.backend ||
        paths.length != attempt.selectedApkSha256.length) {
      throw StateError('Approved APK plan or backend changed');
    }
    for (var i = 0; i < paths.length; i++) {
      if (await FileSystemEntity.type(paths[i], followLinks: false) != FileSystemEntityType.file ||
          await sha256FileOffIsolate(paths[i]) != attempt.selectedApkSha256[i]) {
        throw StateError('Approved APK bytes changed before handoff');
      }
    }
    if (attempt.containerSha256 != null && (container == null ||
        await sha256FileOffIsolate(container.path) != attempt.containerSha256)) {
      throw StateError('Approved archive bytes changed before handoff');
    }
    // Recheck after asynchronous hashing and immediately before dispatch.
    if (!_r05ListingStillBound(attempt) || getInstaller().modeKey != attempt.backend) {
      throw StateError('Approved listing, release or backend changed');
    }
  }

  // Only a result returned to this specific native invocation may enter this
  // confirmation path. A generic package broadcast never supplies its identity.
  Future<R05AndroidEvidence?> _r05ObserveInstalled(R05OperationReceipt attempt) async {
    try {
      const bridge = MethodChannel('dev.imranr.obtainium/r02_local_archive');
      final raw = await bridge.invokeMapMethod<String, dynamic>('installedEvidence',
        {'package': attempt.packageId});
      if (raw == null || raw['package'] != attempt.packageId || raw['version'] is! int ||
          raw['hashes'] is! List || raw['signers'] is! List) {
        return null;
      }
      final hashes = List<String>.from(raw['hashes'] as List);
      final signers = List<String>.from(raw['signers'] as List);
      if (signers.isEmpty || hashes.isEmpty) return null;
      return R05AndroidEvidence(packageName: attempt.packageId,
        exactAttemptMatches: true, attemptId: attempt.id, versionCode: raw['version'] as int,
        installedSignerSha256: signers.first, installedApkSha256: hashes, installedSignerSet: signers);
    } catch (_) {
      // No platform bridge/visibility or unreadable installed bytes: unknown.
      return null;
    }
  }

  Future<bool> _r05CloseAttempt(
    R05OperationReceipt attempt, InstallResult result,
    InstallReleaseSnapshot? expectedRelease,
  ) async {
    final journal = R05OperationJournal.instance;
    if (result.isError) {
      await journal.settleIfOpen(attempt.id, R05InstallStage.failed,
          androidCode: result.errorCode, reason: 'Android installer reported an error');
    } else if (result.isCancelled) {
      await journal.settleIfOpen(attempt.id, R05InstallStage.cancelled,
          reason: 'Installer explicitly cancelled');
    } else if (result.isHandedOff) {
      await journal.settleIfOpen(attempt.id, R05InstallStage.handedOff,
          reason: 'External or native handoff; confirmation remains pending');
    } else if (result.isAlreadyInstalled) {
      await journal.settleIfOpen(attempt.id, R05InstallStage.unknown,
          reason: 'Android reported already installed or pending; not proof of this attempt');
    } else if (result.isSuccess) {
      final observed = await getInstalledInfo(attempt.packageId);
      final evidence = await _r05ObserveInstalled(attempt);
      final entry = apps[attempt.listingKey];
      if (entry != null && entry.app.id == attempt.packageId && observed != null &&
          (expectedRelease == null || p04PendingMatchesInstalledPackage(entry.app, expectedRelease, observed)) &&
          evidence != null) {
        try {
          final settled = await journal.settleIfOpen(attempt.id, R05InstallStage.confirmed, evidence: evidence);
          if (settled.exactBytesConfirmed) {
            // Historical evidence belongs to the original attempt; do not
            // advance a replacement listing or release after an await.
            return _r05ListingStillBound(attempt);
          }
        } on StateError {
          // Matching package/version alone cannot override a digest mismatch.
        }
      }
      await journal.settleIfOpen(attempt.id, R05InstallStage.unknown,
          reason: 'Matching attempt-bound Android byte proof is missing');
    }
    try {
      final latest = (await journal.list()).firstWhere((x) => x.id == attempt.id);
      if (latest.stage == R05InstallStage.failed ||
          latest.stage == R05InstallStage.handedOff || latest.stage == R05InstallStage.unknown) {
        await NotificationsProvider().notifyR07Attention(attemptId: latest.id,
          packageId: latest.packageId, stage: latest.stage.name);
      }
    } catch (_) {
      // Notification failure never changes the journal decision.
    }
    return false;
  }

  Future<bool> _r05AdditionalApproval(R05OperationReceipt receipt,
      {required bool interactive}) async {
    final prefs = await SharedPreferences.getInstance();
    if (prefs.getBool(r05ExtraApprovalPreference) != true) return true;
    await R05OperationJournal.instance.settleIfOpen(
        receipt.id, R05InstallStage.awaitingApproval,
        reason: 'Optional extra approval required');
    try {
      await NotificationsProvider().notifyR07Attention(
        attemptId: receipt.id, packageId: receipt.packageId,
        stage: R05InstallStage.awaitingApproval.name);
    } catch (_) {
      // The optional notification does not affect the durable approval gate.
    }
    final navigator = globalNavigatorKey.currentState;
    if (!interactive || navigator == null || !navigator.mounted) {
      // Preserve the file and review entry; no silent approval.
      return false;
    }
    final accepted = await showDialog<bool>(
      context: navigator.context, barrierDismissible: false,
      builder: (dialog) => AlertDialog(
        title: const Text('Review installation'),
        content: Text('Package: ${receipt.packageId}\n'
            'Installer: ${receipt.backend}\n'
            'Files: ${receipt.fileNames.length}\n'
            'This optional approval does not replace Android security confirmation.'),
        actions: <Widget>[
          TextButton(onPressed: () => Navigator.pop(dialog, false),
              child: const Text('Not now')),
          FilledButton(onPressed: () => Navigator.pop(dialog, true),
              child: const Text('Continue to Android')),
        ],
      ),
    );
    if (accepted != true) {
      await R05OperationJournal.instance.settleIfOpen(
        receipt.id, R05InstallStage.cancelled,
        reason: 'User declined additional approval');
      return false;
    }
    return true;
  }

  /// Read-only package reconciliation for the R05 review screen. A package
  /// broadcast without exact tracked release evidence never confirms.
  Future<void> reconcileR05OperationReceipts() async {
    // A process restart cannot recreate the invocation that produced a native
    // result. Preserve unknown/handed-off evidence without attributing a
    // generic package observation to a particular receipt.
    await R05OperationJournal.instance.recoverInterruptedOnce();
  }

  Future<void> _r05MarkUnknownIfStillPending(String attemptId, String reason) async {
    await R05OperationJournal.instance.settleIfOpen(attemptId,
        R05InstallStage.unknown, reason: reason);
  }

  /// Owns and observes the background future even when Android does not
  /// complete its method-channel reply while this Activity is backgrounded.
  Future<void> _r05TrackBackgroundInstall(String listingKey, Future<bool> operation) async {
    try {
      await operation;
    } catch (error) {
      try {
        // This wrapper has no attempt identity. The invocation owns settlement.
        await logs.add('R05 background install failed for $listingKey: ${error.runtimeType}',
            level: LogLevel.warning);
      } catch (_) {
        // The journal itself failed; keep the original operation error in logs.
        try {
          await logs.add('R05 journal unavailable for background install',
              level: LogLevel.error);
        } catch (_) {}
      }
    }
  }


  /// Listen for package changes as observations only. An external installer
  /// does not return attempt-bound Android evidence, so a package broadcast
  /// cannot confirm an operation or promote a source release receipt.
  void listenForThirdPartyInstallResults() =>
      registerThirdPartyInstallPackageChangedCallback(
        recordThirdPartyInstallBroadcast,
      );

  void stopListeningForThirdPartyInstallResults() =>
      registerThirdPartyInstallPackageChangedCallback(null);

  /// Shows the installing indicator for an app whose APK a third-party installer
  /// accepted without reporting a result, until [recordThirdPartyInstallBroadcast]
  /// confirms it or [_awaitingThirdPartyInstallTimeout] elapses.
  void _awaitThirdPartyInstallConfirmation(R05OperationReceipt attempt) {
    final appId = attempt.listingKey;
    if (!_r05ListingStillBound(attempt)) return;
    thirdPartyInstallIndicatorTimers.remove(appId)?.cancel();
    final entry = apps[appId];
    if (entry == null) return;
    entry.downloadProgress = _awaitingThirdPartyInstallSentinel;
    thirdPartyInstallIndicatorTimers[appId] = Timer(
      _awaitingThirdPartyInstallTimeout,
      () {
        thirdPartyInstallIndicatorTimers.remove(appId);
        unawaited(_r05MarkUnknownIfStillPending(attempt.id,
            'External installer did not provide independent confirmation')
            .catchError((Object error) async {
              await logs.add('R05 receipt timeout could not be persisted: ${error.runtimeType}',
                level: LogLevel.error);
            }));
        final timedOutEntry = apps[appId];
        if (_r05ListingStillBound(attempt) && timedOutEntry?.downloadProgress ==
            _awaitingThirdPartyInstallSentinel) {
          timedOutEntry!.downloadProgress = null;
        }
        notify();
      },
    );
    notify();
  }

  /// Clears the awaiting-third-party indicator for [appId] on the user's say-so.
  /// ObtainX cannot tell a background install from a dismissed installer, so the
  /// indicator is offered as dismissible rather than left to run out its timer on
  /// a row where nothing is happening. The install itself is untouched: if it is
  /// still running, [recordThirdPartyInstallBroadcast] records it either way.
  void dismissThirdPartyInstallIndicator(String appId) {
    thirdPartyInstallIndicatorTimers.remove(appId)?.cancel();
    final entry = apps[appId];
    if (entry?.downloadProgress != _awaitingThirdPartyInstallSentinel) return;
    entry!.downloadProgress = null;
    notify();
  }

  /// Whether [appId] is showing the awaiting-third-party indicator.
  bool isAwaitingThirdPartyInstall(String appId) =>
      apps[appId]?.downloadProgress == _awaitingThirdPartyInstallSentinel;

  /// See [listenForThirdPartyInstallResults].
  Future<void> recordThirdPartyInstallBroadcast(String packageName) async {
    // A package may have multiple tracked source listings. A broadcast has
    // package scope, not listing scope; confirm only each listing's *own*
    // attempted release, never a different listing's pending intent.
    final listingKeys = apps.values
        .where((entry) => entry.app.id == packageName)
        .map((entry) => entry.listingKey)
        .toList(growable: false);
    if (listingKeys.isEmpty) return;
    final installedInfo = await getInstalledInfo(packageName);
    if (installedInfo == null || installedInfo.packageName != packageName) {
      return;
    }
    for (final listingKey in listingKeys) {
      final entry = apps[listingKey];
      if (entry == null || entry.app.id != packageName) continue;
      final pending = InstallReleaseSnapshot.fromJson(
        entry.app.additionalSettings[pendingInstallReleaseKey],
      );
      // A package broadcast cannot identify the originating operation. Keep
      // pending evidence and report the device state separately.
      if (pending != null) continue;
      final corrected = getCorrectedInstallStatusAppIfPossible(entry.app, installedInfo);
      if (corrected != null) {
        entry.app = corrected;
        await saveApps([entry.app], attemptToCorrectInstallStatus: false);
      }
    }
  }

  Future<void> _recordPendingInstall(
    String appId,
    InstallReleaseSnapshot? release,
  ) async {
    final entry = apps[appId];
    if (entry == null || release == null || !release.belongsTo(entry.app)) {
      return;
    }
    entry.app = recordPendingInstall(entry.app, release);
    await saveApps([entry.app], attemptToCorrectInstallStatus: false);
  }

  Future<void> _clearPendingInstall(
    String appId,
    InstallReleaseSnapshot? release,
  ) async {
    final entry = apps[appId];
    if (entry == null || release == null) return;
    final corrected = discardPendingInstall(entry.app, release);
    if (identical(corrected, entry.app)) return;
    entry.app = corrected;
    await saveApps([entry.app], attemptToCorrectInstallStatus: false);
  }

  /// Returns the [Installer] strategy for the current installer mode setting.
  Installer getInstaller() {
    switch (settingsProvider.installerMode) {
      case 'shizuku':
        return ShizukuInstaller(settingsProvider);
      case 'dhizuku':
        return DhizukuInstaller(settingsProvider);
      // Third-party installer. Value matches upstream Obtainium's
      // InstallerMode.external.name.
      case 'external':
        return ExternalInstaller(settingsProvider);
      default:
        return StockInstaller(settingsProvider);
    }
  }

  Future<void> _rememberBlockingAttention(
    String listingKey,
    String code, {
    String? detail,
  }) async {
    final AppInMemory? listing = apps[listingKey];
    if (listing == null) return;
    final Map<String, dynamic> settings = Map<String, dynamic>.from(
      listing.app.additionalSettings,
    );
    setNeedsAttention(settings, code, detail: detail);
    listing.app = listing.app.copyWith(additionalSettings: settings);
    await saveApps(
      [listing.app],
      attemptToCorrectInstallStatus: false,
      updateInstalledInfo: false,
    );
  }

  /// Whether [app]'s current release already failed a pre-install check that
  /// fails the same way every time, with that check still on. Background runs
  /// leave such an app in Needs attention rather than download the release
  /// again just to fail again; an update started by hand still runs the check.
  @visibleForTesting
  bool verificationWouldBlockAgain(App app) {
    if (!appHasBlockingAttention(app)) return false;
    AppSource source() =>
        SourceProvider().getSource(app.url, overrideSource: app.overrideSource);
    return switch (app.additionalSettings[needsAttentionCodeKey]) {
      needsAttentionMalwareFlagged => willScanApkWithVirusTotal(app),
      needsAttentionNotReproducible =>
        reproducibleBuildEnforcementBlocksInstall(app, source()),
      needsAttentionNoAttestation => githubAttestationEnforcementBlocksInstall(
        app,
        source(),
        settingsProvider,
      ),
      _ => false,
    };
  }

  Future<Never> _throwRecordedInstallError(
    String listingKey,
    int errorCode,
  ) async {
    // Matched on the status code: the message is the enum's name
    // ('failureIncompatible'), which a search for 'INCOMPATIBLE' never found.
    final String? attentionCode = installFailureNeedsAttentionCode(errorCode);
    if (attentionCode != null) {
      await _rememberBlockingAttention(listingKey, attentionCode);
    }
    throw InstallError(errorCode);
  }

  /// Returns the renamed file and the resolved app; callers must use the
  /// returned app's ID since [App] is immutable.
  Future<(File, App)> handleAPKIDChange(
    App app,
    PackageInfo newInfo,
    File downloadedFile,
    String downloadUrl,
  ) async {
    // If the APK package ID is different from the App ID, it is either new (using a placeholder ID) or the ID has changed
    // The former case should be handled (give the App its real ID), the latter is a security issue
    final isTempIdBool = isTempId(app);
    final actualPackageName = newInfo.packageName;
    if (app.id != actualPackageName) {
      if (actualPackageName == null) {
        throw ObtainiumError(tr('couldNotGetIdFromApk'))..url = app.url;
      }
      if (apps[app.listingKey] != null && !isTempIdBool && !app.allowIdChange) {
        await _rememberBlockingAttention(
          app.listingKey,
          needsAttentionIdChanged,
          detail: actualPackageName,
        );
        throw IDChangedError(actualPackageName)..url = app.url;
      }
      final idChangeWasAllowed = app.allowIdChange;
      final originalListingKey = app.listingKey;
      app = app.copyWith(id: actualPackageName, allowIdChange: false);
      downloadedFile = downloadedFile.renameSync(
        '${downloadedFile.parent.path}/${app.listingKey}-${downloadReleaseCacheKey(InstallReleaseSnapshot.fromApp(app))}.${downloadedFile.path.split('.').last}',
      );
      if (apps[originalListingKey] != null) {
        await removeApps([originalListingKey]);
        await saveApps([
          app,
        ], onlyIfExists: !isTempIdBool && !idChangeWasAllowed);
      }
    }
    return (downloadedFile, app);
  }

  Future<void> updatePendingRepoRename(String appId, String? newUrl) async {
    final AppInMemory? listing = apps[appId];
    if (listing == null) return;
    listing.app = listing.app.copyWith(pendingRepoRenameUrl: newUrl);
    await saveApps([listing.app]);
  }

  /// Applies a detected repository rename: adopts [newUrl] and clears the
  /// pending-rename flag so update checks resume.
  Future<void> acceptRepoRename(String appId, String newUrl) async {
    final AppInMemory? listing = apps[appId];
    if (listing == null) return;
    listing.app = listing.app.copyWith(url: newUrl, pendingRepoRenameUrl: null);
    await saveApps([listing.app]);
  }

  Future<List<File>> _archiveApkCandidates(Directory directory, App app, bool isTarball) async {
    // Nested containers must not be mistaken for installable APKs.
    final apks = directory
        .listSync(recursive: true, followLinks: false)
        .whereType<File>()
        .where((file) => file.path.toLowerCase().endsWith('.apk'))
        .toList();

    String? filterRegEx;
    if (isTarball &&
        app.settings
                .getStringOrNull('tarballedApkFilterRegEx')
                ?.isNotEmpty ==
            true) {
      filterRegEx = app.settings.getStringOrNull('tarballedApkFilterRegEx');
    } else if (!isTarball &&
        app.settings.getStringOrNull('zippedApkFilterRegEx')?.isNotEmpty ==
            true) {
      filterRegEx = app.settings.getStringOrNull('zippedApkFilterRegEx');
    }
    if (filterRegEx != null) {
      final originalSplits = <String>{};
      for (final file in apks) {
        final facts = await inspectInstallApkMember(file);
        if (facts.splitName != null) originalSplits.add(file.path);
      }
      final reg = RegExp(filterRegEx);
      apks.removeWhere((apk) {
        final relativePath = apk.path.substring(directory.path.length + 1);
        return !reg.hasMatch(relativePath);
      });
      // Do not allow a regex to silently strip required config splits.
      final retained = apks.map((file) => file.path).toSet();
      if (originalSplits.difference(retained).isNotEmpty) {
        throw const FormatException(
          'Archive APK filter excludes required split configurations',
        );
      }
    }
    return apks;
  }

  /// Inspect only an explicitly requested candidate. Private review staging is
  /// discarded on success, refusal or cancellation, with no listing mutation,
  /// installer session, background notification, or persistent download entry.
  Future<R09ArtifactInspection> _inspectR09Candidate(App app,
      MapEntry<String, String> asset, CancellationToken token,
      void Function(double?, int?, int?) progress) async {
    token.throwIfCancelled();
    final exactAssets = app.apkUrls.where((item) => item.key == asset.key && item.value == asset.value).toList();
    if (exactAssets.length != 1 || !r09ActionsEligible(asset, app.additionalSettings, app.url, DateTime.now())) {
      throw const FormatException('Candidate identity changed');
    }
    final releaseKey = _r09ReleaseKey(app.copyWith(preferredApkIndex: app.apkUrls.indexWhere(
      (item) => item.key == asset.key && item.value == asset.value)));
    final source = SourceProvider().getSource(app.url, overrideSource: app.overrideSource);
    final mergedSettings = await source.buildMergedSettings(app.additionalSettings, settingsProvider);
    final url = await source.assetUrlPrefetchModifier(
      await source.generalReqPrefetchModifier(asset.value, mergedSettings), app.url, mergedSettings);
    final uri = Uri.parse(url);
    // Review does not create an exception to verified HTTPS transport policy.
    if (uri.scheme != 'https' || uri.host.isEmpty || uri.userInfo.isNotEmpty) {
      throw const FormatException('Review requires HTTPS');
    }
    final headers = await source.getAssetRequestHeaders(app.additionalSettings, app.url, url);
    final cache = await getTemporaryDirectory();
    final stage = await cache.createTemp('r09-review-');
    try {
      token.throwIfCancelled();
      final advertised = installArtifactFormat(asset.key);
      final fileName = advertised == null ? 'candidate' :
          'candidate.${asset.key.toLowerCase().endsWith('.tar.gz') ? 'tar.gz' : asset.key.split('.').last}';
      Future<File> fetch(Map<String, String>? requestHeaders) => downloadFile(url, fileName,
        advertised != null, progress, stage.path, useExisting: false, headers: requestHeaders,
        allowInsecure: false, cancellationToken: token, maxBytes: r09InspectionMaxBytes,
        privateJournalDirectory: Directory('${stage.path}/journal'), reviewHttpsOnly: true,
        expectedSha256: sourceAssetSha256(app, asset));
      File artifact;
      try {
        artifact = await fetch(headers);
      } catch (error) {
        if (app.additionalSettings[GitHub.r04SourceModeKey] == GitHub.r04ModeActions ||
            !shouldRetryGitHubDownloadWithoutAuthorization(source: source, headers: headers, error: error)) {
          rethrow;
        }
        artifact = await fetch(Map<String, String>.from(headers!)..remove(HttpHeaders.authorizationHeader));
      }
      token.throwIfCancelled();
      await verifyR04ActionsArchiveBeforeExtraction(archive: artifact,
        additionalSettings: app.additionalSettings, sourceUrl: app.url,
        selectedAssetUrl: asset.value, selectedAssetName: asset.key);
      final artifactDigest = await sha256FileOffIsolate(artifact.path);
      final bytes = await artifact.length();
      final format = advertised ?? installArtifactFormat(artifact.path);
      if (format == null) throw const FormatException('Unsupported APK artifact');
      final members = <R09ApkFacts>[];
      var excludedApks = false;
      final obbs = <String>[];
      if (format == InstallArtifactFormat.apk) {
        members.add(await inspectR09Apk(artifact, asset.key));
      } else {
        final extracted = Directory('${stage.path}/extracted');
        if (format == InstallArtifactFormat.tarball) {
          await extractTarballOffIsolate(artifact.path, extracted.path, limits: r09InspectionLimits, checkCancellation: token.throwIfCancelled);
        } else {
          await extractZipOffIsolate(artifact.path, extracted.path, limits: r09InspectionLimits, checkCancellation: token.throwIfCancelled);
        }
        token.throwIfCancelled();
        final allApks = extracted.listSync(recursive: true, followLinks: false).whereType<File>()
            .where((file) => file.path.toLowerCase().endsWith('.apk')).toList();
        if (allApks.isEmpty || allApks.length > r09InspectionMaxApks) {
          throw const FormatException('Review APK inventory limit');
        }
        final candidates = await _archiveApkCandidates(extracted, app, format == InstallArtifactFormat.tarball);
        excludedApks = candidates.length != allApks.length;
        // The installer independently inventories the entire extracted tree.
        // Do not overstate compatibility where a download filter hides files.
        allApks.sort((a, b) => a.path.compareTo(b.path));
        for (final file in allApks) {
          token.throwIfCancelled();
          members.add(await inspectR09Apk(file, file.path.substring(extracted.path.length + 1)));
        }
        obbs.addAll(extracted.listSync(recursive: true, followLinks: false).whereType<File>()
            .where((file) => file.path.toLowerCase().endsWith('.obb')).map((file) => file.path));
      }
      token.throwIfCancelled();
      final device = await DeviceInfoPlugin().androidInfo;
      final dispatcher = WidgetsBinding.instance.platformDispatcher;
      final locales = dispatcher.locales.map((locale) => locale.toLanguageTag()).toList();
      final density = dispatcher.views.isEmpty ? null : (dispatcher.views.first.devicePixelRatio * 160).round();
      validateP05DeviceProfile(sdk: device.version.sdkInt, supportedAbis: device.supportedAbis,
          locales: locales, densityDpi: density);
      final bases = members.where((member) => member.split == null).toList();
      List<String> installedSigners = const [];
      var installedObserved = false;
      int? installedVersionCode;
      String? installedVersionName;
      if (bases.length == 1) {
        try {
          final installed = await getInstalledInfo(bases.single.packageName, light: false, printErr: false, throwOnError: true);
          installedObserved = installed != null;
          installedVersionCode = installed?.versionCode;
          installedVersionName = installed?.versionName;
          installedSigners = certificateHashesFromSignatures(installed?.signingInfo?.apkContentSigners ?? const <List<int>>[])
              .map((value) => value.replaceAll(':', '').toLowerCase()).toList();
        } catch (_) {
          // Unknown installed state is not the same as a proven absent package.
          installedObserved = true;
        }
      }
      final review = reviewR09Artifact(artifactSha256: artifactDigest, bytes: bytes,
        members: members, format: format, supportedAbis: device.supportedAbis,
        sdk: device.version.sdkInt, locales: locales, density: density,
        expectedPackage: isTempId(app) || app.allowIdChange ? null : app.id,
        installedSigners: installedSigners, installedPackageObserved: installedObserved,
        installedVersionCode: installedVersionCode, installedVersionName: installedVersionName,
        actionsDigestVerified: app.additionalSettings[GitHub.r04SourceModeKey] == GitHub.r04ModeActions);
      final extraRefusals = <String>[];
      if (excludedApks) extraRefusals.add('r09ReviewFilteredInventory');
      if (obbs.isNotEmpty && bases.length == 1) {
        try {
          validateObbFileNames(obbs, bases.single.packageName);
          validateStagedObbPaths(obbs, bases.single.packageName, extractionRoot: '${stage.path}/extracted');
          if (!getInstaller().wantsContainerHandoff && device.version.sdkInt >= 30) {
            extraRefusals.add('r09ReviewObbUnsupported');
          }
        } on FormatException {
          extraRefusals.add('r09ReviewObbUnsupported');
        }
      }
      token.throwIfCancelled();
      if (!r09ActionsEligible(asset, app.additionalSettings, app.url, DateTime.now())) {
        throw const FormatException('Actions artifact expired during review');
      }
      return R09ArtifactInspection(artifactSha256: review.artifactSha256, bytes: review.bytes,
        members: review.members, selectedPaths: review.selectedPaths,
        refusals: [...review.refusals, ...extraRefusals], signerStatus: review.signerStatus,
        actionsDigestVerified: review.actionsDigestVerified,
        installedVersionCode: review.installedVersionCode, installedVersionName: review.installedVersionName,
        releaseKey: releaseKey);
    } finally {
      await stage.delete(recursive: true);
    }
  }

  /// Downloads the preferred APK for [app], returning a [DownloadedApk] or [DownloadedDir].
  Future<Object> downloadApp(
    App app, {
    bool allowUserInteraction = false,
    NotificationsProvider? notificationsProvider,
    bool useExisting = true,
    bool preserveListingIdentity = false,
    R03DownloadRecord? resumeRecord,
    R05OperationReceipt? retryParent,
    R07TimelineEntry? queuedIntent,
    bool Function()? allowExternalContinuation,
    void Function(double? progress, int? received, int? total)? onProgress,
  }) async {
    final timeline = R07OperationTimeline.instance;
    final expected = R07OperationIntent(kind: queuedIntent?.intent.kind ?? 'download',
      listingKey: app.listingKey, packageId: app.id, channel: r11ChannelFingerprint(app),
      release: downloadReleaseCacheKey(InstallReleaseSnapshot.fromApp(app)),
      parentId: retryParent?.id ?? resumeRecord?.jobId ?? queuedIntent?.intent.parentId);
    final operation = queuedIntent ?? (await timeline.enqueue([expected])).single;
    return timeline.run(operation, expected, 'downloading', () {
      if (queuedIntent != null) {
        final live = apps[app.listingKey]?.app;
        if (!apps.containsListingKey(app.listingKey) || live == null || r11ChannelFingerprint(live) != expected.channel ||
            downloadReleaseCacheKey(InstallReleaseSnapshot.fromApp(live)) != expected.release ||
            live.id != expected.packageId) {
          throw StateError('Queued release changed before execution');
        }
      }
      return _downloadAppOwned(app,
      allowUserInteraction: allowUserInteraction, notificationsProvider: notificationsProvider,
      useExisting: useExisting, preserveListingIdentity: preserveListingIdentity,
      resumeRecord: resumeRecord, retryParent: retryParent,
      allowExternalContinuation: allowExternalContinuation, onProgress: onProgress,
      timelineId: operation.id);
    }, successStage: expected.kind == 'install' ? 'ready' : 'downloadReady',
      failureTransferId: (error) => error is DownloadPausedException ? error.transferId : null,
      failureReason: (error) => error is DownloadPausedException ? 'paused' :
        error is CancellationException ? 'cancelled' :
        error is SocketException || error is HandshakeException || error is TimeoutException ? 'network' : 'operation');
  }

  Future<Object> _downloadAppOwned(
    App app, {
    bool allowUserInteraction = false,
    NotificationsProvider? notificationsProvider,
    bool useExisting = true,
    bool preserveListingIdentity = false,
    R03DownloadRecord? resumeRecord,
    R05OperationReceipt? retryParent,
    bool Function()? allowExternalContinuation,
    void Function(double? progress, int? received, int? total)? onProgress,
    required String timelineId,
  }) async {
    if (resumeRecord != null && (!preserveListingIdentity ||
        !resumeRecord.explicitlyResumable || resumeRecord.historyBinding?.listingKey != app.listingKey ||
        resumeRecord.historyBinding?.packageId != app.id ||
        resumeRecord.historyBinding?.channel != r11ChannelFingerprint(app) ||
        resumeRecord.historyBinding?.releaseFingerprint != downloadReleaseCacheKey(InstallReleaseSnapshot.fromApp(app)))) {
      throw StateError('Resume requires the exact retained release and listing');
    }
    final original = app;
    final originalRelease = preserveListingIdentity ? InstallReleaseSnapshot.fromApp(original) : null;
    bool matchesListing() {
      if (!preserveListingIdentity) return apps.containsListingKey(app.listingKey);
      if (allowExternalContinuation?.call() != true) return false;
      final live = r11ExactLiveListing(apps, original);
      final expected = originalRelease!;
      if (live == null || !expected.belongsTo(live)) return false;
      final release = InstallReleaseSnapshot.fromApp(live);
      return release.version == expected.version &&
          release.assetName == expected.assetName &&
          release.assetUrl == expected.assetUrl &&
          release.expectedSha256 == expected.expectedSha256;
    }
    if (preserveListingIdentity && (!matchesListing() || isTempId(app) ||
        app.allowIdChange || app.settings.getBool('trackOnly') ||
        apps[app.listingKey]?.downloadProgress != null)) {
      throw StateError('External download requires an unchanged, idle listing');
    }
    final initialNotification = DownloadNotification(
      app.finalName,
      0,
      appId: app.listingKey,
    );
    final notifId = initialNotification.id;
    var nativeDownloadServiceStarted = false;
    final cancellationToken = registerDownloadCancellation(app.listingKey);
    try {
      if (matchesListing()) {
        apps[app.listingKey]!.downloadProgress = 0;
        apps[app.listingKey]!.downloadReceivedBytes = null;
        apps[app.listingKey]!.downloadTotalBytes = null;
        notify();
      }
      if (app.apkUrls.isEmpty) throw NoAPKError();
      if (app.preferredApkIndex >= app.apkUrls.length) {
        app = app.copyWith(preferredApkIndex: app.apkUrls.length - 1);
      }
      if (app.preferredApkIndex < 0) app = app.copyWith(preferredApkIndex: 0);
      final downloadRelease = InstallReleaseSnapshot.fromApp(app);
      // Copy the discovery identity now; do not read mutable listing settings
      // after a download or Android approval returns.
      final discoverySettings = Map<String, dynamic>.of(app.additionalSettings);
      final discoveryChannel = r11ChannelFingerprint(app);
      if (retryParent != null && (retryParent.listingKey != app.listingKey ||
          retryParent.packageId != app.id || retryParent.channelFingerprint != discoveryChannel ||
          retryParent.releaseFingerprint != downloadReleaseCacheKey(downloadRelease))) {
        throw StateError('Retry parent no longer matches selected release');
      }
      final actionsEvidence = discoverySettings[r04ActionsArchiveEvidenceKey];
      if (actionsEvidence is Map) {
        discoverySettings[r04ActionsArchiveEvidenceKey] = Map<String, dynamic>.from(actionsEvidence);
      }
      R03DownloadRecord? transferEvidence;
      final reviewBinding = _r09Selections[this]?[app.listingKey];
      if (reviewBinding != null && reviewBinding.releaseKey != _r09ReleaseKey(app)) {
        throw ObtainiumError(tr('r09ReviewSelectionChanged'));
      }
      if (!preserveListingIdentity && matchesListing()) apps[app.listingKey]!.app = app;
      final AppSource source = SourceProvider().getSource(
        app.url,
        overrideSource: app.overrideSource,
      );
      final additionalSettingsPlusSourceConfig = await source
          .buildMergedSettings(app.additionalSettings, settingsProvider);
      final String downloadUrl = await source.assetUrlPrefetchModifier(
        await source.generalReqPrefetchModifier(
          app.apkUrls[app.preferredApkIndex].value,
          additionalSettingsPlusSourceConfig,
        ),
        app.url,
        additionalSettingsPlusSourceConfig,
      );
      if (allowUserInteraction && isCleartextDownloadUrl(downloadUrl)) {
        final NavigatorState? navigator = globalNavigatorKey.currentState;
        if (navigator == null || !navigator.mounted) {
          throw ObtainiumError(tr('cancelled'));
        }
        final bool? proceed = await showDialog<bool>(
          context: navigator.context,
          barrierDismissible: false,
          builder: (BuildContext dialogContext) => AlertDialog(
            title: Text(tr('insecureDownloadUrl')),
            contentPadding: appDialogContentPadding,
            content: Text(tr('cleartextDownloadWarningExplanation')),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(dialogContext).pop(false),
                child: Text(tr('cancel')),
              ),
              FilledButton(
                onPressed: () => Navigator.of(dialogContext).pop(true),
                child: Text(tr('continue')),
              ),
            ],
          ),
        );
        if (proceed != true) {
          throw ObtainiumError(tr('cancelled'));
        }
      }
      if (notificationsProvider != null) {
        await notificationsProvider.cancel(notifId);
      }
      nativeDownloadServiceStarted =
          await NativeFeatures.startDownloadForegroundService(
            id: initialNotification.id,
            appId: app.listingKey,
            title: initialNotification.title,
            message: initialNotification.message,
            channelCode: initialNotification.channelCode,
            channelName: initialNotification.channelName,
            channelDescription: initialNotification.channelDescription,
            cancelLabel: tr('cancel'),
          );
      var notif = initialNotification;
      if (!nativeDownloadServiceStarted) {
        unawaited(notificationsProvider?.notify(notif));
      }
      int? prevProg;
      var fileNameNoExt =
          '${app.listingKey}-${downloadReleaseCacheKey(downloadRelease)}';
      if (source.urlsAlwaysHaveExtension) {
        fileNameNoExt =
            '$fileNameNoExt.${app.apkUrls[app.preferredApkIndex].key.split('.').last}';
      }
      final headers = await source.getAssetRequestHeaders(
        app.additionalSettings,
        app.url,
        downloadUrl,
        forAPKDownload: true,
      );
      void updateDownloadProgress(
        double? progress, [
        int? received,
        int? total,
      ]) {
        if (preserveListingIdentity && !matchesListing()) {
          cancellationToken.cancel();
          return;
        }
        onProgress?.call(progress, received, total);
        final int? prog = progress?.ceil();
        if (matchesListing()) {
          apps[app.listingKey]!.downloadReceivedBytes = received;
          apps[app.listingKey]!.downloadTotalBytes = total;
          apps[app.listingKey]!.downloadProgress = progress;
          // Only rebuild listeners when the displayed (integer) percent
          // actually changes, to avoid redundant whole-page rebuilds on
          // every sub-percent download tick.
          if (prevProg != prog) {
            notify();
          }
        }
        notif = DownloadNotification(
          app.finalName,
          prog ?? _downloadCompleteProgress,
          // Only foreground downloads are cancellable from the notification;
          // the background isolate's token isn't reachable from the main
          // isolate that handles the action tap.
          appId: isBg ? null : app.listingKey,
          receivedBytes: received,
          totalBytes: total,
        );
        if (prog != null &&
            (prevProg == null ||
                (prog - prevProg!).abs() >= 5 ||
                prog == 100)) {
          if (nativeDownloadServiceStarted) {
            unawaited(
              NativeFeatures.showDownloadProgressNotification(
                id: notif.id,
                appId: app.listingKey,
                title: notif.title,
                message: notif.message,
                channelCode: notif.channelCode,
                progressPercent: prog,
                indeterminate: false,
                cancelLabel: tr('cancel'),
                shortCriticalText: '$prog%',
              ),
            );
          } else {
            unawaited(notificationsProvider?.notify(notif));
          }
          prevProg = prog;
        }
      }

      Future<File> runDownload(Map<String, String>? requestHeaders) {
        if (preserveListingIdentity && !matchesListing()) {
          throw StateError('External download listing changed');
        }
        return downloadFileWithRetry(
          downloadUrl,
          fileNameNoExt,
          source.urlsAlwaysHaveExtension,
          updateDownloadProgress,
          this.apkDir.path,
          useExisting: useExisting,
          headers: requestHeaders,
          // The Actions API and signed ZIP always require verified TLS even
          // when a separate legacy source permits insecure certificates.
          allowInsecure: app.additionalSettings[GitHub.r04SourceModeKey] ==
              GitHub.r04ModeActions ? false : app.settings.getBool('allowInsecure'),
          logs: logs,
          cancellationToken: cancellationToken,
          onVerified: (receipt) => transferEvidence = receipt,
          historyBinding: r11ValidPackage(app.id) ? R03HistoryBinding(
            app.listingKey, app.id, discoveryChannel,
            releaseFingerprint: downloadReleaseCacheKey(downloadRelease)) : null,
          resumeRecord: resumeRecord, expectedSha256: downloadRelease.expectedSha256,
          onPauseAvailable: (_) => notify(),
        );
      }

      File downloadedFile;
      try {
        downloadedFile = await runDownload(headers);
      } catch (error) {
        if (resumeRecord != null || app.additionalSettings[GitHub.r04SourceModeKey] ==
                GitHub.r04ModeActions ||
            !shouldRetryGitHubDownloadWithoutAuthorization(
          source: source,
          headers: headers,
          error: error,
        )) {
          rethrow;
        }
        final Map<String, String> unauthenticatedHeaders =
            Map<String, String>.from(headers!)
              ..remove(HttpHeaders.authorizationHeader);
        unawaited(
          logs.add(
            'GitHub asset download returned 401 with stored PAT. Retrying without authentication.',
            level: LogLevel.warning,
          ),
        );
        downloadedFile = await runDownload(unauthenticatedHeaders);
      }
      final observation = transferEvidence;
      if (observation == null) throw StateError('Verified transfer receipt unavailable');
      await R07OperationTimeline.instance.advance(timelineId, 'downloaded', transferId: observation.jobId);
      await R07OperationTimeline.instance.advance(timelineId, 'verifying');
      // R04 P02: verify ZIP bytes before unzipping, APK inspection, UI
      // approval, or any real Android installer session. Also rejects stale
      // saved provenance and poisoned downloads reused from the local cache.
      await verifyR04ActionsArchiveBeforeExtraction(
        archive: downloadedFile,
        additionalSettings: discoverySettings,
        sourceUrl: downloadRelease.sourceUrl,
        selectedAssetUrl: downloadRelease.assetUrl,
        selectedAssetName: downloadRelease.assetName,
      );
      final transfer = transferEvidence;
      final archiveDigest = await sha256FileOffIsolate(downloadedFile.path);
      if (transfer == null || !transfer.originObserved || transfer.finalDigest != archiveDigest) {
        throw StateError('Missing exact transfer receipt for installation');
      }
      final isActions = discoverySettings[GitHub.r04SourceModeKey] == GitHub.r04ModeActions;
      final rawActions = discoverySettings[r04ActionsArchiveEvidenceKey];
      final canonicalSource = Uri.parse(downloadRelease.sourceUrl);
      final actions = isActions ? Map<String, dynamic>.from(rawActions as Map) : const <String, dynamic>{};
      final provenance = R05DownloadProvenance(
        releaseFingerprint: downloadReleaseCacheKey(downloadRelease), archiveSha256: archiveDigest,
        sourceHost: canonicalSource.host, finalOrigin: transfer.finalOrigin,
        channelFingerprint: discoveryChannel,
        repository: isActions ? canonicalSource.pathSegments.join('/') : null,
        branch: actions['branch'] as String?, workflowId: actions['workflowId'] as int?,
        runId: actions['runId'] as int?, runAttempt: actions['runAttempt'] as int?,
        artifactId: actions['artifactId'] as int?, commitSha: actions['commitSha'] as String?,
        parentAttemptId: retryParent?.id, timelineId: timelineId,
      );
      if (reviewBinding != null) {
        final actualDigest = archiveDigest;
        if (!reviewBinding.matches(_r09ReleaseKey(app), actualDigest)) {
          await downloadedFile.delete();
          throw ObtainiumError(tr('r09ReviewSelectionChanged'));
        }
      }
      if (matchesListing()) {
        apps[app.listingKey]!.downloadProgress = _remainingStepsProgress
            .toDouble();
        notify();
        notif = DownloadNotification(app.finalName, _remainingStepsProgress);
        if (nativeDownloadServiceStarted) {
          unawaited(
            NativeFeatures.showDownloadProgressNotification(
              id: notif.id,
              appId: app.listingKey,
              title: notif.title,
              message: notif.message,
              channelCode: notif.channelCode,
              progressPercent: _remainingStepsProgress,
              indeterminate: true,
              cancelLabel: tr('cancel'),
            ),
          );
        } else {
          unawaited(notificationsProvider?.notify(notif));
        }
      }
      onProgress?.call(_remainingStepsProgress.toDouble(), null, null);
      PackageInfo? newInfo;
      // The archive [newInfo] came from, kept so its icon can be salvaged too.
      String? parsedArchivePath;
      final originalAssetName = app.apkUrls[app.preferredApkIndex].key
          .toLowerCase();
      // The asset name is authoritative for the advertised format; the
      // downloaded path can lack the original multipart suffix (.tar.gz).
      final artifactFormat = installArtifactFormat(originalAssetName) ??
          installArtifactFormat(downloadedFile.path);
      if (artifactFormat == null) {
        throw const FormatException('Unsupported Android package artifact');
      }
      final isAPK = artifactFormat == InstallArtifactFormat.apk;
      final isXAPK = artifactFormat == InstallArtifactFormat.xapk;
      final isTarball = artifactFormat == InstallArtifactFormat.tarball;
      Directory? apkDir;
      InstallBundlePlan? inspectedPlan;
      if (isAPK) {
        parsedArchivePath = downloadedFile.path;
        newInfo = await packageManager.getPackageArchiveInfo(
          archiveFilePath: downloadedFile.path,
        );
      } else {
        final String apkDirPath = '${downloadedFile.path}-dir';
        await R07OperationTimeline.instance.advance(timelineId, 'extracting');
        try {
          if (isTarball) {
            await extractTarballFile(downloadedFile.path, apkDirPath, cancellationToken);
          } else {
            await unzipFile(downloadedFile.path, apkDirPath, cancellationToken);
          }
          apkDir = Directory(apkDirPath);
          final apks = await _archiveApkCandidates(apkDir, app, isTarball);
          final (plan, baseInfo) = await _inspectInstallBundle(
            apks,
            format: artifactFormat,
          );
          newInfo = baseInfo;
          inspectedPlan = plan;
          parsedArchivePath = plan.baseApkPath;
        } catch (_) {
          // Discard any archive whose package inventory is invalid.
          // Only remove a destination that this invocation published.
          if (apkDir != null && apkDir.existsSync()) {
            apkDir.deleteSync(recursive: true);
          }
          rethrow;
        }
      }
      if (newInfo == null) {
        unawaited(downloadedFile.delete());
        if (apkDir != null && apkDir.existsSync()) {
          apkDir.deleteSync(recursive: true);
        }
        throw ObtainiumError(tr('couldNotGetIdFromApk'))..url = app.url;
      }
      if (preserveListingIdentity) {
        cancellationToken.throwIfCancelled();
        if (!matchesListing() || newInfo.packageName != original.id) {
          throw StateError('External download package or listing changed');
        }
      }
      final (renamedFile, resolvedApp) = preserveListingIdentity
          ? (downloadedFile, app)
          : await handleAPKIDChange(app, newInfo, downloadedFile, downloadUrl);
      downloadedFile = renamedFile;
      final String resolvedAppId = resolvedApp.listingKey;
      if (resolvedApp.listingKey != app.listingKey || resolvedApp.id != app.id) {
        await R07OperationTimeline.instance.resolveDownloadedIdentity(timelineId,
          resolvedApp.listingKey, resolvedApp.id);
      }
      // handleAPKIDChange renames a bare APK once the real package id is known.
      if (isAPK) {
        parsedArchivePath = downloadedFile.path;
      }
      // Deduced icons are only ever read for apps that aren't installed yet, so
      // skip the extraction cost entirely on ordinary updates to installed apps.
      if (!preserveListingIdentity) {
        if (apps[resolvedAppId]?.installedInfo == null) {
          await storeIconFromApkArchive(resolvedAppId, parsedArchivePath);
        }
      }
      // A filename prefix does not prove an older transfer is disposable.
      // Preserve its cache/partial bytes for explicit, owner-bound recovery.

      if (identical(_r09Selections[this]?[app.listingKey], reviewBinding)) {
        _r09Selections[this]?.remove(app.listingKey);
      }
      if (isAPK) {
        return DownloadedApk(
          resolvedAppId,
          downloadedFile,
          release: downloadRelease.withPackage(newInfo), provenance: provenance,
        );
      } else {
        DownloadedDirType dirType;
        if (isXAPK) {
          dirType = DownloadedDirType.xapk;
        } else if (artifactFormat == InstallArtifactFormat.apks) {
          dirType = DownloadedDirType.apks;
        } else if (artifactFormat == InstallArtifactFormat.apkm) {
          dirType = DownloadedDirType.apkm;
        } else if (isTarball) {
          dirType = DownloadedDirType.tarball;
        } else {
          dirType = DownloadedDirType.zip;
        }
        return DownloadedDir(
          resolvedAppId,
          downloadedFile,
          apkDir!,
          dirType,
          release: downloadRelease.withPackage(newInfo), provenance: provenance, inspectedPlan: inspectedPlan,
        );
      }
    } finally {
      clearDownloadCancellation(original.listingKey, cancellationToken);
      if (nativeDownloadServiceStarted) {
        await NativeFeatures.stopDownloadForegroundService();
      }
      unawaited(notificationsProvider?.cancel(notifId));
      if ((!preserveListingIdentity && matchesListing()) ||
          (preserveListingIdentity && r11ExactLiveListing(apps, original) != null)) {
        apps[app.listingKey]!.downloadProgress = null;
        apps[app.listingKey]!.downloadReceivedBytes = null;
        apps[app.listingKey]!.downloadTotalBytes = null;
        notify();
      }
    }
  }

  // Gates every update action in the app, so the awaiting-third-party indicator
  // is deliberately excluded: that row is waiting on another app's installer, not
  // occupying ObtainX, and counting it would disable "update all" and every row's
  // update button for the life of the indicator.
  bool areDownloadsRunning() => apps.values
      .where(
        (element) =>
            element.downloadProgress != null &&
            element.downloadProgress != _awaitingThirdPartyInstallSentinel &&
            element.downloadProgress != _recoveredNativeInstallSentinel,
      )
      .isNotEmpty;

  /// Whether [app] can be installed without a user prompt, based only on
  /// device/app capability (single APK plus the active installer's own rules).
  /// Independent of the background-update setting.
  Future<bool> canInstallSilently(App app) async {
    if (app.apkUrls.length > 1) {
      unawaited(
        logs.add(
          'App will not be installed silently: multiple APK URLs require manual selection: ${app.id}',
        ),
      );
      return false; // Manual API selection means silent install is not possible
    }
    // Installer-specific eligibility (target SDK, installer of record, OS
    // version, Shizuku, etc.) is delegated to the active installer strategy.
    return getInstaller().canInstallSilently(app);
  }

  /// Whether [app] should be installed silently in the background: the
  /// background-update policy (global toggle + per-app exemption) on top of
  /// [canInstallSilently]. Foreground installs must not use this.
  Future<bool> canInstallSilentlyInBackground(App app) async {
    if (!settingsProvider.enableBackgroundUpdates) {
      unawaited(
        logs.add(
          'App will not be installed in the background: background updates are disabled: ${app.id}',
        ),
      );
      return false;
    }
    if (app.settings.getBool('exemptFromBackgroundUpdates')) {
      unawaited(
        logs.add(
          'App will not be installed in the background: exempted from background updates: ${app.id}',
        ),
      );
      return false;
    }
    return canInstallSilently(app);
  }

  Future<void> waitForUserToReturnToForeground(
    NotificationsProvider notificationsProvider,
  ) async {
    if (!isForeground) {
      await notificationsProvider.notify(
        completeInstallationNotification,
        cancelExisting: true,
      );
      await FGBGEvents.instance.stream
          .firstWhere((t) => t == FGBGType.foreground)
          .timeout(
            const Duration(minutes: 5),
            onTimeout: () => FGBGType.foreground,
          );
      await notificationsProvider.cancel(completeInstallationNotification.id);
    }
  }

  /// Whether a stock-installer downgrade should go to Android rather than be
  /// blocked up front. The settings switch is ObtainX-only and an upstream sync
  /// once dropped it from here, leaving the switch dead; keep both checks.
  Future<bool> canDowngradeApps() async =>
      settingsProvider.enableDowngradeModules &&
      await isDowngradeModuleInstalled();

  // R01: both ZIP and TAR use the same bounded, atomic archive extractor.
  Future<void> unzipFile(String filePath, String destinationPath,
      [CancellationToken? token]) async {
    await extractZipOffIsolate(filePath, destinationPath,
        checkCancellation: token?.throwIfCancelled);
  }

  Future<void> extractTarballFile(
    String filePath,
    String destinationPath, [CancellationToken? token]
  ) async {
    await extractTarballOffIsolate(filePath, destinationPath,
        checkCancellation: token?.throwIfCancelled);
  }

  void _ensureGitHubAttestationPolicy(String appId) {
    final app = apps[appId]?.app;
    if (app == null) return;
    final source = SourceProvider().getSource(app.url, overrideSource: app.overrideSource);
    if (githubAttestationEnforcementBlocksInstall(app, source, settingsProvider)) {
      throw ObtainiumError(githubAttestationEnforcedBlockedMessage(app.latestAttestationStatus));
    }
  }

  Future<bool> installApkDir(
    DownloadedDir dir,
    NotificationsProvider? firstInstallNotificationsProvider, {
    bool needsBGWorkaround = false,
    InstallPrecommitGate? preparationGate,
    Map<String, dynamic> installOptions = const {},
    bool skipPreInstallVerification = false,
    ThemeData? toastTheme,

    /// See [installApk]'s param of the same name. Verification/scanning runs
    /// once here against the container before any split part is installed.
    bool showMalwareScanDialog = false,
  }) async {
    final timelineId = await _ensureInstallTimeline(dir.appId, dir.file,
      dir.provenance, dir.timelineId);
    dir.installTimelineId = timelineId;
    try {
    // Verify + scan the container once up front; the split-APK installApk calls
    // below pass skipMalwareScan so it is not repeated per part.
    if (skipPreInstallVerification) {
      _ensureGitHubAttestationPolicy(dir.appId);
    }
    if (!skipPreInstallVerification) {
      await R07OperationTimeline.instance.observePreparation(timelineId, 'scanning');
      final bool proceedAfterVerification = await _runPreInstallVerification(
        appId: dir.appId,
        primaryFile: dir.file,
        showMalwareScanDialog: showMalwareScanDialog,
        toastTheme: toastTheme,
        cleanupOnSkip: () {
          try {
            if (dir.file.existsSync()) dir.file.deleteSync();
            if (dir.extracted.existsSync()) {
              dir.extracted.deleteSync(recursive: true);
            }
          } catch (_) {}
        },
      );
      if (!proceedAfterVerification) {
        await R07OperationTimeline.instance.observePreparation(timelineId, 'declined');
        return false;
      }
    }
    await R07OperationTimeline.instance.observePreparation(timelineId, 'preparingInstall');
    // R02: inspect every candidate before the installer is ever invoked.
    // One complete base+config session is required, not an arbitrary first APK.
    var somethingInstalled = false;
    final installer = getInstaller();
    try {
      final MultiAppMultiError errors = MultiAppMultiError();
      final apkFiles = <File>[];
      final obbFiles = <File>[];
      for (var file
          in dir.extracted
              .listSync(recursive: true, followLinks: false)
              .whereType<File>()) {
        if (file.path.toLowerCase().endsWith('.apk')) {
          apkFiles.add(file);
        } else if (file.path.toLowerCase().endsWith('.obb')) {
          // Do not write expansion data before Android confirms install.
          obbFiles.add(file);
        }
      }
      final format = switch (dir.type) {
        DownloadedDirType.xapk => InstallArtifactFormat.xapk,
        DownloadedDirType.apks => InstallArtifactFormat.apks,
        DownloadedDirType.apkm => InstallArtifactFormat.apkm,
        DownloadedDirType.tarball => InstallArtifactFormat.tarball,
        DownloadedDirType.zip => InstallArtifactFormat.zip,
      };
      final (plan, plannedInfo) = await _inspectInstallBundle(
        apkFiles,
        format: format,
        expectedPackageName: apps[dir.appId]?.app.id,
      );
      final inspected = dir.inspectedPlan;
      if (inspected == null || inspected.packageName != plan.packageName ||
          inspected.versionCode != plan.versionCode ||
          inspected.selectedMembers.length != plan.selectedMembers.length ||
          !inspected.selectedMembers.asMap().entries.every((entry) =>
            entry.value.path == plan.selectedMembers[entry.key].path &&
            entry.value.sha256 == plan.selectedMembers[entry.key].sha256)) {
        throw StateError('Archive selection changed after inspection');
      }
      validateObbFileNames(
        obbFiles.map((file) => file.path).toList(),
        plan.packageName,
      );
      validateStagedObbPaths(
        obbFiles.map((file) => file.path).toList(), plan.packageName,
        extractionRoot: dir.extracted.path,
      );
      // Android 11+ restricts direct Android/obb writes. The legacy file
      // branch could silently return after a cancelled SAF picker and still
      // report the APK installed. Refuse before any APK session instead.
      if (obbFiles.isNotEmpty && !installer.wantsContainerHandoff) {
        final sdk = (await DeviceInfoPlugin().androidInfo).version.sdkInt;
        if (sdk >= 30) {
          throw const FormatException(
            'OBB payload cannot be installed by this backend on Android 11+',
          );
        }
        // Ask before APK installation, not after a successful Android session.
        final permission = await Permission.storage.request();
        if (!permission.isGranted) {
          throw const FormatException(
            'OBB write permission denied before Android installation',
          );
        }
      }

      if (installer.wantsContainerHandoff) {
        // Hand off the original bundle file (XAPK/ZIP/tarball) to the
        // third-party installer rather than the extracted split APKs.
        InstallReleaseSnapshot? release;
        try {
          // Even for a third-party handoff, the bundle has to be unambiguous.
          // The original container is handed off, not one extracted split.
          final packageInfo = plannedInfo;
          release = dir.release?.withPackage(packageInfo);
          final r05Container = await _r05BeginAttempt(
              dir.appId, File(plan.baseApkPath), packageInfo, kind: 'container-handoff',
              selected: plan.configApkPaths.map(File.new).toList(), release: release,
              provenance: dir.provenance, container: dir.file, plan: plan, timelineId: timelineId);
          await _recordPendingInstall(dir.appId, release);
          if (!await _r05AdditionalApproval(r05Container,
              interactive: showMalwareScanDialog)) {
            await _clearPendingInstall(dir.appId, release);
            return false;
          }
          // No await after this synchronous barrier: a route-level Cancel
          // cannot claim to undo a third-party handoff already dispatched.
          await _r05CheckHandoff(r05Container, plan.sessionPaths, container: dir.file);
          _ensureGitHubAttestationPolicy(dir.appId);
          if (!sealInstallHandoff(preparationGate)) {
            throw const CancellationException();
          }
          final result = await installer.installApk(
            [dir.file.path],
            appId: dir.appId,
            installOptions: installOptions,
          );
          final exactInstalled = await _r05CloseAttempt(r05Container, result, release);
          if (result.isError || result.isCancelled) {
            await _clearPendingInstall(dir.appId, release);
          }
          if (result.isHandedOff) {
            // The native callback might already have confirmed the pending
            // snapshot while we awaited the external installer. Never show a
            // stale pending indicator after that evidence has been consumed.
            final pending = InstallReleaseSnapshot.fromJson(
              apps[dir.appId]?.app.additionalSettings[pendingInstallReleaseKey],
            );
            if (pending != null) {
              _awaitThirdPartyInstallConfirmation(r05Container);
            }
          }
          if (result.isError) {
            await _throwRecordedInstallError(dir.appId, result.errorCode ?? -1);
          }
          if (exactInstalled) {
            somethingInstalled = true;
            await _r05PersistBoundConfirmation(r05Container, release, packageInfo);
          }
          unawaited(_disposeDownloadedBundle(dir, somethingInstalled));
        } on CancellationException {
          await _clearPendingInstall(dir.appId, release);
          rethrow;
        } catch (e) {
          await _clearPendingInstall(dir.appId, release);
          unawaited(
            logs.add(
              'Could not install container from ${dir.type}: ${e.runtimeType}',
            ),
          );
          errors.add(dir.appId, e, appName: apps[dir.appId]?.name);
        }
        if (errors.idsByErrorString.isNotEmpty) {
          throw errors;
        }
        return somethingInstalled;
      }

      try {
        final wasInstalled = await installApk(
          DownloadedApk(dir.appId, File(plan.baseApkPath), release: dir.release, provenance: dir.provenance, container: dir.file, installTimelineId: timelineId),
          firstInstallNotificationsProvider,
          needsBGWorkaround: needsBGWorkaround,
          preparationGate: preparationGate,
          installOptions: installOptions,
          additionalAPKs: plan.configApkPaths
              .map((path) => DownloadedApk(dir.appId, File(path), release: dir.release))
              .toList(),
          // Container already verified/scanned above.
          skipMalwareScan: true,
          toastTheme: toastTheme,
          // The bundle itself is what gets saved (below); don't also persist
          // the extracted primary APK under the same release asset name.
          skipApkSaveFolderPersistForPrimaryApk: true,
          approvedPlan: plan,
        );
        somethingInstalled = somethingInstalled || wasInstalled;
        if (wasInstalled) {
          for (final obb in obbFiles) {
            await moveObbFile(obb, plan.packageName);
          }
        }
        unawaited(_disposeDownloadedBundle(dir, somethingInstalled));
      } on CancellationException {
        rethrow;
      } catch (e) {
        unawaited(
          logs.add(
            'Could not install APKs for ${dir.appId} from ${dir.type}: ${e.runtimeType}',
          ),
        );
        errors.add(dir.appId, e, appName: apps[dir.appId]?.name);
      }
      if (errors.idsByErrorString.isNotEmpty) {
        throw errors;
      }
    } finally {
      // Keep cleanup complete before another retry can reuse the same path.
      if (dir.extracted.existsSync()) {
        await dir.extracted.delete(recursive: true);
      }
    }
    return somethingInstalled;
    } on CancellationException {
      await R07OperationTimeline.instance.settlePreparation(timelineId, 'cancelled');
      rethrow;
    } catch (_) {
      await R07OperationTimeline.instance.settlePreparation(timelineId, 'failed');
      rethrow;
    } finally {
      await R07OperationTimeline.instance.settlePreparation(timelineId, 'unknown');
    }
  }

  /// Installs a downloaded APK file, with optional auxiliary split APKs and Shizuku support.
  Future<bool> installApk(
    DownloadedApk file,
    NotificationsProvider? firstInstallNotificationsProvider, {
    bool needsBGWorkaround = false,
    InstallPrecommitGate? preparationGate,
    Map<String, dynamic> installOptions = const {},
    List<DownloadedApk> additionalAPKs = const [],

    /// Whether a build-verification/VirusTotal result can be shown as a dialog
    /// (someone's watching) or must skip the app and notify (background/silent).
    bool showMalwareScanDialog = false,
    ThemeData? toastTheme,

    /// Set by [installApkDir] for a split APK — the container was already
    /// verified/scanned once, so re-running per part would waste effort and the
    /// VirusTotal rate limit.
    bool skipMalwareScan = false,

    /// Set by [installApkDir] for the extracted primary split APK: the outer
    /// bundle ([DownloadedDir.file]) is what gets persisted to the save folder,
    /// so the extracted APK must not be copied again under the same asset name.
    bool skipApkSaveFolderPersistForPrimaryApk = false,
    InstallBundlePlan? approvedPlan,
  }) async {
    final timelineId = await _ensureInstallTimeline(file.appId, file.container ?? file.file,
      file.provenance, file.timelineId);
    file.installTimelineId = timelineId;
    try {
    // Resolve the "Save downloaded APK copies" target once, up front (matches
    // main). Only touched when the feature is on and this isn't the extracted
    // primary of a bundle install; feature-off leaves this null (no behavior
    // change, no extra SAF access).
    final bool saveApkCopiesRequested =
        settingsProvider.saveDownloadedApkCopies &&
        !skipApkSaveFolderPersistForPrimaryApk;
    final Uri? apkSaveTreeUri = (Platform.isAndroid && saveApkCopiesRequested)
        ? await settingsProvider.getApkSaveDir(warnIfInaccessible: true)
        : null;
    if (skipMalwareScan) {
      _ensureGitHubAttestationPolicy(file.appId);
    }
    if (!skipMalwareScan) {
      await R07OperationTimeline.instance.observePreparation(timelineId, 'scanning');
      final bool proceed = await _runPreInstallVerification(
        appId: file.appId,
        primaryFile: file.file,
        showMalwareScanDialog: showMalwareScanDialog,
        toastTheme: toastTheme,
        cleanupOnSkip: () {
          try {
            if (file.file.existsSync()) file.file.deleteSync();
            for (final a in additionalAPKs) {
              if (a.file.existsSync()) a.file.deleteSync();
            }
          } catch (_) {}
        },
      );
      if (!proceed) {
        await R07OperationTimeline.instance.observePreparation(timelineId, 'declined');
        return false;
      }
    }
    await R07OperationTimeline.instance.observePreparation(timelineId, 'preparingInstall');
    if (firstInstallNotificationsProvider != null) {
      await _shareWithVerifiedApps(
        file,
        firstInstallNotificationsProvider,
        toastTheme: toastTheme,
      );
    }
    final newInfo = await packageManager.getPackageArchiveInfo(
      archiveFilePath: file.file.path,
    );
    if (newInfo == null) {
      try {
        deleteFile(file.file);
        for (var a in additionalAPKs) {
          deleteFile(a.file);
        }
      } catch (e) {
        unawaited(
          logs.add(
            'Failed to delete bad download files for ${file.appId}: ${e.runtimeType}',
          ),
        );
      }
      throw ObtainiumError(tr('badDownload'))..url = apps[file.appId]?.app.url;
    }
    final PackageInfo? appInfo = await getInstalledInfo(
      apps[file.appId]!.app.id,
    );
    unawaited(
      logs.add(
        'Installing "${newInfo.packageName}" version "${newInfo.versionName}" versionCode "${newInfo.versionCode}"${appInfo != null ? ' (from existing version "${appInfo.versionName}" versionCode "${appInfo.versionCode}")' : ''}',
      ),
    );
    final newVersionCode = newInfo.versionCode;
    final oldVersionCode = appInfo?.versionCode;
    if (isStockInstallerDowngrade(
          installedVersionCode: oldVersionCode,
          newVersionCode: newVersionCode,
          installerModeKey: getInstaller().modeKey,
        ) &&
        !(await canDowngradeApps()) &&
        settingsProvider.showAppDowngradeError) {
      try {
        file.file.deleteSync();
      } catch (e) {
        unawaited(
          logs.add(
            'Failed to delete downgraded APK file: ${e.runtimeType}',
            level: LogLevel.error,
          ),
        );
      }
      throw DowngradeError(oldVersionCode!, newVersionCode!);
    }
    // Persist exact intent before handoff. Uncorrelated broadcasts cannot confirm it.
    final manifestPlan = approvedPlan ?? (await _inspectInstallBundle(
      [file.file, ...additionalAPKs.map((apk) => apk.file)],
      format: additionalAPKs.isEmpty ? InstallArtifactFormat.apk : InstallArtifactFormat.apks,
      expectedPackageName: apps[file.appId]?.app.id)).$1;
    final suppliedPaths = [file.file.path, ...additionalAPKs.map((apk) => apk.file.path)];
    if (manifestPlan.sessionPaths.length != suppliedPaths.length ||
        !manifestPlan.sessionPaths.asMap().entries.every((entry) => suppliedPaths[entry.key] == entry.value)) {
      throw StateError('Supplied APKs differ from the manifest-selected session');
    }
    final installedRelease = file.release?.withPackage(newInfo);
    final r05 = await _r05BeginAttempt(file.appId, file.file, newInfo,
        kind: additionalAPKs.isEmpty ? 'apk' : 'split-session',
        selected: additionalAPKs.map((x) => x.file).toList(),
        release: installedRelease, provenance: file.provenance, container: file.container, plan: manifestPlan, timelineId: timelineId);
    await _recordPendingInstall(file.appId, installedRelease);
    if (!await _r05AdditionalApproval(r05,
        interactive: showMalwareScanDialog)) {
      await _clearPendingInstall(file.appId, installedRelease);
      return false;
    }
    final allAPKs = [file.file.path];
    allAPKs.addAll(additionalAPKs.map((a) => a.file.path));
    final InstallResult result;
    try {
      // Native stock mode keeps the owned session cancellable while
      // awaiting Android approval. Other installer modes seal irreversibly.
      final activeInstaller = getInstaller();
      if (activeInstaller.modeKey == 'system') {
        await R05OperationJournal.instance.settleIfOpen(
            r05.id, R05InstallStage.awaitingApproval,
            reason: 'Android session may require approval');
      }
      await _r05CheckHandoff(r05, allAPKs, container: file.container);
      _ensureGitHubAttestationPolicy(file.appId);
      if (!sealInstallHandoff(preparationGate,
          nativeCancelable: activeInstaller.modeKey == 'system')) {
        throw const CancellationException();
      }
      result = await activeInstaller.installApk(
        allAPKs,
        appId: file.appId,
        installOptions: {
          ...installOptions,
          // Never send a Dart owner object to an external, Shizuku or Dhizuku
          // MethodChannel. Only first-party stock mode understands this token.
          if (activeInstaller.modeKey == 'system' && preparationGate != null)
            'r02fP03Gate': preparationGate,
        },
      );
    } on CancellationException {
      await R05OperationJournal.instance.settleIfOpen(r05.id,
          R05InstallStage.cancelled, reason: 'Precommit cancellation');
      await _clearPendingInstall(file.appId, installedRelease);
      rethrow;
    } catch (_) {
      await R05OperationJournal.instance.settleIfOpen(r05.id,
          R05InstallStage.failed, reason: 'Installer threw before a reliable Android result');
      await _clearPendingInstall(file.appId, installedRelease);
      rethrow;
    }
    final bool installed = await _r05CloseAttempt(r05, result, installedRelease);
    if (result.isError || result.isCancelled) {
      await _clearPendingInstall(file.appId, installedRelease);
    }
    if (result.isHandedOff) {
      if (getInstaller().modeKey == 'external') {
        _awaitThirdPartyInstallConfirmation(r05);
      } else {
        // An uncertain native stock session is not a third-party handoff.
        // Preserve the pending source receipt and allow recovery if it still
        // belongs to this app; never manufacture successful rollback.
        apps[file.appId]?.downloadProgress = _recoveredNativeInstallSentinel;
        unawaited(recoverNativeInstallSessions());
      }
    }
    // Dispose the downloaded APK for EVERY outcome (parity with main's
    // _disposeInstalledApkFilesAfterSession): copy it into the save folder if
    // that feature is on (regardless of success — so a cancelled/pending
    // install still yields a saved copy), then delete only when the install
    // succeeded or the version was skipped. A failed/cancelled/pending install
    // with no skip keeps the file so a retry can reuse it without re-download.
    if (saveApkCopiesRequested && apkSaveTreeUri != null) {
      await _saveInstalledApkCopyThenMaybeDelete(
        appId: file.appId,
        primaryFile: file.file,
        installReportedOk: installed,
        apkSaveTreeUri: apkSaveTreeUri,
        release: file.release,
      );
    } else {
      final App? appRef = apps[file.appId]?.app;
      final bool skipLatest =
          appRef != null && isSkipActiveForCurrentLatest(appRef);
      if (installed || skipLatest) {
        try {
          await file.file.delete(recursive: true);
        } catch (e) {
          unawaited(
            logs.add('Failed to delete APK after install: ${e.runtimeType}'),
          );
        }
      }
    }
    if (result.isError) {
      await _throwRecordedInstallError(file.appId, result.errorCode!);
    }
    if (installed) {
      await _r05PersistBoundConfirmation(r05, installedRelease, newInfo);
    }
    return installed;
    } on CancellationException {
      await R07OperationTimeline.instance.settlePreparation(timelineId, 'cancelled');
      rethrow;
    } catch (_) {
      await R07OperationTimeline.instance.settlePreparation(timelineId, 'failed');
      rethrow;
    } finally {
      await R07OperationTimeline.instance.settlePreparation(timelineId, 'unknown');
    }
  }

  Future<void> _shareWithVerifiedApps(
    DownloadedApk file,
    NotificationsProvider notificationsProvider, {
    ThemeData? toastTheme,
  }) async {
    if (!settingsProvider.beforeNewInstallsShareToAppVerifier) return;
    // Intentionally does NOT gate on whether a known verifier app is installed.
    // Package-visibility rules (Android 11+) hide those packages from
    // getInstalledInfo unless each is declared in a <queries> block, so an
    // installed-check silently suppresses the share sheet for everyone (the
    // regression this restores). The user already opted in via the setting; the
    // share sheet itself lets them pick the verifier. Do not reintroduce a
    // getInstalledInfo()-based gate here.
    final XFile f = XFile(
      file.file.path,
      mimeType: 'application/vnd.android.package-archive',
    );
    showAppToast(
      tr('appVerifierInstructionToast'),
      type: ToastType.info,
      duration: const Duration(seconds: 4),
      theme: toastTheme,
    );
    try {
      await SharePlus.instance.share(ShareParams(files: [f]));
      // The share sheet pulls the user out to the verifier app; wait for them to
      // return before continuing to the actual install prompt.
      await waitForUserToReturnToForeground(notificationsProvider);
    } catch (e) {
      unawaited(logs.add('Share to App Verifier failed: ${e.runtimeType}'));
    }
  }

  Future<String> getStorageRootPath() async {
    try {
      return '/${(await getAppStorageDir()).uri.pathSegments.sublist(0, 3).join('/')}';
    } catch (_) {
      return '/storage/emulated/0';
    }
  }

  Future<void> moveObbFile(File file, String appId) async {
    // Only call after Android confirms the APK session. No best-effort success
    // return: unavailable storage or a mismatched copy is an installation error.
    if (!file.path.toLowerCase().endsWith('.obb')) {
      throw const FormatException('Unsupported expansion file type');
    }
    final sdkInt = (await DeviceInfoPlugin().androidInfo).version.sdkInt;
    if (sdkInt >= _androidApiLevelR) {
      throw const FormatException(
        'OBB payload cannot be installed by this backend on Android 11+',
      );
    }
    // The preinstall gate requests permission before the APK transaction.
    // Rechecking catches revocation while Android's installer UI is open.
    final permission = await Permission.storage.status;
    if (!permission.isGranted) {
      throw const FormatException('OBB storage permission revoked after APK install');
    }
    final target = Directory(
      '${await getStorageRootPath()}/Android/obb/$appId',
    );
    final receipt = await copyVerifiedObbFile(
      source: file,
      packageName: appId,
      destinationFolder: target,
    );
    unawaited(logs.add(
      'Verified OBB delivery ${receipt.fileName} '
      'bytes=${receipt.length} sha256=${receipt.sha256}',
    ));
  }

  Future<void> uninstallApp(String appId) async {
    final intent = AndroidIntent(
      action: 'android.intent.action.DELETE',
      data: 'package:$appId',
      flags: <int>[Flag.FLAG_ACTIVITY_NEW_TASK],
      package: 'vnd.android.package-archive',
    );
    await intent.launch();
  }

  Future<MapEntry<String, String>?> confirmAppFileUrl(
    App app,
    bool pickAnyAsset, {
    bool allowUserInteraction = false,
    bool evenIfSingleChoice = false,
    ThemeData? dialogTheme,
  }) async {
    R09ArtifactInspection? selectedReview;
    var urlsToSelectFrom = app.apkUrls;
    if (pickAnyAsset) {
      urlsToSelectFrom = [...urlsToSelectFrom, ...app.otherAssetUrls];
    }
    // If the App has more than one APK, the user should pick one (if context provided)
    MapEntry<String, String>? appFileUrl;
    if (urlsToSelectFrom.isNotEmpty) {
      final int selectedApkIndex =
          app.preferredApkIndex >= 0 &&
              app.preferredApkIndex < urlsToSelectFrom.length
          ? app.preferredApkIndex
          : 0;
      appFileUrl = urlsToSelectFrom[selectedApkIndex];
    }
    // When picking any asset, use the APK filter regex to pre-select the best matching
    // asset by default, without hiding other assets from the user.
    if (pickAnyAsset &&
        app.settings.getStringOrNull('apkFilterRegEx')?.isNotEmpty == true) {
      final matching = filterApks(
        urlsToSelectFrom,
        app.settings.getStringOrNull('apkFilterRegEx'),
        app.settings.getBool('invertAPKFilter'),
      );
      if (matching.isNotEmpty) {
        appFileUrl = matching.first;
      }
    }
    final List<String> archs =
        (await DeviceInfoPlugin().androidInfo).supportedAbis;
    bool allowed(MapEntry<String, String> asset) => pickAnyAsset ||
        r09ActionsEligible(asset, app.additionalSettings, app.url, DateTime.now());
    appFileUrl = r09ChooseArtifact(urlsToSelectFrom, archs, appFileUrl,
        downloadOnly: pickAnyAsset, allowed: allowed);

    final NavigatorState? navigator = allowUserInteraction
        ? globalNavigatorKey.currentState
        : null;
    if ((urlsToSelectFrom.length > 1 || evenIfSingleChoice ||
        (!pickAnyAsset && urlsToSelectFrom.isNotEmpty)) &&
        navigator != null &&
        navigator.mounted) {
      final picked = await showDialog<R09PickerSelection>(
        context: navigator.context,
        builder: (BuildContext ctx) {
          final Widget picker = AppFilePicker(
            app: app,
            initVal: appFileUrl,
            archs: archs,
            pickAnyAsset: pickAnyAsset,
            inspectCandidate: pickAnyAsset ? null : (asset, token, progress) =>
                _inspectR09Candidate(app, asset, token, progress),
          );
          return dialogTheme == null
              ? picker
              : Theme(data: dialogTheme, child: picker);
        },
      );
      appFileUrl = picked?.asset;
      selectedReview = picked?.inspection;
    }
    if (appFileUrl != null &&
        (!allowed(appFileUrl) ||
            !(selectedReview?.eligible ?? r09ArtifactChoice(appFileUrl.key, archs,
                downloadOnly: pickAnyAsset).eligible))) {
      return null;
    }
    String? getHost(String url) {
      if (url == 'placeholder') {
        return null;
      }
      final temp = Uri.parse(url).host.split('.');
      if (temp.length < 2) return temp.first;
      return temp.sublist(temp.length - 2).join('.');
    }

    // If the picked APK comes from an origin different from the source, get user confirmation (if context provided)
    if (appFileUrl != null &&
        ![
          getHost(app.url),
          'placeholder',
        ].contains(getHost(appFileUrl.value)) &&
        navigator != null &&
        navigator.mounted) {
      if (!(settingsProvider.hideAPKOriginWarning) &&
          await showDialog(
                context: navigator.context,
                builder: (BuildContext ctx) {
                  return APKOriginWarningDialog(
                    sourceUrl: app.url,
                    apkUrl: appFileUrl!.value,
                  );
                },
              ) !=
              true) {
        appFileUrl = null;
      }
    }
    if (appFileUrl != null && selectedReview != null && !pickAnyAsset) {
      final index = app.apkUrls.indexWhere((asset) => asset.key == appFileUrl?.key && asset.value == appFileUrl?.value);
      if (index < 0 || !selectedReview.eligible || !allowed(appFileUrl)) {
        return null;
      }
      final selectedRelease = _r09ReleaseKey(app.copyWith(preferredApkIndex: index));
      if (selectedReview.releaseKey != selectedRelease) {
        throw ObtainiumError(tr('r09ReviewSelectionChanged'));
      }
      final choices = _r09Selections[this] ?? <String, R09ReviewBinding>{};
      _r09Selections[this] = choices;
      choices[app.listingKey] = R09ReviewBinding(releaseKey: selectedRelease,
        digest: selectedReview.artifactSha256);
    }
    if (appFileUrl != null && selectedReview == null && !pickAnyAsset && navigator != null && navigator.mounted) {
      _r09Selections[this]?.remove(app.listingKey);
    }
    return appFileUrl;
  }

  // Filters app IDs into those that can be installed and those that are track-only,
  // refreshing stale data and confirming file URLs before returning.
  Future<(List<String>, List<String>)> _resolveAppsToInstall(
    List<String> appIds,
    bool allowUserInteraction, {
    ThemeData? dialogTheme,
  }) async {
    final List<String> appsToInstall = [];
    final List<String> trackOnlyAppsToUpdate = [];
    for (var id in appIds) {
      if (apps[id] == null) {
        throw ObtainiumError(tr('appNotFound'));
      }
      MapEntry<String, String>? apkUrl;
      final trackOnly = apps[id]!.app.settings.getBool('trackOnly');
      final refreshBeforeDownload = apps[id]!.needsRefreshBeforeDownload;
      if (refreshBeforeDownload) {
        await checkUpdate(id);
      }
      if (!trackOnly) {
        apkUrl = await confirmAppFileUrl(
          apps[id]!.app,
          false,
          allowUserInteraction: allowUserInteraction,
          dialogTheme: dialogTheme,
        );
      }
      if (apkUrl != null) {
        final selected = apkUrl;
        final int urlInd = apps[id]!.app.apkUrls.indexWhere(
          (e) => e.key == selected.key && e.value == selected.value,
        );
        if (urlInd < 0) {
          throw ObtainiumError(tr('r09ReviewSelectionChanged'));
        }
        if (urlInd != apps[id]!.app.preferredApkIndex) {
          apps[id]!.app = apps[id]!.app.copyWith(preferredApkIndex: urlInd);
          await saveApps([apps[id]!.app]);
        }
        if (!allowUserInteraction &&
            verificationWouldBlockAgain(apps[id]!.app)) {
          unawaited(
            logs.add(
              'Skipping background update of $id: this release already failed '
              'a pre-install check (${apps[id]!.app.additionalSettings[needsAttentionCodeKey]}).',
            ),
          );
        } else if (allowUserInteraction ||
            await canInstallSilentlyInBackground(apps[id]!.app)) {
          appsToInstall.add(id);
        }
      }
      if (trackOnly) {
        trackOnlyAppsToUpdate.add(id);
      }
    }
    return (appsToInstall, trackOnlyAppsToUpdate);
  }

  /// Downloads APKs for [appIds] and installs them, silently when possible.
  /// Without a BuildContext, apps requiring user interaction are skipped
  /// and a notification is sent instead. Returns IDs of successfully downloaded apps.
  Future<List<String>> downloadAndInstallLatestApps(
    List<String> appIds,
    BuildContext? context, {
    NotificationsProvider? notificationsProvider,
    bool forceParallelDownloads = false,
    bool useExisting = true,
    ThemeData? dialogTheme,
    R05OperationReceipt? retryParent,
    R07TimelineEntry? resumeQueued,
  }) async {
    if (resumeQueued != null && (retryParent != null || context == null || appIds.length != 1 ||
        appIds.single != resumeQueued.intent.listingKey || resumeQueued.intent.kind != 'install' ||
        resumeQueued.stage != 'queued' || resumeQueued.intent.parentId != null)) {
      throw StateError('Queued install requires exact explicit consent');
    }
    if (retryParent != null) {
      if (context == null || appIds.length != 1 || appIds.single != retryParent.listingKey ||
          !const {R05InstallStage.failed, R05InstallStage.cancelled}.contains(retryParent.stage)) {
        throw StateError('Historical retry requires one explicitly selected failed attempt');
      }
      final records = await R05OperationJournal.instance.list();
      if (!records.any((item) => item.encode() == retryParent.encode()) ||
          records.any((item) => item.listingKey == retryParent.listingKey &&
              !const {R05InstallStage.confirmed, R05InstallStage.failed, R05InstallStage.cancelled}.contains(item.stage))) {
        throw StateError('Historical retry ownership changed');
      }
    }
    final bool allowUserInteraction = context != null;
    if (notificationsProvider == null && allowUserInteraction) {
      final BuildContext? appContext = globalNavigatorKey.currentContext;
      if (appContext != null && appContext.mounted) {
        notificationsProvider = appContext.read<NotificationsProvider>();
      }
    }

    final packages = <String, String>{
      for (final id in appIds)
        if (apps[id] != null && apps[id]!.app.additionalSettings['trackOnly'] != true)
          id: apps[id]!.app.id,
    };
    if (r09SafeBulkSelection(appIds, packages).length != appIds.toSet().length) {
      throw ObtainiumError(tr('r09ConflictingListings'));
    }
    var (appsToInstall, trackOnlyAppsToUpdate) = await _resolveAppsToInstall(
      appIds,
      allowUserInteraction,
      dialogTheme: dialogTheme,
    );

    // Mark all specified track-only apps as latest. Recorded as an explicit user
    // mark and saved without install-status correction: the user asked for this,
    // and correction would otherwise wipe the version right back out within this
    // same save for any track-only app whose package is absent from the device.
    await saveApps(
      trackOnlyAppsToUpdate.map((e) {
        var a = acknowledgeSourceRelease(apps[e]!.app);
        a = a.copyWith(
          additionalSettings: Map<String, dynamic>.from(a.additionalSettings)
            ..[trackOnlyUserMarkedInstalledKey] = true
            ..['trackOnlyUndeterminedInstalledVersion'] = false
            // Retire the legacy 2.9.7 reset sentinel, as the mass-mark action
            // does: its migration restores the device version (null here) and
            // would undo this mark on the next reconcile.
            ..remove(installStatusResetKey),
        );
        return a;
      }).toList(),
      attemptToCorrectInstallStatus: false,
    );

    final MultiAppMultiError errors = MultiAppMultiError();
    final List<String> installedIds = [];
    final List<({String appName, String status, String? detail})>
    malwareScanSkips = [];

    // Move Obtainium to the end of the line (let all other apps update first)
    appsToInstall = moveStrToEnd(
      appsToInstall,
      obtainiumId,
      strB: obtainiumTempId,
    );
    appsToInstall = moveStrToEnd(appsToInstall, '$obtainiumId.fdroid');
    appsToInstall = moveStrToEnd(appsToInstall, '$obtainiumId.debug');

    // Acquire install privileges once for the whole batch. This used to run per
    // app inside the download step, which with parallel downloads meant one
    // check per app racing all the others (and, for Shizuku, racing the first
    // install) as soon as the APKs were ready - the batch stalled with nothing
    // in the logs (ObtainX#283). One prompt up front is also less intrusive.
    if (appsToInstall.isNotEmpty) {
      try {
        await getInstaller().ensurePermission(toastTheme: dialogTheme);
      } catch (error) {
        for (final id in appsToInstall) {
          errors.add(id, error, appName: apps[id]?.name);
        }
        throw errors;
      }
    }

    if (resumeQueued != null && (appsToInstall.length != 1 || appsToInstall.single != resumeQueued.intent.listingKey)) {
      throw StateError('Queued install selection changed');
    }
    final queued = resumeQueued == null ? await R07OperationTimeline.instance.enqueue([
      for (final id in appsToInstall) R07OperationIntent(kind: 'install',
        listingKey: id, packageId: apps[id]!.app.id, channel: r11ChannelFingerprint(apps[id]!.app),
        release: downloadReleaseCacheKey(InstallReleaseSnapshot.fromApp(apps[id]!.app)),
        parentId: retryParent?.id),
    ]) : [resumeQueued];
    final queuedByListing = {for (final entry in queued) entry.intent.listingKey: entry};

    Future<void> installDownloadResult(_InstallResult result) async {
      if ((result.downloadedFile == null && result.downloadedDir == null) ||
          errors.appIdNames.containsKey(result.id)) {
        return;
      }
      try {
        await _installDownloadedApp(
          result.id,
          result.willBeSilent,
          result.downloadedFile,
          result.downloadedDir,
          installedIds,
          errors,
          allowUserInteraction,
          notificationsProvider,
          dialogTheme,
        );
      } on MalwareScanBlockedError catch (error) {
        malwareScanSkips.add((
          appName: apps[result.id]?.name ?? result.id,
          status: error.status,
          detail: error.detail,
        ));
      } catch (error) {
        errors.add(result.id, error, appName: apps[result.id]?.name);
      }
    }

    try {
      if (!forceParallelDownloads && !settingsProvider.parallelDownloads) {
        for (final id in appsToInstall) {
          await installDownloadResult(
            await _downloadAppForInstall(
              id,
              allowUserInteraction,
              notificationsProvider,
              useExisting,
              errors,
              dialogTheme,
              retryParent: retryParent,
              queuedIntent: queuedByListing[id]!,
            ),
          );
        }
      } else {
        final downloads = <({String id, Future<_InstallResult> result})>[
          for (final id in appsToInstall)
            (
              id: id,
              result: _downloadAppForInstall(
                id,
                allowUserInteraction,
                notificationsProvider,
                useExisting,
                errors,
                dialogTheme,
                retryParent: retryParent,
                queuedIntent: queuedByListing[id]!,
              ),
            ),
        ];
        final selfUpdateIds = <String>{
          obtainiumId,
          obtainiumTempId,
          '$obtainiumId.fdroid',
          '$obtainiumId.debug',
        };
        await processDownloadResultsAsReady(
          downloads: downloads,
          deferUntilEnd: selfUpdateIds.contains,
          process: installDownloadResult,
        );
      }
    } finally {
      // Clear any remaining progress in case the flow was interrupted
      // (e.g. unhandled error in a download, app backgrounded/killed, etc.)
      for (var id in appsToInstall) {
        if (apps[id]?.downloadProgress != _awaitingThirdPartyInstallSentinel &&
            apps[id]?.downloadProgress != _recoveredNativeInstallSentinel) {
          apps[id]?.downloadProgress = null;
        }
      }
      notify();
    }

    if (malwareScanSkips.isNotEmpty && notificationsProvider != null) {
      unawaited(
        notificationsProvider.notify(
          MalwareScanSkippedNotification(malwareScanSkips),
        ),
      );
    }

    if (errors.idsByErrorString.isNotEmpty) {
      throw errors;
    }

    return installedIds;
  }

  Future<List<String>> downloadAppAssets(
    List<String> appIds, {
    bool forceParallelDownloads = false,
    ThemeData? dialogTheme,
  }) async {
    final BuildContext? appContext = globalNavigatorKey.currentContext;
    if (appContext == null) {
      throw ObtainiumError(tr('unknown'));
    }
    final NotificationsProvider notificationsProvider = appContext
        .read<NotificationsProvider>();
    final List<MapEntry<MapEntry<String, String>, App>> filesToDownload = [];
    for (var id in appIds) {
      if (apps[id] == null) {
        throw ObtainiumError(tr('appNotFound'));
      }
      MapEntry<String, String>? fileUrl;
      final refreshBeforeDownload = apps[id]!.needsRefreshBeforeDownload;
      if (refreshBeforeDownload) {
        await checkUpdate(id);
      }
      if (apps[id]!.app.apkUrls.isNotEmpty ||
          apps[id]!.app.otherAssetUrls.isNotEmpty) {
        final MapEntry<String, String>? tempFileUrl = await confirmAppFileUrl(
          apps[id]!.app,
          true,
          allowUserInteraction: true,
          evenIfSingleChoice: true,
          dialogTheme: dialogTheme,
        );
        if (tempFileUrl != null) {
          final s = SourceProvider().getSource(
            apps[id]!.app.url,
            overrideSource: apps[id]!.app.overrideSource,
          );
          final additionalSettingsPlusSourceConfig = await s
              .buildMergedSettings(
                apps[id]!.app.additionalSettings,
                settingsProvider,
              );
          fileUrl = MapEntry(
            tempFileUrl.key,
            await s.assetUrlPrefetchModifier(
              await s.generalReqPrefetchModifier(
                tempFileUrl.value,
                additionalSettingsPlusSourceConfig,
              ),
              apps[id]!.app.url,
              additionalSettingsPlusSourceConfig,
            ),
          );
        }
      }
      if (fileUrl != null) {
        filesToDownload.add(MapEntry(fileUrl, apps[id]!.app));
      }
    }

    // Prepare to download+install Apps
    final MultiAppMultiError errors = MultiAppMultiError();
    final List<String> downloadedIds = [];

    if (forceParallelDownloads || !settingsProvider.parallelDownloads) {
      for (var urlWithApp in filesToDownload) {
        await _downloadAssetFile(
          urlWithApp.key,
          urlWithApp.value,
          errors,
          downloadedIds,
          notificationsProvider,
        );
      }
    } else {
      await Future.wait(
        filesToDownload.map(
          (urlWithApp) => _downloadAssetFile(
            urlWithApp.key,
            urlWithApp.value,
            errors,
            downloadedIds,
            notificationsProvider,
          ),
        ),
      );
    }
    if (errors.idsByErrorString.isNotEmpty) {
      throw errors;
    }
    return downloadedIds;
  }

  /// Collect package metadata for every member and return a deterministic,
  /// compatible complete session. Configuration-split metadata can be absent
  /// from Android PackageManager, but an unidentified base is always refused.
  Future<(InstallBundlePlan, PackageInfo)> _inspectInstallBundle(
    List<File> apkFiles, {
    required InstallArtifactFormat format,
    String? expectedPackageName,
  }) async {
    final members = <InstallApkMember>[];
    final infoByPath = <String, PackageInfo>{};
    for (final file in apkFiles) {
      if (FileSystemEntity.typeSync(file.path, followLinks: false) !=
          FileSystemEntityType.file) {
        throw const FormatException('APK member is not a regular file');
      }
      final member = await inspectInstallApkMember(file);
      PackageInfo? info;
      if (member.splitName == null) {
        info = await packageManager.getPackageArchiveInfo(archiveFilePath: file.path);
        if (info == null || info.packageName != member.packageName ||
            info.versionCode != member.versionCode) {
          throw const FormatException('Manifest/platform package identity mismatch');
        }
        infoByPath[file.path] = info;
      }
      members.add(member);
    }
    final device = await DeviceInfoPlugin().androidInfo;
    final dispatcher = WidgetsBinding.instance.platformDispatcher;
    final uiLocales = dispatcher.locales.map((locale) => locale.toLanguageTag())
        .toList(growable: false);
    final views = dispatcher.views;
    final int? uiDensityDpi = views.isNotEmpty
        ? (views.first.devicePixelRatio * 160).round()
        : null;
    validateP05DeviceProfile(
      sdk: device.version.sdkInt,
      supportedAbis: device.supportedAbis,
      locales: uiLocales,
      densityDpi: uiDensityDpi,
    );
    final plan = resolveInstallBundlePlan(
      members: members,
      format: format,
      supportedAbis: device.supportedAbis,
      deviceSdkVersion: device.version.sdkInt,
      deviceLocales: uiLocales,
      deviceDensityDpi: uiDensityDpi,
      expectedPackageName: expectedPackageName,
    );
    verifyP05SdkEnvelope(
      plan: plan, members: members, deviceSdk: device.version.sdkInt,
    );
    final baseInfo = infoByPath[plan.baseApkPath];
    if (baseInfo == null) {
      throw const FormatException('Base APK identity cannot be verified');
    }
    return (plan, baseInfo);
  }

  Future<void> _installDownloadedApp(
    String id,
    bool willBeSilent,
    DownloadedApk? downloadedFile,
    DownloadedDir? downloadedDir,
    List<String> installedIds,
    MultiAppMultiError errors,
    bool allowUserInteraction,
    NotificationsProvider? notificationsProvider,
    ThemeData? toastTheme,
  ) async {
    final appEntry = apps[id];
    if (appEntry == null) return;
    // Nothing to install (e.g. the download was cancelled): skip silently.
    if (downloadedFile == null && downloadedDir == null) return;
    // Installation has actually begun: show an indeterminate busy indicator
    // rather than a frozen percentage. If a VirusTotal scan will run first, lead
    // with "Scanning" so the indicator doesn't flash "Installing" before the scan
    // (the scan step later flips this to "Flagged"/"Installing" as appropriate).
    final InstallPrecommitGate? installPreparationGate = allowUserInteraction
        ? beginInstallPreparation(id)
        : null;
    appEntry.downloadProgress = willScanApkWithVirusTotal(appEntry.app)
        ? _scanningProgressSentinel
        : _installingProgressSentinel;
    notify();
    try {
      bool sayInstalled = true;
      final NotificationsProvider? firstInstallNotificationsProvider =
          appEntry.installedInfo == null && allowUserInteraction
          ? notificationsProvider
          : null;
      final String installerModeKey = getInstaller().modeKey;
      // Only the stock session-based installer needs the background-completion
      // workaround (its install await never returns in the background).
      final bool needBGWorkaround =
          willBeSilent && !allowUserInteraction && installerModeKey == 'system';
      final bool shizukuPretendToBeGooglePlay =
          settingsProvider.shizukuPretendToBeGooglePlay ||
          appEntry.app.settings.getBool('shizukuPretendToBeGooglePlay');
      if (downloadedFile != null) {
        if (needBGWorkaround) {
          await R07OperationTimeline.instance.observePreparation(downloadedFile.timelineId, 'scanning');
          final bool proceedAfterVerification =
              await _runPreInstallVerification(
                appId: id,
                primaryFile: downloadedFile.file,
                showMalwareScanDialog: false,
                cleanupOnSkip: () {
                  try {
                    if (downloadedFile.file.existsSync()) {
                      downloadedFile.file.deleteSync();
                    }
                  } catch (_) {}
                },
              );
          if (!proceedAfterVerification) {
            await R07OperationTimeline.instance.observePreparation(
              downloadedFile.timelineId ?? downloadedDir?.timelineId, 'declined');
            return;
          }
          final baseline = await captureInstallBaseline(id);
          unawaited(_r05TrackBackgroundInstall(id,
            installApk(
              downloadedFile,
              null,
              needsBGWorkaround: true,
              installOptions: {
                'shizukuPretendToBeGooglePlay': shizukuPretendToBeGooglePlay,
              },
              skipMalwareScan: true,
            ),
          ));
          final packageChanged = await waitForPackageInstall(
            id,
            baseline,
            attempts: _bgInstallConfirmAttempts,
          );
          // A changed package is an observation, not an attempt-bound receipt.
          sayInstalled = false;
          unawaited(
            logs.add(
              packageChanged
                  ? 'BG package changed for $id; receipt remains unconfirmed'
                  : 'BG install poll timed out for $id after $_bgInstallConfirmAttempts attempts',
              level: packageChanged ? LogLevel.info : LogLevel.warning,
            ),
          );
          if (!sayInstalled) {
            // No attempt identity is available to this generic package poll.
            final latestInfo = await getInstalledInfo(id);
            unawaited(
              logs.add(
                'BG install final state for $id: wasInstalled=${baseline.wasInstalled}, '
                'baselineUpdateTime=${baseline.updateTime}, '
                'currentUpdateTime=${latestInfo?.lastUpdateTime}, '
                'latestVersion=${appEntry.app.latestVersion}',
                level: LogLevel.warning,
              ),
            );
          }
        } else {
          sayInstalled = await installApk(
            downloadedFile,
            firstInstallNotificationsProvider,
            installOptions: {
              'shizukuPretendToBeGooglePlay': shizukuPretendToBeGooglePlay,
            },
            showMalwareScanDialog: allowUserInteraction,
            toastTheme: toastTheme,
            preparationGate: installPreparationGate,
          );
        }
      } else {
        if (needBGWorkaround) {
          await R07OperationTimeline.instance.observePreparation(downloadedDir?.timelineId, 'scanning');
          final bool proceedAfterVerification =
              await _runPreInstallVerification(
                appId: id,
                primaryFile: downloadedDir!.file,
                showMalwareScanDialog: false,
                cleanupOnSkip: () {
                  try {
                    if (downloadedDir.file.existsSync()) {
                      downloadedDir.file.deleteSync();
                    }
                    if (downloadedDir.extracted.existsSync()) {
                      downloadedDir.extracted.deleteSync(recursive: true);
                    }
                  } catch (_) {}
                },
              );
          if (!proceedAfterVerification) {
            await R07OperationTimeline.instance.observePreparation(
              downloadedFile?.timelineId ?? downloadedDir.timelineId, 'declined');
            return;
          }
          final baseline = await captureInstallBaseline(id);
          unawaited(_r05TrackBackgroundInstall(id,
            installApkDir(
              downloadedDir,
              null,
              needsBGWorkaround: true,
              skipPreInstallVerification: true,
            ),
          ));
          final packageChanged = await waitForPackageInstall(
            id,
            baseline,
            attempts: _bgInstallConfirmAttempts,
          );
          // A changed package is an observation, not an attempt-bound receipt.
          sayInstalled = false;
          unawaited(
            logs.add(
              packageChanged
                  ? 'BG package changed for $id; receipt remains unconfirmed'
                  : 'BG install poll timed out for $id after $_bgInstallConfirmAttempts attempts',
              level: packageChanged ? LogLevel.info : LogLevel.warning,
            ),
          );
          if (!sayInstalled) {
            // No attempt identity is available to this generic package poll.
            final latestInfo = await getInstalledInfo(id);
            unawaited(
              logs.add(
                'BG install final state for $id: wasInstalled=${baseline.wasInstalled}, '
                'baselineUpdateTime=${baseline.updateTime}, '
                'currentUpdateTime=${latestInfo?.lastUpdateTime}, '
                'latestVersion=${appEntry.app.latestVersion}',
                level: LogLevel.warning,
              ),
            );
          }
        } else {
          sayInstalled = await installApkDir(
            downloadedDir!,
            firstInstallNotificationsProvider,
            installOptions: {
              'shizukuPretendToBeGooglePlay': shizukuPretendToBeGooglePlay,
            },
            showMalwareScanDialog: allowUserInteraction,
            toastTheme: toastTheme,
            preparationGate: installPreparationGate,
          );
        }
      }
      if (willBeSilent && !allowUserInteraction) {
        if (installerModeKey == 'system' && !sayInstalled) {
          // Stock background install couldn't be confirmed within the polling
          // window, so report it as a best-effort attempt rather than a result.
          unawaited(
            notificationsProvider?.notify(
              SilentUpdateAttemptNotification([appEntry.app], id: id.hashCode),
            ),
          );
        } else {
          unawaited(
            notificationsProvider?.notify(
              SilentUpdateNotification(
                [appEntry.app],
                sayInstalled,
                id: id.hashCode,
              ),
            ),
          );
        }
      }
      if (sayInstalled) {
        installedIds.add(id);
        // Dismiss the update notification since the app was successfully installed
        unawaited(notificationsProvider?.cancel(updateNotificationId));
      }
    } on CancellationException {
      await R07OperationTimeline.instance.observePreparation(
        downloadedFile?.timelineId ?? downloadedDir?.timelineId, 'cancelled');
      // The platform handoff was refused before dispatch, not installed.
      unawaited(logs.add('R02F P03 precommit user cancellation: $id'));
    } catch (_) {
      await R07OperationTimeline.instance.settlePreparation(
        downloadedFile?.timelineId ?? downloadedDir?.timelineId, 'failed');
      rethrow;
    } finally {
      if (installPreparationGate != null) {
        endInstallPreparation(id, installPreparationGate);
        unawaited(recoverNativeInstallSessions());
      }
      // Leave the awaiting-third-party indicator alone; it outlives the handoff
      // on purpose and clears itself on the package broadcast or its own timer.
      if (appEntry.downloadProgress != _awaitingThirdPartyInstallSentinel &&
          appEntry.downloadProgress != _recoveredNativeInstallSentinel) {
        appEntry.downloadProgress = null;
      }
      notify();
    }
  }

  Future<_InstallResult> _downloadAppForInstall(
    String id,
    bool allowUserInteraction,
    NotificationsProvider? notificationsProvider,
    bool useExisting,
    MultiAppMultiError errors,
    ThemeData? toastTheme, {
    R05OperationReceipt? retryParent,
    required R07TimelineEntry queuedIntent,
  }) async {
    bool willBeSilent = false;
    DownloadedApk? downloadedFile;
    DownloadedDir? downloadedDir;
    try {
      final downloadedArtifact = await downloadApp(
        apps[id]!.app,
        allowUserInteraction: allowUserInteraction,
        notificationsProvider: notificationsProvider,
        useExisting: retryParent == null && useExisting,
        retryParent: retryParent, queuedIntent: queuedIntent,
      );
      if (downloadedArtifact is DownloadedApk) {
        downloadedFile = downloadedArtifact;
      } else if (downloadedArtifact is DownloadedDir) {
        downloadedDir = downloadedArtifact;
      } else {
        throw ObtainiumError(tr('downloadFailed'))..url = apps[id]?.app.url;
      }
      id = downloadedFile?.appId ?? downloadedDir?.appId ?? id;
      // Bridge download-to-install gap so the Dismissible stays disabled.
      // Use 100 (download complete) rather than -1 (installing) so the UI
      // doesn't report "Installing" before installation actually begins.
      apps[id]?.downloadProgress = _downloadCompleteProgress.toDouble();
      notify();
      willBeSilent = await canInstallSilently(apps[id]!.app);
      final installer = getInstaller();
      // Only the stock installer surfaces a system install prompt that pulls the
      // user away; wait for them to return before proceeding.
      if (!willBeSilent &&
          allowUserInteraction &&
          notificationsProvider != null &&
          installer.modeKey == 'system') {
        await waitForUserToReturnToForeground(notificationsProvider);
      }
    } catch (e) {
      // A user-cancelled download is not an error; skip it silently.
      if (e is! CancellationException) {
        errors.add(id, e, appName: apps[id]?.name);
      }
      downloadedFile = null;
      downloadedDir = null;
      if (apps[id] != null) {
        apps[id]!.downloadProgress = null;
        notify();
      }
    }
    return _InstallResult(
      id: id,
      willBeSilent: willBeSilent,
      downloadedFile: downloadedFile,
      downloadedDir: downloadedDir,
    );
  }

  Future<void> _downloadAssetFile(
    MapEntry<String, String> fileUrl,
    App app,
    MultiAppMultiError errors,
    List<String> downloadedIds,
    NotificationsProvider notificationsProvider,
  ) async {
    try {
      final String downloadPath = '${await getStorageRootPath()}/Download';
      final File downloadedFile = await downloadFile(
        fileUrl.value,
        fileUrl.key,
        true,
        (double? progress, [int? received, int? total]) {
          unawaited(
            notificationsProvider.notify(
              DownloadNotification(
                fileUrl.key,
                progress?.ceil() ?? 0,
                receivedBytes: received,
                totalBytes: total,
              ),
            ),
          );
        },
        downloadPath,
        expectedSha256: sourceAssetSha256(app, fileUrl),
        headers: await SourceProvider()
            .getSource(app.url, overrideSource: app.overrideSource)
            .getAssetRequestHeaders(
              app.additionalSettings,
              app.url,
              fileUrl.value,
              forAPKDownload: AppSource.isApkOrContainerFile(fileUrl.key),
            ),
        useExisting: false,
        allowInsecure: app.settings.getBool('allowInsecure'),
        logs: logs,
      );
      unawaited(
        notificationsProvider.notify(
          DownloadedNotification(
            fileUrl.key,
            fileUrl.value,
            installFilePath:
                AppSource.isApkOrContainerFile(
                  downloadedFile.path,
                  includeArchives: true,
                  includeTarballs: true,
                )
                ? downloadedFile.path
                : null,
          ),
        ),
      );
      downloadedIds.add(fileUrl.key);
    } catch (e) {
      if (e is! CancellationException) {
        errors.add(fileUrl.key, e);
      }
    } finally {
      unawaited(
        notificationsProvider.cancel(DownloadNotification(fileUrl.key, 0).id),
      );
    }
  }

  /// Hands a file downloaded to the public Download folder off to the device's
  /// default handler for it, driven by the Install action on the
  /// download-complete notification. This is the same outcome as the user
  /// tapping the file in a file manager: ObtainX plays no part in resolving,
  /// extracting, verifying, or installing it, and takes no further part once
  /// the handoff intent is launched.
  Future<void> installDownloadedAssetFile(String filePath) async {
    if (!File(filePath).existsSync()) {
      unawaited(
        LogsProvider().add(
          'Install notification tapped for missing file: $filePath',
          level: LogLevel.error,
        ),
      );
      return;
    }
    await viewInstallableFile(filePath);
  }

  /// Discovers attestation metadata for the downloaded artifact's SHA-256.
  /// This does not cryptographically verify the bundle. Returns a [githubAttestationStatus*] value, or null when the
  /// app's source is not GitHub.
  Future<String?> verifyGitHubAttestation(
    App app,
    File file, {
    Future<String> Function()? calculateDigest,
  }) async {
    final AppSource source = SourceProvider().getSource(
      app.url,
      overrideSource: app.overrideSource,
    );
    if (source is! GitHub) {
      return null;
    }
    try {
      final String standardizedUrl = source.standardizeUrl(app.url);
      final String sha256Digest =
          await (calculateDigest?.call() ?? sha256FileOffIsolate(file.path));
      return await source.getAttestationStatusForSha256Digest(
        standardizedUrl,
        sha256Digest,
        app.additionalSettings,
      );
    } catch (_) {
      unawaited(
        logs.add('GitHub attestation lookup failed'),
      );
    }
    return githubAttestationStatusError;
  }

  /// Whether a VirusTotal scan will actually run for [app]'s next install: the
  /// global feature toggle is on with a validated API key, AND this app has not
  /// been excluded by switching its per-app [enableVirusTotalScanKey] off. The
  /// per-app exclusion exists for apps whose source already publishes its own
  /// scan results, and for APKs too large to be worth uploading (VirusTotal caps
  /// uploads at 650MB even via the upload_url flow).
  ///
  /// `defaultValue: true` is load-bearing - see [enableVirusTotalScanKey]. This is
  /// the only place the key is read.
  ///
  /// The per-app check deliberately comes before the debug force so the exclusion
  /// can be exercised in debug builds.
  bool willScanApkWithVirusTotal(App app) {
    if (!app.settings.getBool(enableVirusTotalScanKey, defaultValue: true)) {
      return false;
    }
    if (kDebugMode && debugForceFlaggedMalwareScan) {
      return true;
    }
    return virusTotalScanningAvailable(settingsProvider);
  }

  /// Scans a downloaded APK with VirusTotal, when scanning is enabled and an API
  /// key is configured. A null `status` means no scan was attempted (feature off
  /// or unconfigured) — callers must treat that as a no-op, distinct from a real
  /// [malwareScanStatusError]. Unlike the pre-immutability fork version this no
  /// longer mutates [app]; the caller applies the returned detail/reportUrl via
  /// copyWith.
  Future<({String? status, String? detail, String? reportUrl})>
  scanApkWithVirusTotal(
    App app,
    File file, {
    Future<String> Function()? calculateDigest,
  }) async {
    if (!willScanApkWithVirusTotal(app)) {
      return (status: null, detail: null, reportUrl: null);
    }
    if (kDebugMode && debugForceFlaggedMalwareScan) {
      final hash =
          await (calculateDigest?.call() ?? sha256FileOffIsolate(file.path));
      return (
        status: malwareScanStatusFlagged,
        detail:
            '3/70 security vendors flagged this file (TEST result - '
            'debugForceFlaggedMalwareScan is on)',
        reportUrl: 'https://www.virustotal.com/gui/file/$hash',
      );
    }
    final String apiKey = settingsProvider.getSettingString(
      virusTotalApiKeyKey,
    )!;
    try {
      final hash =
          await (calculateDigest?.call() ?? sha256FileOffIsolate(file.path));
      final result = await VirusTotalScanner().scan(
        file,
        hash.toString(),
        apiKey,
      );
      return (
        status: result.status,
        detail: result.detail,
        reportUrl: result.reportUrl,
      );
    } catch (e) {
      unawaited(
        logs.add('Error scanning APK with VirusTotal: ${e.runtimeType}'),
      );
      return (
        status: malwareScanStatusError,
        detail: tr('virusTotalErrorGeneric', args: [safeErrorDisplay(e)]),
        reportUrl: null,
      );
    }
  }

  /// [scanApkWithVirusTotal] with the "Scanning with VirusTotal" busy state
  /// showing while it works. Also used for a user-requested rescan, where the
  /// previous round left the "Flagged" state on screen.
  Future<({String? status, String? detail, String? reportUrl})>
  _scanApkWithVirusTotalShowingProgress(
    String appId,
    App app,
    File primaryFile, {
    Future<String> Function()? calculateDigest,
  }) async {
    if (willScanApkWithVirusTotal(app)) {
      apps[appId]?.downloadProgress = _scanningProgressSentinel;
      notify();
    }
    return scanApkWithVirusTotal(
      app,
      primaryFile,
      calculateDigest: calculateDigest,
    );
  }

  /// Acts on a [scanApkWithVirusTotal] result: `clean` never interrupts;
  /// `flagged`/`error` pause with a decision dialog when someone is watching
  /// ([showMalwareScanDialog]), or skip the app (throwing
  /// [MalwareScanBlockedError]) when there is no one to ask.
  ///
  /// [cleanupOnSkip] deletes whatever was downloaded, but it only runs for a
  /// `flagged` verdict. An `error` status means VirusTotal never returned a
  /// verdict at all (offline, rate limited, key rejected, VT still analyzing
  /// past our poll window) — the APK is then no more suspect than one downloaded
  /// with scanning switched off, so deleting it buys no safety while costing the
  /// user a full re-download (see issue #240). Keeping it makes a retry nearly
  /// free: [downloadFile]'s `useExisting` path returns the cached APK, and
  /// VirusTotal's by-hash lookup usually has a finished analysis by then.
  ///
  /// Returns [_MalwareScanGateDecision.proceed] to install,
  /// [_MalwareScanGateDecision.declined] when the watching user cancelled (a
  /// deliberate choice, not a failure — callers must return quietly rather than
  /// throw), or [_MalwareScanGateDecision.retryScan] when they asked to scan the
  /// same file again (only offered for `error`).
  Future<_MalwareScanGateDecision> _handleMalwareScanResult({
    required App app,
    required String status,
    String? detail,
    String? reportUrl,
    required bool showMalwareScanDialog,
    ThemeData? toastTheme,
    required void Function() cleanupOnSkip,
  }) async {
    if (status == malwareScanStatusClean) {
      if (showMalwareScanDialog) {
        showAppToast(
          tr('malwareScanCleanToast', args: [app.finalName]),
          type: ToastType.success,
          theme: toastTheme,
        );
      }
      return _MalwareScanGateDecision.proceed;
    }
    final bool deleteDownloadOnSkip = status == malwareScanStatusFlagged;
    if (showMalwareScanDialog) {
      final NavigatorState? navigator = globalNavigatorKey.currentState;
      if (navigator == null || !navigator.mounted) {
        return _MalwareScanGateDecision.proceed;
      }
      final ThemeData dialogTheme = Theme.of(navigator.context);
      final MalwareScanDialogChoice? choice =
          await showDialog<MalwareScanDialogChoice>(
            context: navigator.context,
            barrierDismissible: false,
            builder: (BuildContext ctx) => Theme(
              data: dialogTheme,
              child: MalwareScanWarningDialog(
                appName: app.finalName,
                status: status,
                detail: detail,
                reportUrl: reportUrl,
              ),
            ),
          );
      if (choice == MalwareScanDialogChoice.installAnyway) {
        return _MalwareScanGateDecision.proceed;
      }
      if (choice == MalwareScanDialogChoice.retryScan) {
        return _MalwareScanGateDecision.retryScan;
      }
      if (deleteDownloadOnSkip) cleanupOnSkip();
      return _MalwareScanGateDecision.declined;
    }
    if (deleteDownloadOnSkip) cleanupOnSkip();
    // A flagged APK is flagged again on every background retry, so without this
    // the app silently stops updating. A scan that only failed to finish isn't
    // recorded: the next try can get a verdict.
    if (status == malwareScanStatusFlagged) {
      await _rememberBlockingAttention(
        app.listingKey,
        needsAttentionMalwareFlagged,
        detail: app.latestVersion,
      );
    }
    throw MalwareScanBlockedError(status, detail, appName: app.finalName);
  }

  Uri? _documentUriFromSafPluginResult(dynamic pluginResult) {
    if (pluginResult == null) return null;
    if (pluginResult is Map) {
      return Uri.parse(
        Map<String, dynamic>.from(pluginResult)['uri'] as String,
      );
    }
    return (pluginResult as dynamic).uri as Uri?;
  }

  /// Writes [source] into the SAF tree as [displayName] without loading the
  /// whole file into memory. Replaces an existing document with the same name.
  Future<bool> _chunkedCopyApkToSafTree(
    File source,
    Uri treeUri,
    String displayName, {
    String? mimeType,
  }) async {
    final String resolvedMime =
        mimeType ??
        (displayName.toLowerCase().endsWith('.apk')
            ? 'application/vnd.android.package-archive'
            : (displayName.toLowerCase().endsWith('.zip')
                  ? 'application/zip'
                  : (displayName.toLowerCase().endsWith('.json')
                        ? 'application/json'
                        : '*/*')));
    final dynamic existing = await saf.findFile(treeUri, displayName);
    if (existing != null) {
      final Uri? existingUri = existing is Map
          ? Uri.parse(Map<String, dynamic>.from(existing)['uri'] as String)
          : (existing as dynamic).uri as Uri?;
      if (existingUri != null) {
        await saf.delete(existingUri);
      }
    }
    Uri? documentUri;
    var isFirstChunk = true;
    await for (final List<int> chunk in source.openRead()) {
      final Uint8List bytes = Uint8List.fromList(chunk);
      if (isFirstChunk) {
        final dynamic created = await saf.createFile(
          treeUri,
          mimeType: resolvedMime,
          displayName: displayName,
          bytes: bytes,
        );
        isFirstChunk = false;
        documentUri = _documentUriFromSafPluginResult(created);
        if (documentUri == null) {
          return false;
        }
      } else {
        await saf.writeToFile(
          documentUri!,
          bytes: bytes,
          mode: FileMode.append,
        );
      }
    }
    if (isFirstChunk) {
      final dynamic created = await saf.createFile(
        treeUri,
        mimeType: resolvedMime,
        displayName: displayName,
        bytes: Uint8List(0),
      );
      return _documentUriFromSafPluginResult(created) != null;
    }
    return true;
  }

  /// Bundle SAF copy + delete for XAPK/ZIP/tarball installs (off the critical
  /// path). Ports main's `_finalizeDownloadedDirDisposition` bundle handling to
  /// this branch's split-file [installApkDir]: when "Save downloaded APK copies"
  /// is on and a folder resolves, [DownloadedDir.file] is copied to the save
  /// folder BEFORE it is deleted, and the delete is gated on a successful copy.
  /// When the feature is off, the bundle is deleted exactly as before.
  /// ([DownloadedDir.extracted] is disposed separately by [installApkDir]'s
  /// finally.)
  Future<void> _disposeDownloadedBundle(
    DownloadedDir dir,
    bool somethingInstalled,
  ) async {
    // Feature OFF (or non-Android): keep the bundle after a failed install so a
    // retry can reuse it — delete only when something installed or the version
    // was skipped (parity with main's !saveApkCopies branch). With no save
    // folder ever picked, the feature is off too, as the Import/Export page
    // shows it; keeping bundles for recovery is for a folder that can't be
    // reached.
    if (!Platform.isAndroid ||
        !settingsProvider.saveDownloadedApkCopies ||
        await settingsProvider.getApkSaveDir(requireAccess: false) == null) {
      final App? appForSave = apps[dir.appId]?.app;
      final bool skipLatest =
          appForSave != null && isSkipActiveForCurrentLatest(appForSave);
      if (somethingInstalled || skipLatest) {
        unawaited(dir.file.delete());
      }
      return;
    }
    try {
      final App? appForSave = apps[dir.appId]?.app;
      final bool saveApkCopiesEnabled =
          settingsProvider.saveDownloadedApkCopies;
      final Uri? resolvedApkSaveUri = saveApkCopiesEnabled
          ? await settingsProvider.getApkSaveDir(warnIfInaccessible: true)
          : null;
      var bundleCopiedOk = false;
      if (saveApkCopiesEnabled &&
          appForSave != null &&
          resolvedApkSaveUri != null &&
          dir.file.existsSync()) {
        try {
          bundleCopiedOk = await _chunkedCopyApkToSafTree(
            dir.file,
            resolvedApkSaveUri,
            storeFacingDownloadDisplayNameForApp(
              appForSave,
              release: dir.release,
            ),
          );
        } catch (exception) {
          unawaited(
            logs.add(
              'APK save folder copy failed: ${exception.runtimeType}',
              level: LogLevel.error,
            ),
          );
          showAppToast(tr('apkSaveFolderCopyFailed'), type: ToastType.error);
        }
      }
      final bool skipLatest =
          appForSave != null && isSkipActiveForCurrentLatest(appForSave);
      final bool shouldDeleteBundle;
      if (!saveApkCopiesEnabled) {
        shouldDeleteBundle = somethingInstalled || skipLatest;
      } else if (resolvedApkSaveUri != null &&
          appForSave != null &&
          dir.file.existsSync()) {
        // A configured, reachable save folder: only delete once the copy landed.
        shouldDeleteBundle =
            bundleCopiedOk && (somethingInstalled || skipLatest);
      } else {
        // Feature on but folder unreachable: keep the bundle after a successful
        // install (so the user can still recover it), delete only when skipped.
        shouldDeleteBundle = somethingInstalled ? false : skipLatest;
      }
      if (shouldDeleteBundle && dir.file.existsSync()) {
        try {
          dir.file.deleteSync();
        } catch (_) {}
      }
    } catch (exception) {
      unawaited(
        logs.add(
          'Post-install bundle disposition failed: ${exception.runtimeType}',
          level: LogLevel.error,
        ),
      );
    }
  }

  /// Per-APK SAF copy + delete after a successful single-APK install (off the
  /// critical path). Ports main's `_disposeInstalledApkFilesAfterSession`
  /// primary-file handling: the installed APK is copied to the save folder
  /// BEFORE it is deleted, and the delete is gated on a successful copy. Only
  /// invoked when the save-copies feature is on and a folder resolved; the
  /// feature-off delete happens inline at the call site, unchanged.
  Future<void> _saveInstalledApkCopyThenMaybeDelete({
    required String appId,
    required File primaryFile,
    required bool installReportedOk,
    required Uri apkSaveTreeUri,
    InstallReleaseSnapshot? release,
  }) async {
    try {
      final App? appRef = apps[appId]?.app;
      final bool skipLatest =
          appRef != null && isSkipActiveForCurrentLatest(appRef);
      var copiedOk = false;
      if (appRef != null && primaryFile.existsSync()) {
        try {
          copiedOk = await _chunkedCopyApkToSafTree(
            primaryFile,
            apkSaveTreeUri,
            storeFacingDownloadDisplayNameForApp(appRef, release: release),
          );
        } catch (exception) {
          unawaited(
            logs.add(
              'APK save folder copy failed: ${exception.runtimeType}',
              level: LogLevel.error,
            ),
          );
          showAppToast(tr('apkSaveFolderCopyFailed'), type: ToastType.error);
        }
      }
      // hasSaveFolder is always true here (caller only invokes with a resolved
      // save URI), so mirror main's hasSaveFolder branch directly.
      final bool deletePrimary = copiedOk && (installReportedOk || skipLatest);
      if (deletePrimary && primaryFile.existsSync()) {
        try {
          primaryFile.deleteSync();
        } catch (_) {}
      }
    } catch (exception) {
      unawaited(
        logs.add(
          'Post-install APK disposition failed: ${exception.runtimeType}',
          level: LogLevel.error,
        ),
      );
    }
  }

  /// Runs the pre-install verification gauntlet for [appId]: reproducible-build
  /// enforcement, GitHub attestation verify/enforce, and VirusTotal scanning.
  /// Persists attestation/malware status via copyWith + saveApps. Returns true
  /// to proceed, false when a watching user declined a flagged/errored scan;
  /// throws [ObtainiumError] for an enforcement block and
  /// [MalwareScanBlockedError] for a silent (background) skip.
  Future<bool> _runPreInstallVerification({
    required String appId,
    required File primaryFile,
    required bool showMalwareScanDialog,
    ThemeData? toastTheme,
    required void Function() cleanupOnSkip,
  }) async {
    final AppInMemory? appInMemory = apps[appId];
    if (appInMemory == null) return true;
    App app = appInMemory.app;
    // Both checks verify the same artifact. Keep this cache local to this
    // verification attempt; a user-requested retry computes a fresh digest.
    Future<String>? pendingDigest;
    Future<String> calculateDigest() {
      return pendingDigest ??= sha256FileOffIsolate(primaryFile.path);
    }

    final AppSource source = SourceProvider().getSource(
      app.url,
      overrideSource: app.overrideSource,
    );

    // Reproducible-build enforcement. Only a "not reproducible" verdict is
    // final for this release; no data yet, or a failed lookup, can pass later.
    if (reproducibleBuildEnforcementBlocksInstall(app, source)) {
      cleanupOnSkip();
      if (reproducibleBuildStatusForEnforcement(app) ==
          reproducibleBuildStatusNotReproducible) {
        await _rememberBlockingAttention(
          appId,
          needsAttentionNotReproducible,
          detail: app.latestVersion,
        );
      }
      throw ObtainiumError(reproducibleBuildEnforcedBlockedMessage());
    }

    // GitHub attestation verification (+ optional enforcement).
    if (source is GitHub &&
        source.shouldVerifyAttestations(
          app.additionalSettings,
          settingsProvider,
        )) {
      final String? attestationStatus = await verifyGitHubAttestation(
        app,
        primaryFile,
        calculateDigest: calculateDigest,
      );
      app = app.copyWith(latestAttestationStatus: attestationStatus);
      if (apps[appId] != null) {
        apps[appId]!.app = app;
      }
      await saveApps([app], updateInstalledInfo: false);
      if (source.shouldEnforceAttestations(
            app.additionalSettings,
            settingsProvider,
          )) {
        cleanupOnSkip();
        await _rememberBlockingAttention(
          appId,
          needsAttentionNoAttestation,
          detail: app.latestVersion,
        );
        throw ObtainiumError(
          githubAttestationEnforcedBlockedMessage(attestationStatus),
        );
      }
    }

    // VirusTotal malware scan. Surface "Scanning with VirusTotal" while it runs
    // (the caller set "Installing"/"Scanning" up front, but the scan is the part
    // that actually takes time), then reflect a flagged/errored result as
    // "Flagged" before prompting the user to decide. "Retry scan" loops back
    // through the same scan → persist → prompt cycle against the same file: the
    // by-hash lookup usually finds a finished analysis on the second pass, which
    // is exactly why a merely-failed scan keeps the APK instead of deleting it.
    var scan = await _scanApkWithVirusTotalShowingProgress(
      appId,
      app,
      primaryFile,
      calculateDigest: calculateDigest,
    );
    while (scan.status != null) {
      app = app.copyWith(
        latestMalwareScanStatus: scan.status,
        latestMalwareScanDetail: scan.detail,
        latestMalwareScanReportUrl: scan.reportUrl,
      );
      if (apps[appId] != null) {
        apps[appId]!.app = app;
      }
      apps[appId]?.downloadProgress = scan.status != malwareScanStatusClean
          ? _flaggedProgressSentinel
          : _installingProgressSentinel;
      notify();
      await saveApps([app], updateInstalledInfo: false);
      final _MalwareScanGateDecision decision = await _handleMalwareScanResult(
        app: app,
        status: scan.status!,
        detail: scan.detail,
        reportUrl: scan.reportUrl,
        showMalwareScanDialog: showMalwareScanDialog,
        toastTheme: toastTheme,
        cleanupOnSkip: cleanupOnSkip,
      );
      if (decision == _MalwareScanGateDecision.declined) return false;
      if (decision == _MalwareScanGateDecision.retryScan) {
        scan = await _scanApkWithVirusTotalShowingProgress(
          appId,
          app,
          primaryFile,
        );
        continue;
      }
      if (showMalwareScanDialog && scan.status != malwareScanStatusClean) {
        await Future<void>.delayed(const Duration(milliseconds: 500));
      }
      break;
    }
    // Scan cleared (or was skipped) and we're proceeding — hand back to the
    // installer as "Installing" so a lingering "Scanning"/"Flagged" state clears.
    apps[appId]?.downloadProgress = _installingProgressSentinel;
    notify();
    return true;
  }
}
