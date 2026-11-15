/// User-initiated Android document import into the existing ObtainX R02
/// installer. Local files are never treated as verified source downloads.
library;

import 'dart:io';

import 'package:android_package_manager/android_package_manager.dart';
import 'package:device_info_plus/device_info_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:obtainium/providers/apps_provider.dart';
import 'package:obtainium/services/artifact_file_work.dart';
import 'package:obtainium/services/install_bundle_plan.dart';
import 'package:obtainium/services/r02_local_archive_policy.dart';
import 'package:obtainium/services/r02f_p05_device_profile.dart';
import 'package:shared_storage/shared_storage.dart' as saf;
import 'package:path_provider/path_provider.dart';

const MethodChannel _localBridge =
    MethodChannel('dev.imranr.obtainium/r02_local_archive');

/// The selected file is copied via bounded 64KiB native SAF streaming. Never
/// use getDocumentContent here: that API buffers the entire APK into Dart RAM.
/// No install starts until package metadata, source-listing identity and an
/// explicit user review are complete.
Future<void> showR02LocalArchiveImport(
  BuildContext context,
  AppsProvider provider,
) async {
  if (!Platform.isAndroid) {
    throw const FormatException('R02 local archive import requires Android');
  }
  // Capture ScaffoldMessenger before the async SAF picker. Its own mounted
  // state is checked whenever a result is shown; never look up BuildContext
  // after the await without checking context.mounted.
  final notifications = ScaffoldMessenger.of(context);
  final chosen = await saf.openDocument(
    mimeType: '*/*', grantWritePermission: false,
    persistablePermission: false,
  );
  if (chosen == null || chosen.isEmpty) return; // Picker declined: no write.
  if (chosen.length != 1) {
    throw const FormatException('Select exactly one APK or install archive');
  }
  final document = chosen.single;
  if (document.scheme != 'content') {
    throw const FormatException('An Android SAF content URI is required');
  }

  final request = 'r02local${DateTime.now().microsecondsSinceEpoch.toRadixString(16)}';
  var wasCancelled = false;
  String? privatePath;
  Directory? extracted;

  void notice(String message) {
    if (!notifications.mounted) return;
    notifications.hideCurrentSnackBar();
    notifications.showSnackBar(SnackBar(content: Text(message)));
  }

  try {
    notifications.showSnackBar(SnackBar(
      content: const Text('Copying selected archive privately…'),
      duration: const Duration(minutes: 5),
      action: SnackBarAction(label: 'Cancel', onPressed: () {
        wasCancelled = true;
        _localBridge.invokeMethod<bool>('cancel', {'id': request});
      }),
    ));
    final Map<dynamic, dynamic>? receipt =
        await _localBridge.invokeMethod<Map<dynamic, dynamic>>('copy', {
      'id': request,
      'uri': document.toString(),
    });
    if (receipt == null) return;
    final name = receipt['name'];
    final path = receipt['path'];
    final bytes = receipt['bytes'];
    final digest = receipt['sha256'];
    if (name is! String || path is! String || bytes is! int ||
        digest is! String || !RegExp(r'^[0-9a-f]{64}$').hasMatch(digest)) {
      throw const FormatException('Malformed native SAF source receipt');
    }
    privatePath = path;
    if (wasCancelled) return;
    final format = classifyR02LocalArtifact(name, bytes);
    final source = File(path);
    if (FileSystemEntity.typeSync(path, followLinks: false) !=
            FileSystemEntityType.file ||
        (await source.length()) != bytes ||
        (await sha256FileOffIsolate(path)) != digest) {
      throw const FormatException('Local archive failed independent SHA-256 validation');
    }
    if (wasCancelled) return;

    final apks = <File>[];
    final obbs = <File>[];
    if (format == InstallArtifactFormat.apk) {
      apks.add(source);
    } else {
      final temp = await getTemporaryDirectory();
      final stage = Directory('${temp.path}/r02-local-extracted-${DateTime.now().microsecondsSinceEpoch}');
      extracted = stage;
      // R01's atomic bounded extractor refuses traversal, symlinks, duplicate
      // entries, CRC failures, excessive depth, bytes and expansion bombs.
      if (format == InstallArtifactFormat.tarball) {
        await extractTarballOffIsolate(source.path, stage.path);
      } else {
        await extractZipOffIsolate(source.path, stage.path);
      }
      for (final entity in stage.listSync(recursive: true, followLinks: false)) {
        if (FileSystemEntity.typeSync(entity.path, followLinks: false) ==
            FileSystemEntityType.link) {
          throw const FormatException('Symbolic link in local archive staging');
        }
        if (entity is! File) continue;
        if (entity.path.toLowerCase().endsWith('.apk')) apks.add(entity);
        if (entity.path.toLowerCase().endsWith('.obb')) obbs.add(entity);
      }
    }
    if (apks.isEmpty) {
      throw const FormatException('Archive contains no Android base APK');
    }
    final infos = <String, PackageInfo>{};
    final members = <InstallApkMember>[];
    for (final file in apks) {
      if (FileSystemEntity.typeSync(file.path, followLinks: false) !=
          FileSystemEntityType.file) {
        throw const FormatException('APK member is not a regular file');
      }
      PackageInfo? info;
      try {
        info = await packageManager.getPackageArchiveInfo(
          archiveFilePath: file.path,
        );
      } catch (_) {
        if (!isConfigurationSplitApk(file.path)) rethrow;
      }
      if (info != null) infos[file.path] = info;
      members.add(InstallApkMember(
        path: file.path, packageName: info?.packageName,
        versionCode: info?.versionCode,
        minSdkVersion: info?.applicationInfo?.minSdkVersion,
        targetSdkVersion: info?.applicationInfo?.targetSdkVersion,
      ));
    }
    final device = await DeviceInfoPlugin().androidInfo;
    final dispatcher = WidgetsBinding.instance.platformDispatcher;
    final locales = dispatcher.locales.map((x) => x.toLanguageTag()).toList();
    final density = dispatcher.views.isEmpty ? null :
        (dispatcher.views.first.devicePixelRatio * 160).round();
    validateP05DeviceProfile(sdk: device.version.sdkInt,
      supportedAbis: device.supportedAbis, locales: locales, densityDpi: density);
    final plan = resolveInstallBundlePlan(
      members: members, format: format,
      supportedAbis: device.supportedAbis,
      deviceSdkVersion: device.version.sdkInt,
      deviceLocales: locales, deviceDensityDpi: density,
    );
    verifyP05SdkEnvelope(plan: plan, members: members,
      deviceSdk: device.version.sdkInt);
    if (infos[plan.baseApkPath] == null) {
      throw const FormatException('Missing verified base package metadata');
    }
    final targets = provider.apps.values.where(
      (entry) => entry.app.id == plan.packageName,
    ).toList(growable: false);
    if (targets.length != 1) {
      throw const FormatException(
        'Local import requires exactly one tracked app listing for this package. '
        'Add the app first, or resolve multiple source listings.',
      );
    }
    final installer = provider.getInstaller();
    if (obbs.isNotEmpty) {
      if (format == InstallArtifactFormat.apk || extracted == null) {
        throw const FormatException('Unsupported standalone OBB selection');
      }
      validateStagedObbPaths(obbs.map((x) => x.path).toList(),
        plan.packageName, extractionRoot: extracted.path);
      if (device.version.sdkInt >= 30 && !installer.wantsContainerHandoff) {
        throw const FormatException(
          'Android 11+ OBB delivery is not qualified for the selected installer',
        );
      }
    }
    final previous = await getInstalledInfo(plan.packageName);
    if (!context.mounted || wasCancelled) return;
    notifications.hideCurrentSnackBar();
    final accepted = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (dialog) => AlertDialog(
        title: const Text('Review local installation'),
        content: SingleChildScrollView(child: Text(
          'File: $name\n'
          'Package: ${plan.packageName}\n'
          'Version code: ${plan.versionCode}\n'
          'Installed version: ${previous?.versionCode ?? 'not installed'}\n'
          'APK files in session: ${plan.sessionPaths.length}\n'
          'OBB files: ${obbs.length}\n'
          'Installer: ${installer.modeKey}\n\n'
          'This local file has no trusted download-source provenance. '
          'Existing malware and installation checks remain enforced. '
          'Android must confirm the installed package and exact APK bytes; '
          'external handoff is not confirmation.',
        )),
        actions: [
          TextButton(onPressed: () => Navigator.of(dialog).pop(false),
            child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.of(dialog).pop(true),
            child: const Text('Install')),
        ],
      ),
    );
    if (accepted != true || wasCancelled) return;
    verifyR02LocalTarget(
      expectedPackage: targets.single.app.id,
      actualPackage: plan.packageName,
      sourceListingCount: targets.length,
      requestedVersion: plan.versionCode,
      installedVersion: previous?.versionCode,
      reviewAccepted: accepted == true,
    );

    final evidence = await _localBridge.invokeMethod<Map<dynamic, dynamic>>(
      'sourceEvidence', {'package': plan.packageName,
        'version': plan.versionCode, 'sources': plan.sessionPaths});
    if (evidence == null || evidence['hashes'] is! List ||
        evidence['signers'] is! List ||
        (evidence['hashes'] as List).length != plan.sessionPaths.length ||
        (evidence['signers'] as List).isEmpty) {
      throw const FormatException('Cannot establish signed APK byte provenance');
    }
    final listing = targets.single.listingKey;
    final gate = provider.beginInstallPreparation(listing);
    try {
      if (gate.wasCancelled || wasCancelled) return;
      notifications.showSnackBar(SnackBar(
        content: const Text('Awaiting Android install confirmation…'),
        duration: const Duration(minutes: 5),
        action: SnackBarAction(label: 'Cancel', onPressed: () {
          wasCancelled = true;
          provider.cancelInstallPreparation(listing);
        }),
      ));
      final bool reported;
      if (format == InstallArtifactFormat.apk) {
        reported = await provider.installApk(
          DownloadedApk(plan.packageName, source), null,
          preparationGate: gate, showMalwareScanDialog: true,
        );
      } else {
        reported = await provider.installApkDir(
          DownloadedDir(plan.packageName, source, extracted!,
            switch (format) {
              InstallArtifactFormat.xapk => DownloadedDirType.xapk,
              InstallArtifactFormat.apks => DownloadedDirType.apks,
              InstallArtifactFormat.apkm => DownloadedDirType.apkm,
              InstallArtifactFormat.tarball => DownloadedDirType.tarball,
              _ => DownloadedDirType.zip,
            }),
          null, preparationGate: gate, showMalwareScanDialog: true,
        );
      }
      if (wasCancelled || gate.wasCancelled) {
        notice('Cancel requested; Android final install state requires reconciliation.');
        return;
      }
      final current = await getInstalledInfo(plan.packageName);
      final exactBytes = reported && !installer.wantsContainerHandoff &&
          (await _localBridge.invokeMethod<bool>('verifyInstalled', {
            'package': plan.packageName, 'version': plan.versionCode,
            'hashes': evidence['hashes'], 'signers': evidence['signers'],
          }) ?? false);
      final confirmed = r02LocalObservedInstallConfirmed(
        installerReportedSuccess: reported,
        expectedPackage: plan.packageName,
        expectedVersionCode: plan.versionCode,
        observedPackage: current?.packageName,
        observedVersionCode: current?.versionCode,
        byteEvidenceQualified: exactBytes,
      );
      if (confirmed) {
        notice('R02 local installation verified: Android package, version and exact APK bytes match.');
      } else {
        notice('Installation not independently qualified. Check Android status or retry; no success claim.');
      }
    } finally {
      provider.endInstallPreparation(listing, gate);
    }
  } finally {
    if (extracted != null && extracted.existsSync()) {
      await extracted.delete(recursive: true);
    }
    if (privatePath != null) {
      await _localBridge.invokeMethod<bool>('dispose', {'path': privatePath});
    }
  }
}
