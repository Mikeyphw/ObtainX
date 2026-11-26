import 'dart:io';

/// Default User-Agent for source HTTP. Sources that already set a User-Agent
/// keep their explicitly configured identity; this is the default.
const String obtainXUserAgent = 'ObtainX';

bool headersSpecifyUserAgent(Map<String, String>? headers) {
  if (headers == null) {
    return false;
  }
  return headers.keys.any(
    (String headerName) => headerName.toLowerCase() == 'user-agent',
  );
}

/// Copy of [headers] with [obtainXUserAgent] filled in when the source did not
/// already send one (any casing).
Map<String, String> withDefaultObtainXUserAgent(Map<String, String>? headers) {
  final Map<String, String> merged = Map<String, String>.from(headers ?? {});
  if (!headersSpecifyUserAgent(merged)) {
    merged[HttpHeaders.userAgentHeader] = obtainXUserAgent;
  }
  return merged;
}
