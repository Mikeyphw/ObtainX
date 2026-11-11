import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/installers/installer.dart';
import 'package:obtainium/services/third_party_install_evidence.dart';

void main() {
  test('RT02F external broadcast is still unverified handoff', () {
    final result = classifyUnverifiedThirdPartyHandoff(true);
    expect(result.isHandedOff, isTrue);
    expect(result.isSuccess, isFalse);
    expect(result.isCancelled, isFalse);
  });
  test('RT02F external timeout is not cancellation or success', () {
    final result = classifyUnverifiedThirdPartyHandoff(false);
    expect(result.isHandedOff, isTrue);
    expect(result.isSuccess, isFalse);
    expect(result.isCancelled, isFalse);
  });
  test('RT02F stock cancellation and non-success are distinct', () {
    expect(InstallResult.fromPlatformCode(null).isCancelled,isTrue);
    expect(InstallResult.fromPlatformCode(3).isAlreadyInstalled,isTrue);
    expect(InstallResult.fromPlatformCode(0).isSuccess,isTrue);
    expect(InstallResult.fromPlatformCode(-1).isError,isTrue);
  });
}
