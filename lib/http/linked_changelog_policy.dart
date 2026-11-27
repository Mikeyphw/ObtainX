import 'package:obtainium/http/origin_redirect_policy.dart';

/// Plan before requesting credentials. No PAT is accepted as URL input.
/// A linked changelog is metadata, not an artifact-download redirect.
class LinkedChangelogRequest {
  const LinkedChangelogRequest(this.uri, {required this.sourceHeaders,
    this.githubRelease = false, this.gitlabRelease = false});
  final Uri uri;
  final bool sourceHeaders;
  final bool githubRelease;
  final bool gitlabRelease;
}

bool hasCredentialQuery(Uri uri) => uri.queryParametersAll.keys.any((key) {
  final normalized = key.toLowerCase().replaceAll(RegExp(r'[-_]'), '');
  return const {'privatetoken', 'accesstoken', 'authorization', 'password',
    'apikey', 'pat', 'token', 'clientsecret'}.contains(normalized);
});

Uri _metadataUri(String text) {
  final uri = Uri.tryParse(text);
  if (uri == null || uri.scheme != 'https' || uri.host.isEmpty ||
      uri.userInfo.isNotEmpty || hasCredentialQuery(uri)) {
    throw const FormatException('Unsafe linked changelog destination');
  }
  return uri.removeFragment();
}

LinkedChangelogRequest planLinkedChangelog(String trackedUrl, String link, {
  required bool gitlab, required bool github, String? gitlabHost,
}) {
  final target = _metadataUri(link);
  final tracked = Uri.tryParse(trackedUrl);
  final sameOrigin = tracked != null && tracked.scheme == 'https' &&
      tracked.userInfo.isEmpty && sameRequestOrigin(tracked, target);
  final segments = target.pathSegments;
  final projectSegments = tracked?.pathSegments.where((part) => part.isNotEmpty).toList() ?? const <String>[];
  final project = projectSegments.join('/');
  if (gitlab) {
    final configured = Uri.tryParse('https://$gitlabHost');
    if (!sameOrigin || projectSegments.length < 2 || configured == null ||
        !sameRequestOrigin(configured, target) || target.hasQuery) {
      throw const FormatException('GitLab changelog origin refused');
    }
    final dash = segments.indexOf('-');
    if (dash > 1 && segments.length > dash + 1 &&
        segments[dash + 1] == 'releases') {
      if (segments.take(dash).join('/') != project) {
        throw const FormatException('GitLab changelog project refused');
      }
      final tag = segments.skip(dash + 2).join('/');
      return LinkedChangelogRequest(target.replace(pathSegments: [
        'api', 'v4', 'projects', project, 'releases', if (tag.isNotEmpty) tag,
      ]), sourceHeaders: true, gitlabRelease: true);
    }
    if (segments.length >= 5 && segments[0] == 'api' &&
        segments[1] == 'v4' && segments[2] == 'projects' &&
        segments[4] == 'releases') {
      if (segments[3] != project) {
        throw const FormatException('GitLab changelog API project refused');
      }
      return LinkedChangelogRequest(target, sourceHeaders: true, gitlabRelease: true);
    }
    if (dash > 1 && segments.length > dash + 3 && segments[dash + 1] == 'blob') {
      if (segments.take(dash).join('/') != project) {
        throw const FormatException('GitLab changelog project refused');
      }
      final ref = segments[dash + 2];
      final file = segments.skip(dash + 3).join('/');
      if (ref.isEmpty || file.isEmpty) {
        throw const FormatException('GitLab changelog file refused');
      }
      return LinkedChangelogRequest(target.replace(pathSegments: [
        'api', 'v4', 'projects', project, 'repository', 'files', file, 'raw',
      ], queryParameters: {'ref': ref}), sourceHeaders: true);
    }
    // Arbitrary same-host links are public only; do not attach source PAT.
    return LinkedChangelogRequest(target, sourceHeaders: false);
  }
  // Only the configured canonical GitHub origin can select the API path.
  final canonicalGithub = github && sameOrigin && target.host == 'github.com' && target.port == 443 && projectSegments.length >= 2 && segments.length >= 2 &&
      projectSegments.take(2).join('/') == segments.take(2).join('/');
  if (canonicalGithub && segments.length >= 3 && segments[2] == 'releases') {
    final latest = segments.length == 3 || segments[3] == 'latest';
    final tagged = segments.length >= 5 && segments[3] == 'tag';
    if (latest || tagged) {
      return LinkedChangelogRequest(Uri(scheme: 'https', host: 'api.github.com', pathSegments: [
        'repos', segments[0], segments[1], 'releases',
        if (latest) 'latest' else ...['tags', segments.skip(4).join('/')],
      ]), sourceHeaders: true, githubRelease: true);
    }
  }
  if (canonicalGithub && segments.length >= 5 && segments[2] == 'blob') {
    return LinkedChangelogRequest(Uri(scheme: 'https', host: 'raw.githubusercontent.com',
      pathSegments: [segments[0], segments[1], ...segments.skip(3)]), sourceHeaders: false);
  }
  return LinkedChangelogRequest(target, sourceHeaders: sameOrigin);
}

/// No credential-bearing URL may be displayed or launched by the changelog UI.
Uri? safeChangelogNavigation(String trackedUrl, String link) {
  try {
    return _metadataUri(Uri.parse(trackedUrl).resolve(link).toString());
  } catch (_) {
    return null;
  }
}
