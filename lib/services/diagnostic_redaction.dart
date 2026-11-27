/// Diagnostics are not a transport or a credential store. Unknown exceptions
/// contribute a category, never their untrusted message, body, headers or stack.
String diagnosticErrorCategory(Object? error) =>
    error == null ? 'UnknownError' : error.runtimeType.toString();

final _url = RegExp(
  r'''(?:[a-z][a-z0-9+.-]*://|[a-z][a-z0-9+.-]*%3a%2f%2f|[a-z][a-z0-9+.-]*:\\/\\/)[^\s<>"'`]+''',
  caseSensitive: false,
);
final _credentialField = RegExp(
  r'''\b(?:authorization|proxy[-_]authorization|private[-_]token|access[-_]token|refresh[-_]token|id[-_]token|client[-_]secret|api[-_]?key|x[-_]api[-_]key|x[-_]auth[-_]token|set[-_]cookie|cookie|password|passwd|secret|token|pat|github[-_]creds|gitlab[-_]creds|request[-_ ]headers|response[-_ ]headers|headers)\s*["']?\s*(?:[:=]|%3a|%3d)''',
  caseSensitive: false,
);
final _credentialScheme = RegExp(r'\b(?:Bearer|Basic)\s+\S+', caseSensitive: false);
final _knownToken = RegExp(
  r'\b(?:gh[pousr]_[A-Za-z0-9_\-]+|github_pat_[A-Za-z0-9_\-]+|glpat-[A-Za-z0-9_\-]+|gldt-[A-Za-z0-9_\-]+|glrt-[A-Za-z0-9_\-]+)\b',
  caseSensitive: false,
);
final _control = RegExp(r'[\x00-\x08\x0b-\x1f\x7f]');

/// Free-form diagnostics can contain opaque signed paths as well as queries.
/// Omit entire URLs, redact sensitive fields, and discard multiline credential
/// blocks. This is defense in depth; callers must not include raw exception
/// messages, server bodies or credential values in the first place.
String redactDiagnosticText(String text) {
  final clean = text.replaceAll('\r\n', '\n').replaceAll('\r', '\n')
      .replaceAll(_control, ' ');
  // An entire message is withheld if it contains a credential field. A value
  // can be quoted, folded, JSON-encoded or spread across subsequent lines.
  if (_credentialField.hasMatch(clean) || _credentialScheme.hasMatch(clean)) {
    return '[redacted credential-bearing diagnostic]';
  }
  return clean.replaceAll(_url, '[redacted URL]')
      .replaceAll(_knownToken, '[redacted token]');
}

String boundedDiagnosticText(String text) {
  const maxChars = 32768;
  // Do not expose a truncated credential prefix or suffix.
  if (text.length > maxChars) return '[oversized diagnostic withheld]';
  return redactDiagnosticText(text);
}
