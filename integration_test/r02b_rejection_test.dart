// OPT05 P01: two independent real Android negative installer attempts in one
// Flutter session. The host must attest unchanged Android state after each
// rejection before the Dart test can proceed to the next attempt.
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:obtainium/installers/stock_installer.dart';
import 'package:obtainium/providers/settings_provider.dart';
import 'package:obtainium/services/install_bundle_plan.dart';

const targetPackage = 'dev.bikram.obtainx.rt02.fixture';
const wrongDigest = String.fromEnvironment('OX_R02B_WRONG_SHA256');
const downgradeDigest = String.fromEnvironment('OX_R02B_DOWNGRADE_SHA256');
const fixturePort = 18782;
const negativeCases = <String>['signature_mismatch','downgrade'];

Future<File> exactFixture(String name, String fixtureDigest, Directory folder) async {
  if (!RegExp(r'^[0-9a-f]{64}$').hasMatch(fixtureDigest)) {
    throw StateError('Missing source-bound signed fixture digest');
  }
  final client=HttpClient()..connectionTimeout=const Duration(seconds:10);
  try {
    final req=await client.getUrl(Uri.parse('http://127.0.0.1:$fixturePort/$name'));
    final resp=await req.close().timeout(const Duration(seconds:25));
    if (resp.statusCode!=HttpStatus.ok) throw StateError('Fixture unavailable');
    final bytes=await resp.fold<List<int>>(<int>[],(b,chunk)=>b..addAll(chunk));
    if (bytes.length<250 || bytes.length>70*1024*1024 ||
        sha256.convert(bytes).toString()!=fixtureDigest) {
      throw StateError('Fixture SHA-256/size mismatch');
    }
    final file=File('${folder.path}/base.apk');
    await file.writeAsBytes(bytes,flush:true);
    return file;
  } finally {
    client.close(force:true);
  }
}

Future<void> awaitHostAck(String testCase) async {
  // The server only acknowledges after the host independently verifies the
  // exact installed signed v2 APK bytes and unchanged package version.
  for (var attempt=0;attempt<120;attempt++) {
    final client=HttpClient()..connectionTimeout=const Duration(seconds:5);
    try {
      final request=await client.getUrl(Uri.parse('http://127.0.0.1:$fixturePort/ack/$testCase'));
      final response=await request.close().timeout(const Duration(seconds:10));
      await response.drain<void>();
      if (response.statusCode==HttpStatus.ok) return;
      if (response.statusCode!=425) throw StateError('Host rejected negative case acknowledgement');
    } finally {
      client.close(force:true);
    }
    await Future<void>.delayed(const Duration(seconds:2));
  }
  throw StateError('Host did not attest unchanged Android package state');
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('RT02B two real unsafe update refusals in one session',(tester) async {
    if (!Platform.isAndroid) throw StateError('Android emulator only');
    if (!RegExp(r'^[0-9a-f]{64}$').hasMatch(wrongDigest) ||
        !RegExp(r'^[0-9a-f]{64}$').hasMatch(downgradeDigest) ||
        wrongDigest==downgradeDigest) {
      throw StateError('Both distinct source-bound fixture hashes are required');
    }
    for (final testCase in negativeCases) {
      debugPrint('OX_R02B_EVENT=$testCase:START');
      debugPrint('OX_R02_RT02_DART_STAGE=SCENARIO_STARTED');
      final folder=await Directory.systemTemp.createTemp('obtainx-rt02b-');
      try {
        final isWrong=testCase=='signature_mismatch';
        final name=isWrong?'wrong_signer_v3.apk':'base_v1.apk';
        final digest=isWrong?wrongDigest:downgradeDigest;
        final file=await exactFixture(name,digest,folder);
        final version=isWrong?3:1;
        final plan=resolveInstallBundlePlan(
          members:[InstallApkMember(path:file.path,packageName:targetPackage,
                   versionCode:version,minSdkVersion:26,targetSdkVersion:35)],
          format:InstallArtifactFormat.apk,supportedAbis:const ['x86_64'],
          expectedPackageName:targetPackage,deviceSdkVersion:36);
        expect(plan.packageName,targetPackage);
        expect(plan.versionCode,version);
        expect(plan.sessionPaths.length,1);
        debugPrint('OX_R02B_EVENT=$testCase:INSTALL_CALL');
        debugPrint('OX_R02_RT02_DART_STAGE=INSTALL_CALL');
        final result=await StockInstaller(SettingsProvider()).installApk(
          plan.sessionPaths,appId:targetPackage,
        ).timeout(const Duration(minutes:3));
        debugPrint('OX_R02_RT02_DART_STAGE=INSTALL_RETURNED');
        expect(result.isError,isTrue,
          reason:'Android must reject wrong-certificate update or downgrade');
        debugPrint('OX_R02B_EVENT=$testCase:REJECTED');
        await awaitHostAck(testCase);
        debugPrint('OX_R02B_EVENT=$testCase:ACKED');
      } finally {
        if (await folder.exists()) await folder.delete(recursive:true);
      }
    }
  }, timeout: const Timeout(Duration(minutes:45)));
}
