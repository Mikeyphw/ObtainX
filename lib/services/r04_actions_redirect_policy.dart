/// R04: GitHub artifact ZIP redirects need a different trust boundary from the
/// GitHub REST API. Only the canonical API endpoint may receive a PAT.
/// The one-minute signed storage URL receives no authorization or cookies.
library;

import 'dart:io';
import 'package:obtainium/http/origin_redirect_policy.dart';

class R04ActionsRedirectFailure implements Exception {
  const R04ActionsRedirectFailure(this.reason);
  final String reason;
  @override
  String toString() => 'GitHub Actions download refused: $reason';
}

bool r04IsCanonicalArtifactDownload(Uri uri) =>
    uri.scheme == 'https' && uri.host == 'api.github.com' &&
    uri.userInfo.isEmpty && !uri.hasPort &&
    !uri.hasQuery && !uri.hasFragment &&
    RegExp(r'^/repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/actions/artifacts/[1-9][0-9]*/zip$')
        .hasMatch(uri.path);

bool r04IsActionsMetadataApi(Uri uri) =>
    uri.scheme == 'https' && uri.host == 'api.github.com' &&
    uri.userInfo.isEmpty && !uri.hasPort &&
    RegExp(r'^/repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/actions(?:/|$)')
        .hasMatch(uri.path);

bool r04IsTrustedArtifactStorage(Uri uri) {
  if (uri.scheme != 'https' || uri.userInfo.isNotEmpty || uri.hasPort ||
      uri.hasFragment || uri.host.isEmpty) {
    return false;
  }
  final host = uri.host.toLowerCase();
  // GitHub Actions' current signed object-store hosts. Do not accept a
  // hostname merely *containing* one of these strings.
  return host.endsWith('.actions.githubusercontent.com') ||
      host == 'actions.githubusercontent.com' ||
      host.endsWith('.githubusercontent.com') ||
      host == 'githubusercontent.com' ||
      host.endsWith('.blob.core.windows.net');
}

void r04ValidateArtifactRedirect(Uri from, Uri destination) {
  if (from.scheme != 'https') {
    throw const R04ActionsRedirectFailure('insecure redirect origin');
  }
  if (!r04IsTrustedArtifactStorage(destination)) {
    throw const R04ActionsRedirectFailure(
      'artifact redirected outside approved HTTPS storage hosts',
    );
  }
}

/// A private repository PAT and any source-config headers MUST NOT reach the
/// short-lived signed blob URL, even when an HTTP client follows a 302.
Map<String, String> r04ArtifactStorageHeaders(Map<String, String>? original) {
  return {
    HttpHeaders.acceptHeader: 'application/octet-stream',
    ...crossOriginDownloadHeaders(original),
  };
}
