import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/services/install_bundle_plan.dart';
import 'package:obtainium/services/r09_artifact_inspection.dart';
import 'package:obtainium/services/r09_discovery.dart';

final digest = List.filled(64, 'a').join();
final signer = List.filled(64, 'b').join();
R09ApkFacts member(String name, {String? split, String package = 'dev.example.app',
  int version = 2, int? sdk = 26, List<String> abis = const [],
  List<String>? signers, bool required = false}) => R09ApkFacts(
    path: '/private/$name', name: name, sha256: digest, packageName: package,
    versionCode: version, split: split, minSdk: sdk, nativeAbis: abis,
    signers: signers ?? [signer], splitRequired: required);
R09ArtifactInspection review(List<R09ApkFacts> members,
    {InstallArtifactFormat format = InstallArtifactFormat.apk, List<String>? installed}) =>
  reviewR09Artifact(artifactSha256: digest, bytes: 1024, members: members,
    format: format, supportedAbis: const ['arm64-v8a'], sdk: 33,
    locales: const ['en-US'], density: 420, expectedPackage: 'dev.example.app',
    installedSigners: installed ?? [signer], installedPackageObserved: true,
    actionsDigestVerified: false, installedVersionCode: 1);

void main() {
  test('actual metadata replaces an inaccurate filename hint', () {
    final result = review([member('x86.apk', abis: ['arm64-v8a'])]);
    expect(result.eligible, isTrue);
    expect(result.signerStatus, 'r09ReviewSignerMatches');
    expect(result.actionsDigestVerified, isFalse);
    expect(result.installedVersionCode, 1);
    final asset = const MapEntry('x86.apk', 'https://example.org/apk');
    expect(r09ChooseArtifact([asset], ['arm64-v8a'], null,
      evaluatedChoice: (_) => const R09ArtifactChoice(true, ['arm64-v8a'], 'r09RoleApk', 'r09ReviewCompatible')), asset);
  });
  test('actual package SDK ABI and certificate mismatches refuse', () {
    expect(review([member('base.apk', package: 'dev.other.app')]).refusals, contains('r09ReviewPackageMismatch'));
    expect(review([member('base.apk', sdk: 34)]).refusals, contains('r09ReviewSdkMismatch'));
    expect(review([member('base.apk', abis: ['x86_64'])]).refusals, contains('r09ReviewAbiMismatch'));
    expect(review([member('base.apk', signers: [])]).eligible, isFalse);
    expect(review([member('base.apk')], installed: [List.filled(64, 'c').join()]).eligible, isFalse);
    expect(review([member('base.apk', required: true)]).eligible, isFalse);
    expect(review([member('config.arm64_v8a.apk', split: 'config.arm64_v8a')]).eligible, isFalse);
  });
  test('split inventory must match actual manifest and base identity', () {
    final base = member('base.apk');
    final split = member('config.arm64_v8a.apk', split: 'config.arm64_v8a', signers: []);
    expect(review([base, split], format: InstallArtifactFormat.apks).eligible, isTrue);
    for (final bad in [
      member('config.arm64_v8a.apk', split: 'config.x86_64'),
      member('config.arm64_v8a.apk', split: 'config.arm64_v8a', version: 3),
      member('config.arm64_v8a.apk', split: 'config.arm64_v8a', signers: [List.filled(64, 'c').join()]),
      member('base2.apk'),
    ]) {
      expect(review([base, bad], format: InstallArtifactFormat.apks).eligible, isFalse);
    }
  });
  test('selection is bound to exact release and reviewed digest', () {
    final binding = R09ReviewBinding(releaseKey: 'release', digest: digest);
    expect(binding.matches('release', digest), isTrue);
    expect(binding.matches('other', digest), isFalse);
    expect(binding.matches('release', List.filled(64, 'f').join()), isFalse);
  });
}
