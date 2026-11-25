// Manages state related to the list of Apps tracked by Obtainium.
//
// Exposes related functions such as those used to add, remove, download, and install Apps.

import 'dart:async';
import 'dart:collection';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:android_package_manager/android_package_manager.dart';
// Uses the pinned plugin's wire format for queries dispatched on our worker.
// ignore: implementation_imports
import 'package:android_package_manager/src/entities/impl/package_info.dart';
import 'package:battery_plus/battery_plus.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:crypto/crypto.dart';
import 'package:easy_localization/easy_localization.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:obtainium/custom_errors.dart';
import 'package:obtainium/http/obtainx_user_agent.dart';
import 'package:obtainium/http/response_bytes.dart';
import 'package:obtainium/services/app_check_store.dart';
import 'package:obtainium/services/r11_schedule.dart';
import 'package:obtainium/services/r03_download_engine.dart';
import 'package:obtainium/services/install_precommit_gate.dart';
import 'package:obtainium/installers/r02f_p03_cancellable_stock.dart';
import 'package:obtainium/providers/logs_provider.dart';
import 'package:obtainium/providers/notifications_provider.dart';
import 'package:obtainium/providers/settings_provider.dart';
import 'package:path_provider/path_provider.dart';
import 'package:flutter_fgbg/flutter_fgbg.dart';
import 'package:obtainium/providers/source_provider.dart';
import 'package:http/http.dart';
import 'package:workmanager/workmanager.dart';
import 'package:obtainium/main.dart';
// ignore: implementation_imports
import 'package:easy_localization/src/easy_localization_controller.dart';
// ignore: implementation_imports
import 'package:easy_localization/src/localization.dart';

import 'package:obtainium/providers/apps_provider_import_export.dart';
import 'package:obtainium/providers/apps_provider_install.dart';
import 'package:obtainium/providers/apps_provider_lifecycle.dart';
import 'package:obtainium/providers/apps_provider_updates.dart';
import 'package:obtainium/version/app_version.dart';
export 'package:obtainium/version/app_version.dart';

export 'apps_provider_icon_backup.dart';
export 'apps_provider_import_export.dart';
export 'apps_provider_install.dart';
export 'apps_provider_lifecycle.dart';
export 'apps_provider_updates.dart';

// Named constants for magic numbers and hardcoded values
const int _defaultRetries = 3;
const int _partialHashCheckStartingSize = 1024;
const int _partialHashCheckLowerLimit = 128;
const int _partialHashCheckDecrement = 256;
const int _bgUpdateMaxAttempts = 4;
const int _bgUpdateMaxRetryWaitSeconds = 30;
const int _bgClientExceptionRetryWaitSeconds = 15 * 60;

/// Legacy key written by ObtainX 2.9.7's reset-install-status action.
///
/// Reconciliation removes it and restores the actual device version so affected
/// apps are not pinned to "not installed" until their next reinstall.
const String installStatusResetKey = 'installStatusResetAtInstallTime';

/// Set when the user explicitly marks a track-only app as installed.
///
/// Track-only apps are often watched without being installed through ObtainX at
/// all (or under a package ID that never matches anything on the device), so
/// absence from the device is not evidence of an uninstall once the user has
/// asserted otherwise. Reconciliation treats this like a temporary package ID
/// and leaves the recorded version alone; it is cleared when the package turns
/// up on the device or the app is uninstalled through ObtainX.
const String trackOnlyUserMarkedInstalledKey = 'trackOnlyUserMarkedInstalled';

final packageManager = AndroidPackageManager();
final packageInfoFlags = PackageInfoFlags({PMFlag.getSigningCertificates});
final packageInfoFlagsLight = PackageInfoFlags({});

App resetInstallStatusToDeviceVersion(App app, PackageInfo? installedInfo) {
  final Map<String, dynamic> additionalSettings =
      Map<String, dynamic>.from(app.additionalSettings)
        ..remove(installStatusResetKey)
        ..remove(pendingInstallReleaseKey)
        ..remove(confirmedInstallReleaseKey)
        ..remove(acknowledgedSourceReleaseKey)
        ..remove(trackOnlyUserMarkedInstalledKey)
        ..remove('trackOnlyUndeterminedInstalledVersion');
  final String? installedVersion = app.usesVersionCodeAsOsVersion
      ? installedInfo?.versionCode?.toString()
      : installedInfo?.versionName;
  return app.copyWith(
    installedVersion: installedVersion,
    additionalSettings: additionalSettings,
  );
}

List<String> certificateHashesFromSignatures(Iterable<List<int>> signatures) {
  return signatures
      .map((signature) {
        final digest = sha256.convert(signature);
        return digest.bytes
            .map((byte) => byte.toRadixString(16).padLeft(2, '0').toUpperCase())
            .join(':');
      })
      .toList(growable: false);
}

/// Live download state for an app: the progress percent (listenable, with -1
/// meaning "installing" and null meaning "idle") plus the bytes downloaded and
/// total size when known. Held by reference and shared across [AppInMemory]
/// copies so UI listeners bound to an earlier instance keep updating even after
/// saveApps replaces the map entry with a copy.
class DownloadState {
  final ValueNotifier<double?> progress = ValueNotifier(null);
  int? receivedBytes;
  int? totalBytes;
}

/// Runtime wrapper for [App] holding download state and OS package info.
class AppInMemory {
  late App app;
  final DownloadState download;
  PackageInfo? installedInfo;
  Uint8List? icon;
  String? sourceType;

  ValueNotifier<double?> get downloadProgressNotifier => download.progress;

  double? get downloadProgress => download.progress.value;
  set downloadProgress(double? value) => download.progress.value = value;

  int? get downloadReceivedBytes => download.receivedBytes;
  set downloadReceivedBytes(int? value) => download.receivedBytes = value;

  int? get downloadTotalBytes => download.totalBytes;
  set downloadTotalBytes(int? value) => download.totalBytes = value;

  AppInMemory(
    this.app,
    double? downloadProgress,
    this.installedInfo,
    this.icon, {
    this.sourceType,
    DownloadState? download,
  }) : download =
           download ?? (DownloadState()..progress.value = downloadProgress);

  AppInMemory deepCopy() => AppInMemory(
    app.copyWith(),
    downloadProgress,
    installedInfo,
    icon,
    sourceType: sourceType,
    download: download,
  );

  AppInMemory copyWith({
    App? app,
    PackageInfo? installedInfo,
    Uint8List? icon,
    String? sourceType,
  }) => AppInMemory(
    app ?? this.app,
    downloadProgress,
    installedInfo ?? this.installedInfo,
    icon ?? this.icon,
    sourceType: sourceType ?? this.sourceType,
    download: download,
  );

  String get listingKey => app.listingKey;

  /// Store this listing currently tracks, resolved live when the cached
  /// [sourceType] has not been filled in yet.
  String get sourceIdentifier => sourceType ?? sourceIdentifierForApp(app);

  String get name => app.finalName;
  String get author => app.overrideAuthor ?? app.finalAuthor;

  bool get needsRefreshBeforeDownload =>
      app.settings.getBool('refreshBeforeDownload') ||
      (app.apkUrls.isNotEmpty && app.apkUrls.first.value == 'placeholder');

  bool get hasMultipleSigners {
    return installedInfo?.signingInfo?.hasMultipleSigners ?? false;
  }

  List<String> get certificateHashes {
    // https://developer.android.com/reference/android/content/pm/SigningInfo#getApkContentsSigners()
    final signatures = hasMultipleSigners
        ? installedInfo?.signingInfo?.apkContentSigners
        : installedInfo?.signingInfo?.signingCertificateHistory;

    return certificateHashesFromSignatures(signatures ?? const <List<int>>[]);
  }
}

/// In-memory library keyed by [App.listingKey], so one Android package can be
/// tracked from several stores at once.
///
/// A package's only listing is keyed by its package ID, which keeps every
/// existing caller (and record file name) working unchanged. Lookups by
/// package ID also resolve while that package has exactly one listing.
class AppListings extends MapBase<String, AppInMemory> {
  final Map<String, AppInMemory> _byListingKey = {};

  @override
  AppInMemory? operator [](Object? key) {
    if (key is! String) return null;
    final AppInMemory? direct = _byListingKey[key];
    if (direct != null) return direct;
    final List<AppInMemory> packageListings = listingsForPackage(key).toList();
    return packageListings.length == 1 ? packageListings.first : null;
  }

  @override
  void operator []=(String key, AppInMemory value) {
    value.sourceType ??= sourceIdentifierForApp(value.app);
    final String listingKey = value.listingKey;
    if (key != listingKey) {
      // A package-ID rename legitimately re-keys a listing, and it carries the
      // same listing ID across the move, so the stale key has to go. Any other
      // mismatch means [key] holds a *different* store's listing of this
      // package, which must survive - dropping it silently destroyed the
      // second listing of every multi-store app on load.
      final AppInMemory? occupant = _byListingKey[key];
      if (occupant != null &&
          occupant.app.listingId == value.app.listingId &&
          occupant.app.id != value.app.id) {
        _byListingKey.remove(key);
      }
    }
    _byListingKey[listingKey] = value;
  }

  @override
  void clear() => _byListingKey.clear();

  @override
  Iterable<String> get keys => _byListingKey.keys;

  @override
  AppInMemory? remove(Object? key) {
    if (key is! String) return null;
    final AppInMemory? direct = _byListingKey.remove(key);
    if (direct != null) return direct;
    final List<AppInMemory> packageListings = listingsForPackage(key).toList();
    if (packageListings.length != 1) return null;
    return _byListingKey.remove(packageListings.first.listingKey);
  }

  @override
  bool containsKey(Object? key) {
    if (key is! String) return false;
    return _byListingKey.containsKey(key) || listingsForPackage(key).isNotEmpty;
  }

  /// Exact-key membership, ignoring the package-ID fallback in [containsKey].
  bool containsListingKey(String listingKey) =>
      _byListingKey.containsKey(listingKey);

  /// Every tracked listing of [packageId], one per store.
  Iterable<AppInMemory> listingsForPackage(String packageId) =>
      _byListingKey.values.where((listing) => listing.app.id == packageId);
}

class DownloadedApk {
  String appId;
  File file;
  final InstallReleaseSnapshot? release;
  DownloadedApk(this.appId, this.file, {this.release});
}

enum DownloadedDirType { xapk, apks, apkm, zip, tarball }

class DownloadedDir {
  String appId;
  File file;
  Directory extracted;
  DownloadedDirType type;
  final InstallReleaseSnapshot? release;
  DownloadedDir(
    this.appId,
    this.file,
    this.extracted,
    this.type, {
    this.release,
  });
}

/// Removes all matching elements and appends the last match to the end.
/// This is intentionally deduplicating — only one instance is re-added.
List<T> _moveToEnd<T extends Object>(List<T> arr, bool Function(T) match) {
  T? temp;
  arr.removeWhere((element) {
    if (match(element)) {
      temp = element;
      return true;
    }
    return false;
  });
  if (temp != null) {
    arr.add(temp as T);
  }
  return arr;
}

List<String> moveStrToEnd(List<String> arr, String str, {String? strB}) =>
    _moveToEnd(arr, (e) => e == str || e == strB);

/// See [_moveToEnd] for semantic details.
List<MapEntry<String, int>> moveStrToEndMapEntryWithCount(
  List<MapEntry<String, int>> arr,
  MapEntry<String, int> str, {
  MapEntry<String, int>? strB,
}) => _moveToEnd(arr, (e) => e.key == str.key || e.key == strB?.key);

Future<File> downloadFileWithRetry(
  String url,
  String fileName,
  bool fileNameHasExt,
  Function? onProgress,
  String destDir, {
  bool useExisting = true,
  Map<String, String>? headers,
  int retries = _defaultRetries,
  bool allowInsecure = false,
  LogsProvider? logs,
  CancellationToken? cancellationToken,
  R03HistoryBinding? historyBinding,
}) async {
  int remaining = retries;
  while (true) {
    cancellationToken?.throwIfCancelled();
    try {
      return await downloadFile(
        url, fileName, fileNameHasExt, onProgress, destDir,
        useExisting: useExisting, headers: headers, allowInsecure: allowInsecure,
        logs: logs, cancellationToken: cancellationToken, historyBinding: historyBinding,
      );
    } catch (error) {
      final int? code = error is ObtainiumError && error.code == 'HTTP_ERROR'
          ? error.data['statusCode'] as int?
          : null;
      final transient = error is ClientException || error is SocketException ||
          error is TimeoutException || (code != null && r03CanRetryHttpStatus(code));
      if (!transient || remaining <= 0) rethrow;
      final int attempt = retries - remaining;
      remaining--;
      final int jitter = Random().nextInt(800);
      final int fromHttp = error is ObtainiumError
          ? (error.data['retryAfterSeconds'] as int? ?? 0)
          : 0;
      final int delayMs = max(fromHttp * 1000,
          min(60000, (1 << attempt) * 1200 + jitter));
      await Future.any<void>([
        Future<void>.delayed(Duration(milliseconds: delayMs)),
        if (cancellationToken != null) cancellationToken.whenCancelled,
      ]);
      cancellationToken?.throwIfCancelled();
    }
  }
}

class DownloadResponseMetadata {
  const DownloadResponseMetadata({
    required this.finalUri,
    required this.headers,
  });

  final Uri finalUri;
  final Map<String, String> headers;

  String? get suggestedFileName =>
      extractDownloadFileNameFromContentDisposition(
        headers['content-disposition'],
      );
}

String? sanitizeDownloadFileName(String? rawFileName) {
  if (rawFileName == null) {
    return null;
  }
  String fileName = rawFileName.trim();
  if (fileName.length >= 2 &&
      ((fileName.startsWith('"') && fileName.endsWith('"')) ||
          (fileName.startsWith("'") && fileName.endsWith("'")))) {
    fileName = fileName.substring(1, fileName.length - 1);
  }
  try {
    fileName = Uri.decodeComponent(fileName);
  } on FormatException {
    // Keep the server-provided text when percent encoding is malformed.
  }
  fileName = fileName.replaceAll(r'\', '/').split('/').last.trim();
  fileName = fileName
      .replaceAll(RegExp(r'[\x00-\x1F\x7F]'), '')
      .replaceAll(RegExp(r'[<>:"/\\|?*]'), '_')
      .replaceAll(RegExp(r'[. ]+$'), '');
  return fileName.isEmpty || fileName == '.' || fileName == '..'
      ? null
      : fileName;
}

/// Extracts and sanitizes an RFC 6266/RFC 5987 response filename.
String? extractDownloadFileNameFromContentDisposition(
  String? contentDisposition,
) {
  if (contentDisposition == null || contentDisposition.trim().isEmpty) {
    return null;
  }
  final RegExpMatch? encodedMatch = RegExp(
    r'(?:^|;)\s*filename\*\s*=\s*([^;]+)',
    caseSensitive: false,
  ).firstMatch(contentDisposition);
  if (encodedMatch != null) {
    String encodedFileName = encodedMatch.group(1)!.trim();
    encodedFileName = encodedFileName.replaceFirst(
      RegExp(r"^[^']*'[^']*'"),
      '',
    );
    final String? normalized = sanitizeDownloadFileName(encodedFileName);
    if (normalized != null) {
      return normalized;
    }
  }

  final RegExpMatch? plainMatch = RegExp(
    r'(?:^|;)\s*filename\s*=\s*(?:"([^"]*)"|([^;]*))',
    caseSensitive: false,
  ).firstMatch(contentDisposition);
  return sanitizeDownloadFileName(plainMatch?.group(1) ?? plainMatch?.group(2));
}

DownloadResponseMetadata _downloadResponseMetadata(
  Uri finalUri,
  HttpClientResponse response,
) {
  final headers = <String, String>{};
  response.headers.forEach((name, values) => headers[name] = values.join(', '));
  return DownloadResponseMetadata(finalUri: finalUri, headers: headers);
}

/// Fetches only enough of a download response to inspect headers and redirects.
Future<DownloadResponseMetadata?> probeDownloadResponseMetadata(
  String url, {
  Map<String, String>? headers,
  bool allowInsecure = false,
}) async {
  final requestHeaders = {...?headers, HttpHeaders.rangeHeader: 'bytes=0-0'};
  final streamed = await HttpService().sourceRequestStreamResponse(
    'GET', url, requestHeaders, {'allowInsecure': allowInsecure},
  );
  try {
    final response = streamed.value.value;
    if (response.statusCode < 200 || response.statusCode >= 300) {
      return null;
    }
    return _downloadResponseMetadata(streamed.key, response);
  } finally {
    streamed.value.key.close(force: true);
  }
}

Future<String> checkPartialDownloadHashDynamic(
  String url, {
  int startingSize = _partialHashCheckStartingSize,
  int lowerLimit = _partialHashCheckLowerLimit,
  Map<String, String>? headers,
  bool allowInsecure = false,
  void Function(DownloadResponseMetadata metadata)? onResponseMetadata,
}) async {
  bool metadataReported = false;
  void reportMetadata(DownloadResponseMetadata metadata) {
    if (!metadataReported) {
      metadataReported = true;
      onResponseMetadata?.call(metadata);
    }
  }

  for (int i = startingSize; i >= lowerLimit; i -= _partialHashCheckDecrement) {
    // Both requests fetch the same byte range to confirm the hash is
    // stable. The loop decrements on mismatch; when two consecutive
    // requests agree, the hash is considered valid.
    final List<String> ab = await Future.wait([
      checkPartialDownloadHash(
        url,
        i,
        headers: headers,
        allowInsecure: allowInsecure,
        onResponseMetadata: reportMetadata,
      ),
      checkPartialDownloadHash(
        url,
        i,
        headers: headers,
        allowInsecure: allowInsecure,
        onResponseMetadata: reportMetadata,
      ),
    ]);
    if (ab[0] == ab[1]) {
      return ab[0];
    }
  }
  throw NoVersionError();
}

Future<String> checkPartialDownloadHash(
  String url,
  int bytesToGrab, {
  Map<String, String>? headers,
  bool allowInsecure = false,
  void Function(DownloadResponseMetadata metadata)? onResponseMetadata,
}) async {
  if (bytesToGrab <= 0) {
    throw ArgumentError.value(bytesToGrab, 'bytesToGrab');
  }
  final requestHeaders = {
    ...?headers,
    HttpHeaders.rangeHeader: 'bytes=0-${bytesToGrab - 1}',
  };
  final streamed = await HttpService().sourceRequestStreamResponse(
    'GET', url, requestHeaders, {'allowInsecure': allowInsecure},
  );
  try {
    final response = streamed.value.value;
    if (response.statusCode < 200 || response.statusCode > 299) {
      throw ObtainiumError(response.reasonPhrase);
    }
    onResponseMetadata?.call(_downloadResponseMetadata(streamed.key, response));
    final bytes = await readBytePrefix(response, bytesToGrab);
    if (bytes.isEmpty) throw NoVersionError();
    return 'sha256:$bytesToGrab:${sha256.convert(bytes)}';
  } finally {
    streamed.value.key.close(force: true);
  }
}

Future<String?> checkETagHeader(
  String url, {
  Map<String, String>? headers,
  bool allowInsecure = false,
  void Function(DownloadResponseMetadata metadata)? onResponseMetadata,
}) async {
  final streamed = await HttpService().sourceRequestStreamResponse(
    'GET', url, headers, {'allowInsecure': allowInsecure},
  );
  try {
    final response = streamed.value.value;
    if (response.statusCode < 200 || response.statusCode >= 300) {
      return null;
    }
    onResponseMetadata?.call(_downloadResponseMetadata(streamed.key, response));
    final etag = response.headers.value(HttpHeaders.etagHeader)?.replaceAll('"', '');
    return etag != null
        ? sha256.convert(utf8.encode(etag)).toString().substring(0, 12)
        : null;
  } finally {
    streamed.value.key.close(force: true);
  }
}

void deleteFile(File file) {
  try {
    file.deleteSync();
  } on PathAccessException catch (e) {
    throw ObtainiumError(
      tr('fileDeletionError', args: [e.path ?? tr('unknown')]),
    );
  }
}

// R03 coalesces exact request identities and validates every persisted part.

/// Downloads a file to [destDir] with progress reporting, resuming partial downloads when supported.
Future<File> downloadFile(
  String url,
  String fileName,
  bool fileNameHasExt,
  Function? onProgress,
  String destDir, {
  bool useExisting = true,
  Map<String, String>? headers,
  bool allowInsecure = false,
  LogsProvider? logs,
  CancellationToken? cancellationToken,
  int maxBytes = r03MaximumBytes,
  Directory? privateJournalDirectory,
  bool reviewHttpsOnly = false,
  R03HistoryBinding? historyBinding,
}) async {
  final bool keepAwakeAcquired =
      await NativeFeatures.acquireDownloadKeepAwake();
  try {
    return await _downloadFile(
      url,
      fileName,
      fileNameHasExt,
      onProgress,
      destDir,
      useExisting: useExisting,
      headers: headers,
      allowInsecure: allowInsecure,
      logs: logs,
      cancellationToken: cancellationToken,
      maxBytes: maxBytes,
      privateJournalDirectory: privateJournalDirectory,
      reviewHttpsOnly: reviewHttpsOnly,
      historyBinding: historyBinding,
    );
  } finally {
    if (keepAwakeAcquired) {
      await NativeFeatures.releaseDownloadKeepAwake();
    }
  }
}

Future<File> _downloadFile(
  String url,
  String fileName,
  bool fileNameHasExt,
  Function? onProgress,
  String destDir, {
  bool useExisting = true,
  Map<String, String>? headers,
  bool allowInsecure = false,
  LogsProvider? logs,
  CancellationToken? cancellationToken,
  int maxBytes = r03MaximumBytes,
  Directory? privateJournalDirectory,
  bool reviewHttpsOnly = false,
  R03HistoryBinding? historyBinding,
}) async {
  final requestHeaders = withDefaultObtainXUserAgent(headers);
  if (requestHeaders.keys.any((key) =>
      key.toLowerCase() == 'range' || key.toLowerCase() == 'if-range')) {
    throw const FormatException('R03 cannot accept a source-defined byte range');
  }
  final responseClient = createHttpClient(allowInsecure && !reviewHttpsOnly);
  void abortDownload() => responseClient.close(force: true);
  cancellationToken?.addListener(abortDownload);
  try {
    cancellationToken?.throwIfCancelled();
    Future<HttpClientResponse> fetch(Map<String, String> requestHeaders) async =>
        (await HttpService().sourceRequestStreamResponse(
          'GET', url, requestHeaders, {'allowInsecure': allowInsecure},
          sharedClient: responseClient,
          reviewHttpsOnly: reviewHttpsOnly,
        )).value.value;
    final firstResponse = await fetch(requestHeaders);
    final suggested = extractDownloadFileNameFromContentDisposition(
      firstResponse.headers.value('content-disposition'));
    String extensionOf(String rawName) {
      final lower = rawName.toLowerCase();
      for (final suffix in const [
        '.tar.gz', '.tar.xz', '.tar.bz2', '.tar.raw',
        '.xapk', '.apkm', '.apks', '.apk', '.zip',
      ]) {
        if (lower.endsWith(suffix)) return suffix;
      }
      return '.apk';
    }
    final uri = Uri.tryParse(url);
    final pathName = uri != null && uri.pathSegments.isNotEmpty
        ? uri.pathSegments.last : url;
    final ext = extensionOf(
      AppSource.isApkOrContainerFile(pathName,
        includeArchives: true, includeTarballs: true)
          ? pathName
          : suggested ?? 'download.apk',
    );
    final safeBase = sanitizeDownloadFileName(fileName);
    if (safeBase == null) throw const FormatException('Unsafe download file name');
    final finalName = fileNameHasExt ? safeBase : '$safeBase$ext';
    final downloadedFile = File('$destDir/$finalName');
    final privateSupport = await getApplicationSupportDirectory();
    final engine = R03DownloadEngine(
      journalDirectory: privateJournalDirectory ?? Directory('${privateSupport.path}/r03-download-journal'),
      maxBytes: maxBytes,
    );
    try {
      return await engine.download(
        source: Uri.parse(url), destination: downloadedFile,
        headers: requestHeaders, firstResponse: firstResponse, fetch: fetch,
        isCancelled: () => cancellationToken?.isCancelled ?? false,
        useExisting: useExisting,
        historyBinding: historyBinding,
        onProgress: (progress, received, total) {
          onProgress?.call(progress, received, total);
        },
      );
    } on R03DownloadHttpException catch (error) {
      throw ObtainiumError('HTTP ${error.statusCode}', code: 'HTTP_ERROR',
        data: <String, dynamic>{
          'statusCode': error.statusCode,
          if (error.retryAfterSeconds != null)
            'retryAfterSeconds': error.retryAfterSeconds,
        },
      )..url = url;
    } on R03InvalidEntityException catch (error) {
      cancellationToken?.throwIfCancelled();
      throw ObtainiumError(error.reason, code: 'R03_ENTITY_INVALID')..url = url;
    } catch (_) {
      // A canceled native stream can surface as SocketException instead of
      // CancellationException when the owner closes its HTTP client.
      cancellationToken?.throwIfCancelled();
      rethrow;
    }
  } catch (_) {
    // The first GET can fail while waiting for response headers. Convert an
    // owner-requested cancellation; never mask a genuine HTTP/network error.
    cancellationToken?.throwIfCancelled();
    rethrow;
  } finally {
    cancellationToken?.removeListener(abortDownload);
    responseClient.close(force: true);
  }
}

/// Best-effort probe of a download's size via its Content-Length header. Returns
/// null when the server doesn't report it (or the request fails), so callers can
/// treat the size as unknown ("when possible").
Future<int?> getDownloadSize(
  String url, {
  Map<String, String>? headers,
  bool allowInsecure = false,
}) async {
  try {
    final streamed = await HttpService().sourceRequestStreamResponse(
      'GET', url, headers, {'allowInsecure': allowInsecure},
    );
    try {
      final response = streamed.value.value;
      if (response.statusCode < 200 || response.statusCode >= 300) {
        return null;
      }
      final length = response.contentLength;
      return length > 0 ? length : null;
    } finally {
      streamed.value.key.close(force: true);
    }
  } catch (_) {
    // A refused or failed probe is unknown; never log credential-bearing URLs.
    return null;
  }
}

/// Formats a byte count with coarse, fixed per-unit precision (e.g. "5.0 GB",
/// "512 MB", "128 KB"). Used for download-size labels in the UI.
String formatBytesForDisplay(int bytes) {
  if (bytes >= 1024 * 1024 * 1024) {
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
  } else if (bytes >= 1024 * 1024) {
    return '${(bytes / (1024 * 1024)).toStringAsFixed(0)} MB';
  } else if (bytes >= 1024) {
    return '${(bytes / 1024).toStringAsFixed(0)} KB';
  } else {
    return '$bytes B';
  }
}

/// Formats a byte count as a short human-readable string (e.g. "5.0 MB").
String formatBytes(int bytes) {
  if (bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  var size = bytes.toDouble();
  var unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit++;
  }
  final value = unit == 0 ? size.toStringAsFixed(0) : size.toStringAsFixed(1);
  return '$value ${units[unit]}';
}

/// Formats download progress as "received / total" (e.g. "5.0 MB / 20.0 MB"),
/// or just the received amount when the total is unknown. Returns null when no
/// bytes have been received yet.
String? formatDownloadSize(int? receivedBytes, int? totalBytes) {
  if (receivedBytes == null) return null;
  if (totalBytes != null && totalBytes > 0) {
    return '${formatBytes(receivedBytes)} / ${formatBytes(totalBytes)}';
  }
  return formatBytes(receivedBytes);
}

// The pinned android_package_manager native SigningInfo.toMap emits
// apkContentsSigners (Android's getter name), but SigningInfoImpl consumes
// apkContentSigners. Normalize at the native device-apps decoding boundary.
// Never substitute the historical signing lineage for current signers.
PackageInfo decodeDevicePackageInfo(Map<Object?, Object?> data) {
  final package = Map<String, dynamic>.from(data);
  final nativeSigning = package['signingInfo'];
  if (nativeSigning is Map) {
    final signing = Map<String, dynamic>.from(nativeSigning);
    if (signing.containsKey('apkContentsSigners')) {
      signing['apkContentSigners'] = signing.remove('apkContentsSigners');
    }
    package['signingInfo'] = signing;
  }
  return PackageInfoImpl(package);
}

Future<List<PackageInfo>> getAllInstalledInfo({bool light = false}) async {
  try {
    final packages = await NativeFeatures._deviceAppsChannel.invokeListMethod(
      'getInstalledPackageInfos',
      {'includeSigningCertificates': !light},
    );
    return packages
            ?.map((entry) => decodeDevicePackageInfo(Map<Object?, Object?>.from(entry)))
            .toList() ??
        [];
  } on MissingPluginException {
    // Headless engines do not have MainActivity's channel.
    return await packageManager.getInstalledPackages(
          flags: light ? packageInfoFlagsLight : packageInfoFlags,
        ) ??
        [];
  }
}

/// How an app about to be added will be named and drawn once saved; see
/// [AppsProviderLifecycle.newAppLook].
class NewAppLook {
  const NewAppLook({required this.name, this.icon, this.downloadedIcon});

  final String name;
  final Uint8List? icon;

  /// [icon], when it was downloaded for this and isn't stored yet. Adding the
  /// app stores it ([AppsProviderLifecycle.storeDeducedAppIcon]) rather than
  /// downloading it again.
  final Uint8List? downloadedIcon;
}

/// [app], just fetched, with how its installed version is read recorded, as
/// Add app has always saved it (see [AppsProvider.addNewListing]).
///
/// A track-only app takes its installed version from the device, or is marked
/// as not knowing its package yet. Otherwise, an app whose version can't be
/// compared with the installed one starts as up to date.
Future<App> appPreparedForAdding(App app) async {
  app.additionalSettings['useVersionCodeAsOSVersion'] =
      app.versionDetectionMode == VersionDetectionMode.versionCode;
  if (app.additionalSettings['trackOnly'] == true) {
    app = app.copyWith(installedVersion: null);
    if (isTempId(app)) {
      app.additionalSettings['trackOnlyTemporaryPackageId'] = true;
      app.additionalSettings['trackOnlyUndeterminedInstalledVersion'] = true;
    } else {
      app.additionalSettings['trackOnlyTemporaryPackageId'] = false;
      final installedInfo = await getInstalledInfo(app.id, printErr: false);
      if (installedInfo != null) {
        app = app.copyWith(
          installedVersion: app.usesVersionCodeAsOsVersion
              ? installedInfo.versionCode.toString()
              : installedInfo.versionName,
        );
        app.additionalSettings['trackOnlyUndeterminedInstalledVersion'] = false;
      } else {
        app.additionalSettings['trackOnlyUndeterminedInstalledVersion'] = true;
      }
    }
  } else if (!app.usesStandardVersionDetection) {
    app = app.copyWith(installedVersion: app.latestVersion);
  }
  return app;
}

Future<PackageInfo?> getInstalledInfo(
  String? packageName, {
  bool printErr = true,
  bool light = true,
  bool includeOwnDebugBuild = false,
  bool throwOnError = false,
}) async {
  if (packageName != null) {
    // In debug builds the running app is `<id>.debug`; when asked, try that
    // first so first-run self-add finds the locally-installed debug build.
    final List<String> namesToTry = <String>[packageName];
    if (kDebugMode && includeOwnDebugBuild && packageName == obtainiumId) {
      namesToTry.insert(0, '$obtainiumId.debug');
    }
    try {
      for (final String name in namesToTry) {
        PackageInfo? info;
        try {
          final data = await NativeFeatures._deviceAppsChannel.invokeMapMethod(
            'getInstalledPackageInfo',
            {'packageName': name, 'includeSigningCertificates': !light},
          );
          if (data != null) {
            info = decodeDevicePackageInfo(data);
          }
        } on MissingPluginException {
          // Preserve the headless-engine fallback: this pinned plugin's
          // getPackageInfo does not catch native NameNotFoundException.
          // MainActivity's worker handles absence safely and uses targeted
          // queries; without it, enumerate once for all candidate names.
          final installed = await getAllInstalledInfo(light: light);
          for (final candidate in namesToTry) {
            for (final package in installed) {
              if (package.packageName == candidate) return package;
            }
          }
          return null;
        }
        if (info != null) return info;
      }
    } catch (e) {
      if (printErr) {
        debugPrint('getInstalledInfo($packageName): $e');
      }
      if (throwOnError) rethrow;
    }
  }
  return null;
}

/// Snapshot of a package's install state, taken before an install so that
/// [waitForPackageInstall] can later tell whether the install landed.
class InstallBaseline {
  final bool wasInstalled;
  final int? updateTime;
  const InstallBaseline(this.wasInstalled, this.updateTime);
}

/// Captures the current install state of [appId] to compare against later.
Future<InstallBaseline> captureInstallBaseline(String appId) async {
  final info = await getInstalledInfo(appId);
  return InstallBaseline(info != null, info?.lastUpdateTime);
}

/// Polls for an install that can't report completion synchronously (a silent
/// background install, or a hand-off to an external installer). Returns true as
/// soon as the package appears (when it wasn't installed before) or its update
/// timestamp changes relative to [baseline] — a version-agnostic signal that
/// also works with pseudo-versions — or false if neither happens within
/// [attempts] × [interval].
Future<bool> waitForPackageInstall(
  String appId,
  InstallBaseline baseline, {
  required int attempts,
  Duration interval = const Duration(milliseconds: 500),
}) async {
  for (var attempt = 0; attempt < attempts; attempt++) {
    final info = await getInstalledInfo(appId);
    if (info != null) {
      if (!baseline.wasInstalled) return true;
      final updateTimeAfter = info.lastUpdateTime;
      if (baseline.updateTime == null ||
          (updateTimeAfter != null && updateTimeAfter != baseline.updateTime)) {
        return true;
      }
    }
    await Future.delayed(interval);
  }
  return false;
}

Future<Directory> getAppStorageDir() async {
  try {
    final extDir = await getExternalStorageDirectory();
    if (extDir != null) {
      if (!extDir.existsSync()) {
        extDir.createSync(recursive: true);
      }
      return extDir;
    }
  } catch (_) {}
  return await getApplicationDocumentsDirectory();
}

/// The listing in [listings] that already tracks [app]'s package from the same
/// store, or null when that store is free.
///
/// The same package from a *different* store is allowed, so this - not the
/// package ID alone - is what decides whether adding, renaming, or swapping an
/// app would duplicate a listing. [ignoreKey] drops one listing from the
/// comparison, for when an existing listing is being edited and so must not
/// collide with itself.
///
/// Only [ignoreKey] excuses a listing: an app being *added* carries no listing
/// ID yet, so its key is the bare package ID, which is also the key of the
/// package's first listing. Excusing that key implicitly (rather than only when
/// a caller asks for it) hid the one listing every duplicate add collides with,
/// so re-adding an already tracked store silently created a second record.
AppInMemory? sameStoreListingIn(
  AppListings listings,
  App app, {
  String? ignoreKey,
}) {
  final String storeIdentity = storeIdentityForApp(app);
  for (final AppInMemory listing in listings.listingsForPackage(app.id)) {
    if (ignoreKey != null && listing.listingKey == ignoreKey) continue;
    if (storeIdentityForApp(listing.app) == storeIdentity) return listing;
  }
  return null;
}

/// Returns [app] carrying the listing ID it should be stored under in
/// [listings].
///
/// The first listing of a package keeps a null listing ID (key = package ID).
/// Any further store for that package gets a stable `package@Source` ID,
/// suffixed if that is somehow taken, so the two records never collide.
App allocateListingIdIn(AppListings listings, App app) {
  if (app.listingId != null) return app;
  if (!listings.containsListingKey(app.id)) return app;
  final String base = appListingKey(app.id, sourceIdentifierForApp(app));
  if (!listings.containsListingKey(base)) return app.copyWith(listingId: base);
  for (int suffix = 2; ; suffix++) {
    final String candidate = '$base$appListingKeySeparator$suffix';
    if (!listings.containsListingKey(candidate)) {
      return app.copyWith(listingId: candidate);
    }
  }
}

/// Null requests a full reconciliation; an empty list means no reload work.
List<String>? appIdsForResumeReload({
  required DateTime now,
  required DateTime? lastFullLoad,
  required bool diskChanged,
  required bool backgroundSaved,
  required List<String>? changedPackages,
  required Set<String> trackedIds,
}) {
  if (backgroundSaved ||
      diskChanged ||
      changedPackages == null ||
      lastFullLoad == null ||
      now.difference(lastFullLoad) >=
          AppsProvider.fullResumeReconciliationInterval) {
    return null;
  }
  return changedPackages.toSet().where(trackedIds.contains).toList();
}

class AppsProvider with ChangeNotifier {
  // Static, app-lifetime cross-instance save-notification bus; intentionally
  // never closed. The foreground instance subscribes so it can detect saves
  // made by background tasks and reload as needed.
  // ignore: close_sinks
  static final StreamController<void> _eventsController =
      StreamController<void>.broadcast();

  // In memory App state (should always be kept in sync with local storage versions)
  final AppListings apps = AppListings();
  bool loadingApps = false;

  // Active per-app download cancellation tokens, keyed by app ID.
  final Map<String, CancellationToken> _downloadCancellations = {};

  /// UI-owned pre-handoff gates survive route changes via provider state.
  final InstallPrecommitRegistry _installPrecommit = InstallPrecommitRegistry();
  /// Native pending sessions survive a killed Flutter process.
  final Map<String, String> recoveredNativeInstallIds = {};
  /// Terminal uncertainty must never masquerade as a cancellable session.
  final Set<String> uncertainNativeInstallListings = <String>{};

  bool isNativeInstallOutcomeUncertain(String listingKey) =>
      uncertainNativeInstallListings.contains(listingKey);

  /// Non-null when the provider failed to initialize. Callers can check this
  /// before assuming the provider is in a usable state.
  String? initError;

  /// Non-null while a [checkUpdates] batch is in flight. Serves as both an
  /// atomic guard (preventing concurrent batches) and a deduplication
  /// mechanism: subsequent callers receive the existing completer's future.
  Completer<List<App>>? updateCheckCompleter;
  final ValueNotifier<double?> refreshProgressNotifier = ValueNotifier(null);
  double? get refreshProgress => refreshProgressNotifier.value;
  set refreshProgress(double? value) => refreshProgressNotifier.value = value;
  LogsProvider logs = LogsProvider();

  int _cachedPendingUpdateCount = 0;
  bool _pendingUpdateCountDirty = true;
  int appsListRevision = 0;

  // Serializes concurrent loadApps() calls without busy-waiting.
  Completer<void>? appsLoadingCompleter;

  // Completes once the launch-time loadApps() has run, or init has finished or
  // failed without one. See [waitForInitialLoad].
  final Completer<void> _initialLoadDone = Completer<void>();

  // Coalesces bursts of saveApps()/removeApps() into a single auto-export.
  Timer? _autoExportDebounce;
  DateTime? _autoExportFirstPendingAt;
  bool _autoExportRunning = false;

  // Set in dispose() to guard against deferred callbacks running post-disposal.
  bool _disposed = false;

  // Tracks whether a background save occurred since the last load.
  bool _needsBgReload = false;
  StreamSubscription<void>? _eventSubscription;

  // Variables to keep track of the app foreground status (installs can't run in the background)
  bool isForeground = true;
  bool _isBg = false;
  int _foregroundResumeGeneration = 0;

  /// Watermark used by incremental full-directory loads. Public so the
  /// lifecycle extension can reuse unchanged JSON files across resumes.
  DateTime? lastFullDiskLoadAt;
  DateTime? appDirectoryModifiedAt;
  DateTime? appCheckStoreModifiedAt;
  static const fullResumeReconciliationInterval = Duration(minutes: 5);

  /// Whether this provider runs in the background (WorkManager) isolate rather
  /// than the main UI isolate.
  bool get isBg => _isBg;
  Stream<FGBGType>? foregroundStream;
  StreamSubscription<FGBGType>? foregroundSubscription;
  late final SettingsProvider settingsProvider;
  Directory? _apkDir;
  Directory? _iconsCacheDir;
  Directory? _userAppIconsDir;
  Directory? _deducedAppIconsDir;
  Directory? cachedAppsDir;
  AppCheckStore? appCheckStore;

  // Per-app-detail-page transient error banners, keyed by app ID. Populated by
  // [setAppPageError]/[clearAppPageError]; read by the app detail page.
  final Map<String, ({String? title, String message})> appPageErrors = {};

  // Detail-page auto-check bookkeeping (see AppsProviderUpdates'
  // tryBeginDetailPageAutoCheck / finishDetailPageAutoCheck). Public so the
  // updates extension can reach them across library files.
  final Set<String> detailPageAutoChecksInFlight = <String>{};
  final Map<String, DateTime> lastDetailPageAutoCheckStartedAt =
      <String, DateTime>{};

  // Deferred "remove from ObtainX" (no uninstall) bookkeeping. The JSON is
  // stashed under app_data/pending_removal, the UI updates immediately, and the
  // disk purge fires after a short delay unless the user undoes it. Public so
  // the lifecycle extension can reach them across library files.
  final Map<String, Timer> deferredObtainiumTimers = {};
  final Map<String, AppInMemory> deferredObtainiumSnapshots = {};

  // Apps handed to a third-party installer that returned without confirming the
  // install. Each timer only bounds how long the row keeps showing "Installing"
  // so a dismissed installer can't leave it spinning forever - it is purely
  // cosmetic. Confirmation arrives on the system package broadcast and never
  // waits on these. Public so the install extension can reach them.
  final Map<String, Timer> thirdPartyInstallIndicatorTimers = {};

  Directory get apkDir {
    if (_apkDir == null) {
      throw StateError(
        'apkDir not initialized - wait for async init to complete',
      );
    }
    return _apkDir!;
  }

  Directory get iconsCacheDir {
    if (_iconsCacheDir == null) {
      throw StateError(
        'iconsCacheDir not initialized - wait for async init to complete',
      );
    }
    return _iconsCacheDir!;
  }

  /// User-chosen PNG icon overrides. Lives under app storage (not [iconsCacheDir])
  /// so it survives Android "clear cache".
  Directory get userAppIconsDir {
    if (_userAppIconsDir == null) {
      throw StateError(
        'userAppIconsDir not initialized - wait for async init to complete',
      );
    }
    return _userAppIconsDir!;
  }

  /// Icons deduced for apps whose source publishes none: extracted from a
  /// downloaded APK, or fetched from another store's listing. Lives under app
  /// storage (not [iconsCacheDir]) because re-deriving one costs a download or
  /// a network round-trip, so Android "clear cache" must not wipe it.
  Directory get deducedAppIconsDir {
    if (_deducedAppIconsDir == null) {
      throw StateError(
        'deducedAppIconsDir not initialized - wait for async init to complete',
      );
    }
    return _deducedAppIconsDir!;
  }

  /// Count of installed apps with an actionable or attention-needed update.
  /// Data mutations invalidate the cache; download/icon progress notifications
  /// do not need to rescan the entire collection.
  int get pendingUpdateCount {
    if (_pendingUpdateCountDirty) {
      _cachedPendingUpdateCount = findExistingUpdates(
        installedOnly: true,
        excludeOnDemandOnly: true,
        includeVersionOrderUncertain: true,
      ).length;
      _pendingUpdateCountDirty = false;
    }
    return _cachedPendingUpdateCount;
  }

  void markAppsChanged() {
    appsListRevision++;
    _pendingUpdateCountDirty = true;
    // Any change to the app set or its check timestamps invalidates the cached
    // due time; the next background wake-up recomputes it from the real apps.
    settingsProvider.bgNextCheckDue = null;
  }

  /// Records a transient error banner for [appId]'s detail page.
  void setAppPageError(String appId, Object error, {String? title}) {
    appPageErrors[appId] = (title: title, message: error.toString());
    notifyListeners();
  }

  /// Clears any transient error banner for [appId]'s detail page.
  void clearAppPageError(String appId) {
    if (appPageErrors.remove(appId) != null) {
      notifyListeners();
    }
  }

  Iterable<AppInMemory> getAppValues() {
    _reloadIfBgSaved();
    return apps.values;
  }

  void _reloadIfBgSaved() {
    if (!_needsBgReload) return;
    _needsBgReload = false;
    loadApps().catchError((e) {
      unawaited(
        logs.add(
          'Reload after background save failed: $e',
          level: LogLevel.error,
        ),
      );
    });
  }

  Future<void> refreshAppsOnResume() async {
    await waitForAppsToLoad();
    final directory = await getAppsDir();
    final modified = (await directory.stat()).modified;
    final checkStoreModified = await appCheckStore?.modified();
    List<String>? changedPackages;
    try {
      changedPackages = await NativeFeatures._deviceAppsChannel
          .invokeListMethod<String>('consumePackageChanges');
    } on MissingPluginException {
      // Older native hosts and background engines retain full reconciliation.
    } on PlatformException {
      // A failed journal read is not evidence that no packages changed.
    }
    final reloadIds = appIdsForResumeReload(
      now: DateTime.now(),
      lastFullLoad: lastFullDiskLoadAt,
      diskChanged:
          appDirectoryModifiedAt != modified ||
          appCheckStoreModifiedAt != checkStoreModified,
      backgroundSaved: _needsBgReload,
      changedPackages: changedPackages,
      trackedIds: apps.values.map((listing) => listing.app.id).toSet(),
    );
    try {
      if (reloadIds == null) {
        _needsBgReload = false;
        await loadApps(silent: true);
        return;
      }
      for (final id in reloadIds) {
        await loadApps(singleId: id, silent: true);
      }
    } catch (_) {
      // The native journal was consumed. Retry with a full scan next time.
      _needsBgReload = true;
      rethrow;
    }
  }

  /// Public wrapper around the protected [notifyListeners] so the provider's
  /// part-file extensions can request listeners to rebuild.
  void notify() => notifyListeners();

  /// Registers a cancellation token for an in-flight download of [appId].
  CancellationToken registerDownloadCancellation(String appId) {
    final token = CancellationToken();
    _downloadCancellations[appId] = token;
    return token;
  }

  /// Clears the cancellation token once a download of [appId] finishes.
  void clearDownloadCancellation(String appId) {
    _downloadCancellations.remove(appId);
  }

  /// Requests cancellation of an ongoing download for [appId], if any.
  void cancelDownload(String appId) {
    _downloadCancellations[appId]?.cancel();
    final entry = apps[appId];
    if (entry != null && entry.downloadProgress != null) {
      entry.downloadProgress = null;
    }
    notify();
  }

  /// The UI can cancel while preparing, but never claim cancellation
  /// after the platform handoff is sealed. The previous package is untouched
  /// when a pre-handoff cancellation is accepted.
  bool canCancelInstallPreparation(String listingKey) =>
      _installPrecommit.canCancel(listingKey) ||
      recoveredNativeInstallIds.containsKey(listingKey);

  InstallPrecommitGate beginInstallPreparation(String listingKey) {
    final gate = _installPrecommit.begin(listingKey);
    notify();
    return gate;
  }

  bool cancelInstallPreparation(String listingKey) {
    if (_installPrecommit.requestCancel(listingKey)) {
      notify();
      return true; // Request accepted; Android may still report UNKNOWN.
    }
    final id = recoveredNativeInstallIds[listingKey];
    if (id == null) return false;
    // Hide the button during this request; restore only on UNKNOWN.
    recoveredNativeInstallIds.remove(listingKey);
    notify();
    unawaited(_cancelRecoveredInstall(listingKey, id));
    return true;
  }

  Future<void> _cancelRecoveredInstall(String listingKey, String id) async {
    String status = 'unknown';
    try {
      status = await R02fP03CancellableStock.instance.cancelRecovered(id);
    } catch (error) {
      unawaited(logs.add('P03 recovered cancel uncertain: $error'));
    }
    final entry = apps[listingKey];
    if (entry == null) return;
    if (status == 'cancelled') {
      uncertainNativeInstallListings.remove(listingKey);
      final pending = InstallReleaseSnapshot.fromJson(
        entry.app.additionalSettings[pendingInstallReleaseKey],
      );
      if (pending != null) {
        entry.app = discardPendingInstall(entry.app, pending);
        await saveApps([entry.app], attemptToCorrectInstallStatus: false);
      }
      if (entry.downloadProgress == -5) entry.downloadProgress = null;
    } else {
      // A session may already be committed or abandoned, making cancellation
      // impossible. Preserve its pending receipt without claiming success.
      try {
        final active = await R02fP03CancellableStock.instance.pending();
        if (active?['id'] == id && active?['sessionExists'] == true) {
          recoveredNativeInstallIds[listingKey] = id;
        } else {
          uncertainNativeInstallListings.add(listingKey);
          if (entry.downloadProgress == -5) entry.downloadProgress = null;
        }
      } catch (error) {
        recoveredNativeInstallIds[listingKey] = id;
        unawaited(logs.add('P03 post-cancel recovery uncertain: $error'));
      }
    }
    notify();
  }

  Future<void> recoverNativeInstallSessions() async {
    if (_isBg || _disposed) return;
    try {
      final snapshot = await R02fP03CancellableStock.instance.snapshot();
      final active = snapshot['active'] as Map<String, dynamic>?;
      final terminal = snapshot['terminal'] as Map<String, dynamic>?;
      if (terminal != null) {
        final key = terminal['listingKey']?.toString();
        if (key != null && key != active?['listingKey']?.toString() &&
            apps[key] != null &&
            terminal['outcome']?.toString() == 'unknown') {
          uncertainNativeInstallListings.add(key);
          // A finalized native session cannot be cancelled. Reconcile
          // observed installed package state separately; never clear pending
          // source/asset provenance based only on this terminal callback.
          recoveredNativeInstallIds.remove(key);
          if (apps[key]?.downloadProgress == -5) {
            apps[key]!.downloadProgress = null;
          }
          unawaited(logs.add('P03 recovery UNKNOWN for $key: independent package verification required'));
        }
      }
      if (active == null) {
        notify();
        return;
      }
      final listingKey = active['listingKey']?.toString();
      final id = active['id']?.toString();
      if (listingKey == null || id == null || apps[listingKey] == null) return;
      if (_installPrecommit.canCancel(listingKey)) return;
      if (active['sessionExists'] != true) {
        // No longer abandonable: do not keep showing a fake Cancel action.
        recoveredNativeInstallIds.remove(listingKey);
        uncertainNativeInstallListings.add(listingKey);
        if (apps[listingKey]?.downloadProgress == -5) {
          apps[listingKey]!.downloadProgress = null;
        }
        notify();
        return;
      }
      recoveredNativeInstallIds[listingKey] = id;
      final entry = apps[listingKey]!;
      entry.downloadProgress ??= -5;
      notify();
    } catch (error) {
      unawaited(logs.add('P03 restart session reconciliation inconclusive: $error'));
    }
  }

  bool sealInstallHandoff(InstallPrecommitGate? gate, {
    bool nativeCancelable = false,
  }) {
    if (gate == null) return true; // Background/direct call has no UI cancellation owner.
    final allowed = _installPrecommit.sealForHandoff(gate,
        nativeCancelable: nativeCancelable);
    notify();
    return allowed;
  }

  void endInstallPreparation(String listingKey, InstallPrecommitGate gate) {
    _installPrecommit.finish(listingKey, gate);
    notify();
  }

  /// Waits for any in-flight [loadApps] to finish, so concurrent callers
  /// serialize instead of busy-waiting on a polling loop.
  Future<void> waitForAppsToLoad() async {
    final completer = appsLoadingCompleter;
    if (completer != null) {
      await completer.future;
      await waitForAppsToLoad();
    }
  }

  /// Waits for the launch-time [loadApps], including the stretch of init
  /// before it starts, when [waitForAppsToLoad] has nothing to wait on yet.
  ///
  /// For UI entry points that can run on a cold start - a deep link above
  /// all - which would otherwise read the still-empty library as the real one.
  /// Not for anything that init itself awaits, which would deadlock.
  Future<void> waitForInitialLoad() async {
    await _initialLoadDone.future;
    await waitForAppsToLoad();
  }

  /// Schedules a debounced automatic export. Coalesces the many per-app
  /// save/remove operations that happen in bursts into a single export.
  /// No-op (cheaply returns) if auto-export is disabled inside [export].
  void scheduleAutoExport() {
    if (_disposed || !settingsProvider.autoExportOnChanges) return;
    final now = DateTime.now();
    _autoExportFirstPendingAt ??= now;
    _autoExportDebounce?.cancel();
    // Save batches arrive every three seconds during a refresh. Wait until the
    // operation finishes, but still checkpoint at least every thirty seconds.
    final remaining =
        const Duration(seconds: 30) -
        now.difference(_autoExportFirstPendingAt!);
    final delay = updateCheckCompleter == null
        ? const Duration(seconds: 2)
        : (remaining.isNegative ? Duration.zero : remaining);
    _autoExportDebounce = Timer(delay, () async {
      if (_disposed || _autoExportRunning) return;
      _autoExportFirstPendingAt = null;
      _autoExportRunning = true;
      try {
        await export(isAuto: true);
      } catch (error) {
        unawaited(
          logs.add('Auto-export failed: $error', level: LogLevel.warning),
        );
      } finally {
        _autoExportRunning = false;
        if (_autoExportFirstPendingAt != null) scheduleAutoExport();
      }
    });
  }

  void finishPendingAutoExport() {
    if (_autoExportFirstPendingAt != null) scheduleAutoExport();
  }

  AppsProvider({
    bool isBg = false,
    SettingsProvider? settingsProvider,
    LogsProvider? logsProvider,
  }) {
    _isBg = isBg;
    this.settingsProvider = settingsProvider ?? SettingsProvider();
    logs = logsProvider ?? LogsProvider();
    // Subscribe to changes in the app foreground status
    foregroundStream = FGBGEvents.instance.stream.asBroadcastStream();
    foregroundSubscription = foregroundStream?.listen((event) async {
      isForeground = event == FGBGType.foreground;
      final generation = ++_foregroundResumeGeneration;
      if (isForeground) {
        await Future<void>.delayed(const Duration(milliseconds: 300));
        if (!isForeground ||
            _disposed ||
            generation != _foregroundResumeGeneration) {
          return;
        }
        try {
          await refreshAppsOnResume();
        } catch (error) {
          _needsBgReload = true;
          unawaited(
            logs.add(
              'Foreground reconciliation failed: $error',
              level: LogLevel.warning,
            ),
          );
        }
      }
    });
    if (!_isBg) {
      _eventSubscription = _eventsController.stream.listen((_) {
        _needsBgReload = true;
      });
      // Let the download notification's Cancel action reach this provider,
      // including taps routed through the FLN background isolate.
      NativeFeatures.registerDownloadCancelHandler(cancelDownload);
      NotificationsProvider.onDownloadCancelRequested = cancelDownload;
      NotificationsProvider.listenForDownloadCancelFromMain();
      // Let the download-complete notification's Install action hand the
      // release asset it just downloaded off to the system installer.
      NotificationsProvider.onInstallDownloadedFileRequested =
          installDownloadedAssetFile;
      // Record third-party installs as soon as the system confirms them, instead
      // of only when the handoff session manages to report success (#222).
      listenForThirdPartyInstallResults();
    }
    () async {
      await this.settingsProvider.initializeSettings();
      var useExternalCache = false;
      try {
        final cacheDirs = await getExternalCacheDirectories();
        if (cacheDirs?.isNotEmpty ?? false) {
          _apkDir = cacheDirs!.first;
          _iconsCacheDir = Directory('${cacheDirs.first.path}/icons');
          if (!_iconsCacheDir!.existsSync()) {
            _iconsCacheDir!.createSync();
          }
          useExternalCache = true;
        }
      } catch (_) {}
      if (!useExternalCache) {
        _apkDir = Directory('${(await getAppStorageDir()).path}/apks');
        if (!_apkDir!.existsSync()) {
          _apkDir!.createSync();
        }
        _iconsCacheDir = Directory('${(await getAppStorageDir()).path}/icons');
        if (!_iconsCacheDir!.existsSync()) {
          _iconsCacheDir!.createSync();
        }
      }
      _userAppIconsDir = Directory(
        '${(await getAppStorageDir()).path}/user_icons',
      );
      if (!_userAppIconsDir!.existsSync()) {
        _userAppIconsDir!.createSync(recursive: true);
      }
      _deducedAppIconsDir = Directory(
        '${(await getAppStorageDir()).path}/deduced_icons',
      );
      if (!_deducedAppIconsDir!.existsSync()) {
        _deducedAppIconsDir!.createSync(recursive: true);
      }
      if (!isBg) {
        await loadApps();
        _completeInitialLoad();
        // One-shot legacy user-icon migration: kept OFF the cold-start critical
        // path so it never delays the first app-list render. It also self-skips
        // on later launches via a prefs flag (see the method).
        unawaited(migrateUserIconsFromLegacyCacheDir());
        final cutoff = DateTime.now().subtract(const Duration(days: 7));
        await for (var entity in apkDir.list()) {
          if (entity is File &&
              entity.path.endsWith('.part') &&
              (await entity.stat()).modified.isBefore(cutoff)) {
            if (!areDownloadsRunning()) {
              await entity.delete();
            }
          }
        }
      } else {
        await migrateUserIconsFromLegacyCacheDir();
      }
      _completeInitialLoad();
    }().catchError((e) {
      initError = e.toString();
      _completeInitialLoad();
      unawaited(
        logs.add('AppsProvider async init error: $e', level: LogLevel.error),
      );
    });
  }

  void _completeInitialLoad() {
    if (!_initialLoadDone.isCompleted) _initialLoadDone.complete();
  }

  @override
  void dispose() {
    _disposed = true;
    foregroundSubscription?.cancel();
    _autoExportDebounce?.cancel();
    _eventSubscription?.cancel();
    if (!_isBg) {
      stopListeningForThirdPartyInstallResults();
    }
    for (final Timer timer in deferredObtainiumTimers.values) {
      timer.cancel();
    }
    deferredObtainiumTimers.clear();
    for (final Timer timer in thirdPartyInstallIndicatorTimers.values) {
      timer.cancel();
    }
    thirdPartyInstallIndicatorTimers.clear();
    refreshProgressNotifier.dispose();
    // Pending JSON under app_data/pending_removal is intentionally left on disk;
    // the next loadApps commits the removal for any id without a live deferral.
    super.dispose();
  }

  /// Returns [app] carrying the listing ID it should be stored under in the
  /// library; see [allocateListingIdIn].
  App withAllocatedListingId(App app) => allocateListingIdIn(apps, app);

  Future<List<List<String>>> addAppsByURL(
    List<String> urls, {
    AppSource? sourceOverride,
  }) async {
    final List<dynamic> results = await SourceProvider().getAppsByURLNaive(
      urls,
      alreadyAddedUrls: apps.values.map((e) => e.app.url).toSet(),
      sourceOverride: sourceOverride,
      includePrereleases: settingsProvider.includePrereleasesByDefault,
    );
    final List<App> pps = results[0];
    final Map<String, dynamic> errorsMap = results[1];
    for (var app in pps) {
      if (sameStoreListingIn(apps, app) != null) {
        errorsMap.addAll({app.id: tr('appAlreadyAdded')});
      } else {
        await saveApps([withAllocatedListingId(app)], onlyIfExists: false);
      }
    }
    final List<List<String>> errors = errorsMap.keys
        .map((e) => [e, errorsMap[e].toString()])
        .toList();
    return errors;
  }

  /// Saves [app], just fetched by [SourceProvider.getApp], as a new listing,
  /// and returns it as saved. Add app's own steps, shared so that every way of
  /// adding an app ends the same: [appPreparedForAdding], then saved under its
  /// own listing ID and put in any matching smart folders.
  Future<App> addNewListing(App app) async {
    // Tracking this package from a second store needs its own listing ID
    // so the two records never overwrite each other.
    app = withAllocatedListingId(await appPreparedForAdding(app));
    await saveApps([app], onlyIfExists: false);
    final App? liveApp = apps[app.listingKey]?.app;
    if (liveApp != null) {
      await assignMatchingFoldersToAppIfNeeded(liveApp);
    }
    return app;
  }

  /// Saves apps already fetched for an add ([SourceProvider.getAppByURLNaive])
  /// through [addNewListing], skipping any whose store listing is tracked by
  /// now. Returns those saved.
  ///
  /// [downloadedIcons], by package ID, are the icons already downloaded to
  /// show them ([NewAppLook.downloadedIcon]); they're kept as the apps' icons
  /// instead of being downloaded again.
  Future<List<App>> addFetchedApps(
    List<App> fetched, {
    Map<String, Uint8List> downloadedIcons = const {},
  }) async {
    final List<App> added = [];
    for (final App app in fetched) {
      if (sameStoreListingIn(apps, app) != null) continue;
      final App listing = await addNewListing(app);
      final Uint8List? icon = downloadedIcons[listing.id];
      if (icon != null) await storeDeducedAppIcon(listing.id, icon);
      added.add(listing);
    }
    return added;
  }
}

/// The WorkManager constraints every background task runs under, from the
/// user's Wi-Fi-only and charging-only settings.
Constraints _bgTaskConstraints(SettingsProvider settings) => Constraints(
  networkType: settings.bgUpdatesOnWiFiOnly
      ? NetworkType.unmetered
      : NetworkType.connected,
  requiresCharging: settings.bgUpdatesWhileChargingOnly,
  requiresBatteryNotLow: false,
  requiresDeviceIdle: false,
  requiresStorageNotLow: false,
);

/// Installs [appIds] silently, and returns whether any of them is still
/// waiting afterwards (postponed because the screen is on, or failed), so the
/// next wake-up tries again.
Future<bool> _runBGInstallMode(
  List<String> appIds,
  AppsProvider appsProvider,
  NotificationsProvider notificationsProvider,
  LogsProvider logs,
) async {
  unawaited(logs.add('BG install task: Started.'));
  if (appIds.isEmpty) {
    unawaited(logs.add('BG install task: No pending installs.'));
    return false;
  }
  if (await NativeFeatures.isDeviceInteractive()) {
    unawaited(
      logs.add(
        'BG install task: Device is active (screen on). Postponing background installations.',
      ),
    );
    return true;
  }
  unawaited(
    logs.add('BG install task: Installing ${appIds.length} apps silently.'),
  );
  bool failed = false;
  try {
    await appsProvider.downloadAndInstallLatestApps(
      appIds,
      null,
      notificationsProvider: notificationsProvider,
      forceParallelDownloads: true,
    );
  } catch (e) {
    if (e is MultiAppMultiError) {
      // The apps that did install are no longer pending, so the next wake-up
      // attempts only the ones that failed.
      failed = true;
      e.idsByErrorString.forEach((key, value) {
        final String failure = e.errorsAppsString(key, value);
        // Logged as well as notified: otherwise a failed download reads as a
        // clean "Done installing updates" in the log (#317).
        unawaited(
          logs.add(
            'BG install task: Failed: $failure',
            level: LogLevel.warning,
          ),
        );
        unawaited(
          notificationsProvider.notify(
            ErrorInstallingUpdatesNotification(failure),
          ),
        );
      });
    } else {
      unawaited(logs.add('Fatal error in BG install task: ${e.toString()}'));
      rethrow;
    }
  }
  unawaited(logs.add('BG install task: Done installing updates.'));
  return failed;
}

/// Background update check and installation orchestrator.
///
/// In "update mode" (toCheck is non-empty): checks [toCheck] apps in parallel,
/// notifies the user of any non-silent updates, and retries failed checks.
///
/// In "install mode" (toCheck is empty): downloads and silently installs all
/// pending updates, placing Obtainium last in the install queue.
Future<void> bgUpdateCheck(
  String taskId,
  Map<String, dynamic>? params, {
  LogsProvider? logs,
  NotificationsProvider? notifs,
  SettingsProvider? settings,
  bool forceAll = false,
}) async {
  final bgLogs = logs ?? LogsProvider();
  WidgetsFlutterBinding.ensureInitialized();
  params ??= {};
  final SettingsProvider settingsProvider = settings ?? SettingsProvider();
  await settingsProvider.initializeSettings();
  if (!forceAll && r11InQuietHours(DateTime.now(), settingsProvider.r11QuietStart,
      settingsProvider.r11QuietEnd)) {
    unawaited(bgLogs.add('R11 automatic work postponed: quiet hours.'));
    return;
  }

  // This task wakes every 15 minutes, not once per update interval, so most
  // wake-ups have nothing to do: no check is due and no background install is
  // waiting (see [bgNextCheckDue], cleared while one is). Deciding that first,
  // before loading translations or any app record, keeps those wake-ups to a
  // settings read and one log line. Skipping the app records also avoids the
  // check timestamp database, whose contention made a concurrent foreground
  // load wait on a lock. An explicit request (manual check, or a retry carrying
  // its own list) always proceeds.
  final DateTime? nextDue = settingsProvider.bgNextCheckDue;
  if (!forceAll &&
      params['toCheck'] == null &&
      nextDue != null &&
      DateTime.now().isBefore(nextDue)) {
    unawaited(
      bgLogs.add('BG task $taskId: Nothing due before $nextDue; skipped.'),
    );
    return;
  }

  await EasyLocalization.ensureInitialized();
  await TranslationLoader.load();
  unawaited(bgLogs.add('BG task started $taskId: $params'));

  final NotificationsProvider notificationsProvider =
      notifs ?? NotificationsProvider();
  final AppsProvider appsProvider = AppsProvider(
    isBg: true,
    settingsProvider: settingsProvider,
    logsProvider: bgLogs,
  );

  await appsProvider.loadApps();

  final netResult = await (Connectivity().checkConnectivity());
  if (netResult.contains(ConnectivityResult.none) ||
      netResult.isEmpty ||
      (netResult.contains(ConnectivityResult.vpn) && netResult.length == 1)) {
    unawaited(bgLogs.add('BG update task: No network.'));
    return;
  }

  if (appsProvider.settingsProvider.updateInterval == 0) {
    if (!forceAll) {
      unawaited(bgLogs.add('BG update task: Skipped (interval=0)'));
      return;
    }
    unawaited(
      bgLogs.add(
        'BG update task: Running manual check despite disabled settings',
      ),
    );
  }

  final List<MapEntry<String, int>> toCheck = <MapEntry<String, int>>[
    ...(params['toCheck']
            ?.map(
              (entry) => MapEntry<String, int>(
                entry['key'] as String,
                entry['value'] as int,
              ),
            )
            .toList() ??
        appsProvider
            .getAppsSortedByUpdateCheckTime(
              onlyCheckInstalledOrTrackOnlyApps: appsProvider
                  .settingsProvider
                  .onlyCheckInstalledOrTrackOnlyApps,
              forceAll: forceAll,
            )
            .map((e) => MapEntry(e, 0))),
  ];

  final networkRestricted =
      appsProvider.settingsProvider.bgUpdatesOnWiFiOnly &&
      !netResult.contains(ConnectivityResult.wifi) &&
      !netResult.contains(ConnectivityResult.ethernet);

  // "While charging" means plugged in. A phone plugged in at 100% reports
  // full, and one held at a charge limit (Samsung's "Protect battery", say)
  // reports connectedNotCharging; neither is actively charging, and treating
  // them as unplugged meant installs never ran overnight.
  final chargingRestricted =
      appsProvider.settingsProvider.bgUpdatesWhileChargingOnly &&
      !const {
        BatteryState.charging,
        BatteryState.full,
        BatteryState.connectedNotCharging,
      }.contains(await Battery().batteryState);

  if (networkRestricted) {
    unawaited(bgLogs.add('BG update task: Network restriction in effect.'));
  }

  if (chargingRestricted) {
    unawaited(bgLogs.add('BG update task: Charging restriction in effect.'));
  }

  if (!forceAll) {
    if (networkRestricted || chargingRestricted) {
      unawaited(bgLogs.add('R11 automatic work postponed: network or charging restriction.'));
      await appsProvider.appCheckStore?.close();
      return;
    }
    try {
      if (!await r11ClaimAutomaticRun(settingsProvider.r11RateMinutes, DateTime.now())) {
        unawaited(bgLogs.add('R11 automatic work postponed: minimum interval.'));
        await appsProvider.appCheckStore?.close();
        return;
      }
    } catch (_) {
      unawaited(bgLogs.add('R11 automatic work postponed: scheduling policy unavailable.'));
      await appsProvider.appCheckStore?.close();
      return;
    }
  }
  final canInstall = !networkRestricted && !chargingRestricted;
  final silentlyInstallable = <String>[];

  if (toCheck.isNotEmpty) {
    final result = await _bgRunUpdateCheck(
      taskId,
      toCheck,
      appsProvider,
      notificationsProvider,
      bgLogs,
    );

    final List<App> trackOnlyToNotify = [];
    final List<App> toNotify = [];
    final List<App> reviewToNotify = [];
    for (var i = 0; i < result.updates.length; i++) {
      // checkUpdates reports "the source's version string changed", not "the
      // device is behind". Re-read the post-save app so the verdict is computed
      // from the same state the app list renders, then apply the shared update
      // predicate: without it a version reformat notifies (and silently
      // installs) an update the UI itself does not show.
      final App update =
          appsProvider.apps[result.updates[i].id]?.app ?? result.updates[i];
      final bool installable = appUpdateIsUserVisible(update);
      final bool notifiable = appUpdateIsUserVisible(
        update,
        includeVersionOrderUncertain: true,
      );
      if (!installable && !notifiable) {
        unawaited(
          bgLogs.add(
            'BG update task: ${update.id} version string changed '
            '(${update.installedVersion} → ${update.latestVersion}) but no update '
            'is available for the installed build; not notifying or installing.',
          ),
        );
        continue;
      }
      if (!installable) {
        if (!update.settings.getBool('skipUpdateNotifications')) {
          reviewToNotify.add(update);
        }
        continue;
      }
      final willInstallInBackground = await appsProvider
          .canInstallSilentlyInBackground(update);
      if (!canInstall || !willInstallInBackground) {
        if (notifiable && !update.settings.getBool('skipUpdateNotifications')) {
          unawaited(
            bgLogs.add(
              'BG update task notifying for ${update.id} (canInstall $canInstall, canInstallSilentlyInBackground $willInstallInBackground).',
            ),
          );
          if (update.settings.getBool('trackOnly')) {
            trackOnlyToNotify.add(update);
          } else {
            toNotify.add(update);
          }
        }
      } else {
        silentlyInstallable.add(update.id);
      }
    }

    if (toNotify.isNotEmpty) {
      unawaited(notificationsProvider.notify(UpdateNotification(toNotify)));
    }
    if (trackOnlyToNotify.isNotEmpty) {
      unawaited(
        notificationsProvider.notify(
          TrackOnlyUpdateNotification(trackOnlyToNotify),
        ),
      );
    }
    if (reviewToNotify.isNotEmpty) {
      unawaited(
        notificationsProvider.notify(VersionReviewNotification(reviewToNotify)),
      );
    }

    unawaited(
      bgLogs.add(
        'BG update task: Notified ${toNotify.length} updates, '
        '${trackOnlyToNotify.length} track-only, '
        '${reviewToNotify.length} releases needing review, '
        '${result.toThrow.rawErrors.length} errors',
      ),
    );

    if (result.toThrow.rawErrors.isNotEmpty && result.errors != null) {
      for (var element in result.toThrow.idsByErrorString.entries) {
        unawaited(
          notificationsProvider.notify(
            ErrorCheckingUpdatesNotification(
              result.errors!.errorsAppsString(element.key, element.value),
              id:
                  errorCheckingUpdatesNotificationId +
                  100 +
                  Random().nextInt(9900),
            ),
          ),
        );
      }
    }
  } else {
    unawaited(bgLogs.add('BG update task: No apps due for checking.'));
  }
  if (canInstall && params['toCheck'] == null) {
    final discovered = appsProvider.findExistingUpdates(
      installedOnly: true,
      excludeOnDemandOnly: true,
    );
    final existing = silentlyInstallable.toSet();
    for (final id in discovered) {
      if (existing.contains(id)) continue;
      if (await appsProvider.canInstallSilentlyInBackground(
        appsProvider.apps[id]!.app,
      )) {
        silentlyInstallable.add(id);
      }
    }
    unawaited(
      bgLogs.add(
        'BG install task: Found ${silentlyInstallable.length} apps to install (${existing.length} from checks, ${silentlyInstallable.length - existing.length} pre-existing).',
      ),
    );
  }
  // Whether a background install is still waiting after this run: one that
  // failed or was postponed for the screen, or one held back by the charging or
  // Wi-Fi limit. That last case is the foreground service's: WorkManager does
  // not start this task until both limits are met.
  final bool installStillAllowed = canInstall &&
      ((forceAll || !r11InQuietHours(DateTime.now(), settingsProvider.r11QuietStart, settingsProvider.r11QuietEnd)) &&
       (!settingsProvider.bgUpdatesOnWiFiOnly || (await Connectivity().checkConnectivity()).any(
           (network) => network == ConnectivityResult.wifi || network == ConnectivityResult.ethernet)) &&
       (!settingsProvider.bgUpdatesWhileChargingOnly || const {BatteryState.charging,
         BatteryState.full, BatteryState.connectedNotCharging}.contains(await Battery().batteryState)));
  if (canInstall && !installStillAllowed) {
    unawaited(bgLogs.add('R11 automatic installation postponed: policy changed during check.'));
  }
  final bool installWaiting = installStillAllowed
      ? await _runBGInstallMode(
          silentlyInstallable,
          appsProvider,
          notificationsProvider,
          bgLogs,
        )
      : appsProvider
            .findExistingUpdates(installedOnly: true, excludeOnDemandOnly: true)
            .isNotEmpty;
  // A retry carrying its own list never looked at the other pending installs,
  // so it leaves the due time as its saves left it (cleared) and the next
  // wake-up works it out in full.
  if (params['toCheck'] == null) {
    // Recorded after every save this run has made, so the next wake-up can
    // skip its load. Cleared by [AppsProvider.markAppsChanged] on any later
    // change, and left clear while an install is waiting, so the next wake-up
    // tries it again rather than the next due check (#317). A run Android
    // stops midway never gets here, so the due time stays clear or already past
    // and the next wake-up runs too, resuming the partial downloads where the
    // server allows it.
    appsProvider.settingsProvider.bgNextCheckDue = installWaiting
        ? null
        : appsProvider.earliestNextUpdateCheckDue();
  }
  // This engine is about to go away, so close its own connection rather than
  // leave it open for the life of the process. Closing is only safe because
  // each engine has a connection of its own (see [AppCheckStore]): a shared
  // one closed the UI isolate's too (#317).
  await appsProvider.appCheckStore?.close();
  unawaited(bgLogs.add('BG task completed $taskId.'));
  AppsProvider._eventsController.add(null);
}

Future<
  ({List<App> updates, MultiAppMultiError? errors, MultiAppMultiError toThrow})
>
_bgRunUpdateCheck(
  String taskId,
  List<MapEntry<String, int>> toCheck,
  AppsProvider appsProvider,
  NotificationsProvider notificationsProvider,
  LogsProvider logs,
) async {
  unawaited(logs.add('BG update task: Started (${toCheck.length}).'));

  List<App> updates = [];
  final List<MapEntry<String, int>> toRetry = [];
  var retryAfterXSeconds = 0;
  MultiAppMultiError? errors;
  final MultiAppMultiError toThrow = MultiAppMultiError();
  final CheckingUpdatesNotification notif = CheckingUpdatesNotification(
    plural('apps', toCheck.length),
  );

  try {
    unawaited(notificationsProvider.notify(notif, cancelExisting: true));
    updates = await appsProvider.checkUpdates(
      specificIds: toCheck.map((e) => e.key).toList(),
      sp: appsProvider.settingsProvider,
    );
  } catch (e) {
    if (e is CheckUpdatesException) {
      updates = e.updates;
      errors = e.errors;
      errors.rawErrors.forEach((key, err) {
        unawaited(
          logs.add(
            'BG update task: Got error on checking for $key \'${err.toString()}\'.',
          ),
        );

        final toCheckApp = toCheck.firstWhere(
          (element) => element.key == key,
          orElse: () => MapEntry(key, 0),
        );
        if (toCheckApp.value < _bgUpdateMaxAttempts) {
          toRetry.add(MapEntry(toCheckApp.key, toCheckApp.value + 1));
          int minRetryIntervalForThisApp = err is RateLimitError
              ? (err.remainingMinutes * 60)
              : err is ClientException
              ? (_bgClientExceptionRetryWaitSeconds)
              : (toCheckApp.value + 1);
          if (minRetryIntervalForThisApp > _bgUpdateMaxRetryWaitSeconds) {
            minRetryIntervalForThisApp = _bgUpdateMaxRetryWaitSeconds;
          }
          if (minRetryIntervalForThisApp > retryAfterXSeconds) {
            retryAfterXSeconds = minRetryIntervalForThisApp;
          }
        } else {
          if (err is! RateLimitError) {
            toThrow.add(key, err, appName: errors!.appIdNames[key]);
          }
        }
      });
    } else {
      unawaited(logs.add('Fatal error in BG update task: ${e.toString()}'));
      rethrow;
    }
  } finally {
    unawaited(notificationsProvider.cancel(notif.id));
  }

  unawaited(logs.add('BG update task: Done checking for updates.'));
  if (toRetry.isNotEmpty) {
    unawaited(
      logs.add(
        'BG update task $taskId: Scheduling retry in ${retryAfterXSeconds}s '
        '(${toRetry.length} to retry).',
      ),
    );
    final retryName = 'retry_${taskId}_${Random().nextInt(10000)}';
    await Workmanager().registerOneOffTask(
      retryName,
      retryName,
      initialDelay: Duration(seconds: retryAfterXSeconds),
      constraints: _bgTaskConstraints(appsProvider.settingsProvider),
      inputData: {
        'toCheck': toRetry
            .map((entry) => {'key': entry.key, 'value': entry.value})
            .toList(),
      },
    );
  } else {
    unawaited(logs.add('BG update task: No retries needed.'));
  }

  return (updates: updates, errors: errors, toThrow: toThrow);
}

class CancellationToken {
  bool _cancelled = false;
  bool get isCancelled => _cancelled;
  final Set<VoidCallback> _listeners = {};
  final _cancellation = Completer<void>();
  Future<void> get whenCancelled => _cancellation.future;

  void cancel() {
    if (_cancelled) return;
    _cancelled = true;
    _cancellation.complete();
    for (final listener in _listeners.toList()) {
      listener();
    }
    _listeners.clear();
  }

  void addListener(VoidCallback listener) {
    if (_cancelled) {
      listener();
    } else {
      _listeners.add(listener);
    }
  }

  void removeListener(VoidCallback listener) {
    _listeners.remove(listener);
  }

  void throwIfCancelled() {
    if (_cancelled) throw const CancellationException();
  }
}

/// Isolates the implementation-level `easy_localization/src/` imports to a
/// single file so the rest of the codebase only depends on the public API.
class TranslationLoader {
  static Future<void> load() async {
    await EasyLocalizationController.initEasyLocation();
    final s = SettingsProvider();
    await s.initializeSettings();
    final forceLocale = s.forcedLocale;
    final controller = EasyLocalizationController(
      saveLocale: true,
      forceLocale: forceLocale,
      fallbackLocale: fallbackLocale,
      supportedLocales: supportedLocales.map((e) => e.key).toList(),
      assetLoader: const RootBundleAssetLoader(),
      useOnlyLangCode: false,
      useFallbackTranslations: true,
      path: localeDir,
      onLoadError: (FlutterError e) {
        throw e;
      },
    );
    await controller.loadTranslations();
    Localization.load(
      controller.locale,
      translations: controller.translations,
      fallbackTranslations: controller.fallbackTranslations,
    );
  }
}
// Platform channel helpers for native OS features (e.g. system font loading).

class NativeFeatures {
  static const MethodChannel _powerChannel = MethodChannel(
    'dev.imranr.obtainium/power',
  );
  static const MethodChannel _storageChannel = MethodChannel(
    'dev.imranr.obtainium/storage',
  );
  static const MethodChannel _notificationsChannel = MethodChannel(
    'dev.imranr.obtainium/notifications',
  );
  static const MethodChannel _diagnosticsChannel = MethodChannel(
    'dev.imranr.obtainium/diagnostics',
  );
  static const MethodChannel _deviceAppsChannel = MethodChannel(
    'dev.imranr.obtainium/device_apps',
  );
  static bool _systemFontLoadAttempted = false;
  // True once a real multi-weight 'SystemFont' family has been registered and
  // should be used in place of Flutter's default. See [loadSystemFont].
  static bool _systemFontApplied = false;

  /// Whether the app should render with the explicitly-loaded system font
  /// family ('SystemFont') instead of Flutter's default. False until (and
  /// unless) [loadSystemFont] adopts a multi-weight device font.
  static bool get systemFontApplied => _systemFontApplied;
  static bool _downloadCancelHandlerRegistered = false;

  static void registerDownloadCancelHandler(
    FutureOr<void> Function(String appId) handler,
  ) {
    if (_downloadCancelHandlerRegistered) return;
    _downloadCancelHandlerRegistered = true;
    _notificationsChannel.setMethodCallHandler((call) async {
      if (call.method != 'cancelDownload') {
        throw MissingPluginException();
      }
      final appId = call.arguments?.toString();
      if (appId == null || appId.isEmpty) return;
      await handler(appId);
    });
    unawaited(_consumePendingDownloadCancels(handler));
  }

  static Future<void> _consumePendingDownloadCancels(
    FutureOr<void> Function(String appId) handler,
  ) async {
    try {
      final pendingAppIds =
          await _notificationsChannel.invokeListMethod<String>(
            'consumePendingDownloadCancels',
          ) ??
          const <String>[];
      for (final String appId in pendingAppIds) {
        if (appId.isNotEmpty) {
          await handler(appId);
        }
      }
    } on PlatformException {
      // Notification actions remain best-effort on older native runners.
    } on MissingPluginException {
      // Non-Android builds and older native runners do not expose this method.
    }
  }

  /// Launcher icon of a downloaded, not-yet-installed APK, as PNG bytes.
  ///
  /// Rendered natively from the archive (adaptive icons composited, size-capped)
  /// so an app from a source that publishes no icon still gets one.
  static Future<Uint8List?> getApkArchiveIcon(String archiveFilePath) async {
    try {
      return await _deviceAppsChannel.invokeMethod<Uint8List>(
        'getApkArchiveIcon',
        {'archiveFilePath': archiveFilePath},
      );
    } on MissingPluginException {
      return null;
    } on PlatformException {
      return null;
    }
  }

  static Future<ByteData> _readFileBytes(String path) async {
    final bytes = await File(path).readAsBytes();
    return ByteData.view(bytes.buffer);
  }

  /// Registers the device's default font family (all weight/style files) under
  /// the Flutter family name 'SystemFont', so the app can follow a user-picked
  /// OEM font with real bold/medium weights.
  ///
  /// Deliberately adopts 'SystemFont' ONLY when the device provides two or more
  /// weight files. A lone file means a modern variable font: Flutter's default
  /// (fontFamily: null) already derives real weights from its variation axis,
  /// whereas registering the single file ourselves would give faux-synthesized
  /// bold. So in that case we do nothing and stay on the default — which is the
  /// same system font anyway. Idempotent; safe to call more than once.
  static Future<void> loadSystemFont() async {
    if (_systemFontLoadAttempted) return;
    _systemFontLoadAttempted = true;
    try {
      final List<String>? files = await _deviceAppsChannel
          .invokeListMethod<String>('getSystemFontFiles');
      if (files == null || files.length < 2) return;
      final fontLoader = FontLoader('SystemFont');
      for (final String path in files) {
        fontLoader.addFont(_readFileBytes(path));
      }
      await fontLoader.load();
      _systemFontApplied = true;
    } on MissingPluginException {
      // Non-Android build or background engine: keep the default font.
    } catch (_) {
      // Any font read / registration failure: keep the default font.
    }
  }

  static Future<String?> consumeNativeCrashLog() async {
    if (!Platform.isAndroid) return null;
    try {
      final log = await _diagnosticsChannel.invokeMethod<String>(
        'consumeNativeCrashLog',
      );
      if (log == null || log.trim().isEmpty) return null;
      return log;
    } on PlatformException {
      return null;
    } on MissingPluginException {
      return null;
    }
  }

  /// Raw display densities from the platform, or null when unavailable.
  ///
  /// Keys: stableDensityDpi, systemDensityDpi, effectiveDensityDpi,
  /// isInMultiWindowMode. See MainActivity.displayDiagnostics().
  static Future<Map<String, Object?>?> getDisplayDiagnostics() async {
    if (!Platform.isAndroid) return null;
    try {
      return (await _diagnosticsChannel.invokeMapMethod<String, Object?>(
        'getDisplayDiagnostics',
      ));
    } on PlatformException {
      return null;
    } on MissingPluginException {
      return null;
    }
  }

  static Future<bool> acquireDownloadKeepAwake() async {
    try {
      return await _powerChannel.invokeMethod<bool>(
            'acquireDownloadKeepAwake',
          ) ??
          false;
    } on PlatformException {
      // Downloads should still proceed if the platform cannot hold a lock.
      return false;
    } on MissingPluginException {
      // Non-Android builds do not provide this channel.
      return false;
    }
  }

  static Future<void> releaseDownloadKeepAwake() async {
    try {
      await _powerChannel.invokeMethod('releaseDownloadKeepAwake');
    } on PlatformException {
      // Best-effort cleanup; Android also releases locks if the process dies.
    } on MissingPluginException {
      // Non-Android builds do not provide this channel.
    }
  }

  static Future<bool> isDeviceInteractive() async {
    try {
      return await _powerChannel.invokeMethod<bool>('isDeviceInteractive') ??
          false;
    } on PlatformException {
      return false;
    } on MissingPluginException {
      return false;
    }
  }

  static Future<Uri?> openPersistedDocumentTree({Uri? initialUri}) async {
    try {
      final uriString = await _storageChannel.invokeMethod<String>(
        'openPersistedDocumentTree',
        <String, String?>{'initialUri': initialUri?.toString()},
      );
      if (uriString == null || uriString.isEmpty) {
        return null;
      }
      return Uri.parse(uriString);
    } on PlatformException {
      return null;
    } on MissingPluginException {
      return null;
    }
  }

  static Future<bool> hasPersistedDocumentTreePermission(Uri uri) async {
    try {
      return await _storageChannel.invokeMethod<bool>(
            'hasPersistedDocumentTreePermission',
            <String, String>{'uri': uri.toString()},
          ) ??
          false;
    } on PlatformException {
      return false;
    } on MissingPluginException {
      return false;
    }
  }

  static Future<void> showDownloadProgressNotification({
    required int id,
    required String appId,
    required String title,
    required String message,
    required String channelCode,
    required int progressPercent,
    required bool indeterminate,
    required String cancelLabel,
    String? shortCriticalText,
  }) async {
    if (!Platform.isAndroid) return;
    try {
      await _notificationsChannel
          .invokeMethod('showDownloadProgressNotification', <String, Object?>{
            'id': id,
            'appId': appId,
            'title': title,
            'message': message,
            'channelCode': channelCode,
            'progressPercent': progressPercent,
            'indeterminate': indeterminate,
            'cancelLabel': cancelLabel,
            'shortCriticalText': shortCriticalText,
          });
    } on PlatformException {
      // The regular Flutter notification remains the fallback.
    } on MissingPluginException {
      // Non-Android builds and older runners do not provide this channel.
    }
  }

  static Future<bool> startDownloadForegroundService({
    required int id,
    required String appId,
    required String title,
    required String message,
    required String channelCode,
    required String channelName,
    required String channelDescription,
    required String cancelLabel,
  }) async {
    if (!Platform.isAndroid) return false;
    try {
      return await _notificationsChannel.invokeMethod<bool>(
            'startDownloadForegroundService',
            <String, Object?>{
              'id': id,
              'appId': appId,
              'title': title,
              'message': message,
              'channelCode': channelCode,
              'channelName': channelName,
              'channelDescription': channelDescription,
              'cancelLabel': cancelLabel,
            },
          ) ??
          false;
    } on PlatformException {
      // The download can still proceed; wake locks and progress notification remain best effort.
      return false;
    } on MissingPluginException {
      // Non-Android builds and older runners do not provide this channel.
      return false;
    }
  }

  static Future<void> stopDownloadForegroundService() async {
    if (!Platform.isAndroid) return;
    try {
      await _notificationsChannel.invokeMethod('stopDownloadForegroundService');
    } on PlatformException {
      // Android will tear the service down if the process dies.
    } on MissingPluginException {
      // Non-Android builds and older runners do not provide this channel.
    }
  }
}
