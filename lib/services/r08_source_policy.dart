/// Shared source selection and incoming-link decisions. No installation authority.
library;

/// Promote ARM64 only if the device actually supports it, preserving the
/// relative order of every other ABI (including x86 and x86_64).
List<String> preferredSourceAbis(List<String> supported) {
  final ordered = supported.toSet().toList();
  final arm64 = ordered.indexOf('arm64-v8a');
  final arm32 = ordered.indexWhere((abi) =>
      abi == 'armeabi-v7a' || abi == 'armeabi');
  if (arm64 >= 0 && arm32 >= 0 && arm64 > arm32) {
    ordered.removeAt(arm64);
    ordered.insert(arm32, 'arm64-v8a');
  }
  return ordered;
}

/// Match an actual ABI token, not a host, query value, or x86_64 as x86.
/// The source's explicit artifact name/label remains authoritative.
bool sourceAssetHasAbi(String name, String abi) {
  final aliases = switch (abi) {
    'arm64-v8a' => ['arm64-v8a', 'arm64_v8a', 'arm64', 'aarch64'],
    'armeabi-v7a' => ['armeabi-v7a', 'armeabi_v7a', 'arm-v7a', 'armv7', 'armv7a'],
    'armeabi' => ['armeabi'],
    'x86_64' => ['x86_64', 'x86-64', 'amd64'],
    'x86' => ['x86'],
    _ => [abi],
  };
  final pattern = aliases.map(RegExp.escape).join('|');
  return RegExp('(?<![a-z0-9])(?:$pattern)(?![a-z0-9]|[_-](?:64|v7a))',
      caseSensitive: false).hasMatch(name);
}

/// Decode the outer add-link transport exactly once. Never decode the inner
/// URL a second time, and reject ambiguous query values and non-web schemes.
String obtainiumAddUrl(Uri link) {
  if (link.scheme != 'obtainium' || link.host != 'add') {
    throw const FormatException('Not an Obtainium add link');
  }
  final query = link.queryParametersAll['url'];
  if (query != null && query.length != 1) {
    throw const FormatException('Ambiguous add URL');
  }
  String data;
  if (query != null) {
    data = query.single;
  } else {
    final path = link.path.length > 1 ? link.path.substring(1) : '';
    // A literal URL may carry its own query and fragment. Transport-encoded
    // links already contain these in the decoded path.
    if (path.startsWith('https://') || path.startsWith('http://')) {
      Uri.decodeComponent(path); // reject malformed UTF-8 escape sequences
      data = '$path${link.hasQuery ? '?${link.query}' : ''}'
          '${link.hasFragment ? '#${link.fragment}' : ''}';
    } else {
      data = Uri.decodeComponent(path);
    }
  }
  final url = Uri.tryParse(data);
  if (url == null || !const {'https', 'http'}.contains(url.scheme) ||
      url.host.isEmpty || url.userInfo.isNotEmpty ||
      RegExp(r'[\x00-\x20\x7f]').hasMatch(data)) {
    throw const FormatException('Invalid HTTP(S) app source URL');
  }
  return data;
}

/// Suppress only the exact cold-start echo (or quick repeated identical event),
/// not the first unrelated warm link. Time-bound so intentional revisits work.
class IncomingSourceLinkGate {
  IncomingSourceLinkGate({this.window = const Duration(seconds: 5)});
  final Duration window;
  Uri? _last;
  DateTime? _lastAt;

  bool accept(Uri uri, DateTime now) {
    final previous = _lastAt;
    if (_last == uri && previous != null && !now.isBefore(previous) &&
        now.difference(previous) < window) {
      return false;
    }
    _last = uri;
    _lastAt = now;
    return true;
  }
}
