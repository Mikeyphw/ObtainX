import 'dart:io';

/// Exact scheme, normalized host and effective port. Never use suffix matching.
bool sameRequestOrigin(Uri a, Uri b) =>
    a.scheme == b.scheme && a.host == b.host && a.port == b.port;

void validateHttpRequestUri(Uri uri) {
  if ((uri.scheme != 'https' && uri.scheme != 'http') ||
      uri.host.isEmpty || uri.userInfo.isNotEmpty) {
    throw const FormatException('Invalid HTTP request destination');
  }
}

/// No HTTPS downgrade, even for public data. POST bodies may contain credentials
/// and must not be replayed into another origin. Do not include URLs in errors.
void validateHttpRedirect(Uri from, Uri to, String method, {
  bool hasBody = false,
  bool insecureTls = false,
}) {
  validateHttpRequestUri(to);
  if (from.scheme == 'https' && to.scheme != 'https') {
    throw const FormatException('HTTPS redirect downgrade refused');
  }
  if (!sameRequestOrigin(from, to)) {
    if (hasBody || (method != 'GET' && method != 'HEAD')) {
      throw const FormatException('Cross-origin request body redirect refused');
    }
    if (insecureTls) {
      throw const FormatException('Insecure TLS permission cannot cross origins');
    }
  }
}

/// After leaving the initial origin, no source-supplied credentials or custom
/// headers (including User-Agent, Referer and Cookie) are restored, even on a
/// redirect back. Only the download protocol's byte-range controls survive.
Map<String, String> crossOriginDownloadHeaders(Map<String, String>? original) {
  final safe = <String, String>{};
  for (final entry in (original ?? const <String, String>{}).entries) {
    final name = entry.key.toLowerCase();
    if (name == HttpHeaders.rangeHeader || name == 'if-range') {
      safe[name] = entry.value;
    }
  }
  return safe;
}
