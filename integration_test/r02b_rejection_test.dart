// Real Android 16 negative installer acceptance, not a simulated platform call.
// The host creates and independently verifies a signed v2 precondition.
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:obtainium/installers/stock_installer.dart';
import 'package:obtainium/providers/settings_provider.dart';
import 'package:obtainium/services/install_bundle_plan.dart';

const targetPackage = 'dev.bikram.obtainx.rt02.fixture';
const negativeCase = String.fromEnvironment('OX_R02B_CASE');
const fixtureDigest = String.fromEnvironment('OX_R02B_SHA256');
const fixturePort = 18782;

Future<File> exactFixture(String name, Directory folder) async {
  if (!RegExp(r'^[0-9a-f]{64}$').hasMatch(fixtureDigest)) {
    throw StateError('Missing bound fixture digest');
  }
  final client=HttpClient()..connectionTimeout=const Duration(seconds:10);
  try {
    final req=await client.getUrl(Uri.parse('http://127.0.0.1:$fixturePort/$name'));
    final resp=await req.close().timeout(const Duration(seconds:25));
    if (resp.statusCode!=HttpStatus.ok) throw StateError('Fixture unavailable');
    final bytes=await resp.fold<List<int>>(<int>[],(b,chunk)=>b..addAll(chunk));
    if (bytes.length<250 || sha256.convert(bytes).toString()!=fixtureDigest) {
      throw StateError('Fixture SHA-256 mismatch');
    }
    final file=File('${folder.path}/base.apk');
    await file.writeAsBytes(bytes,flush:true);
    return file;
  } finally {
    client.close(force:true);
  }
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('RT02B reject unsafe update through production StockInstaller',(tester) async {
    debugPrint('OX_R02_RT02_DART_STAGE=SCENARIO_STARTED');
    if (!Platform.isAndroid) throw StateError('Android emulator only');
    if (negativeCase!='signature_mismatch' && negativeCase!='downgrade') {
      throw StateError('Unapproved negative test case');
    }
    final folder=await Directory.systemTemp.createTemp('obtainx-rt02b-');
    try {
      const name=negativeCase=='signature_mismatch'?'wrong_signer_v3.apk':'base_v1.apk';
      final file=await exactFixture(name,folder);
      const version=negativeCase=='signature_mismatch'?3:1;
      final plan=resolveInstallBundlePlan(
        members:[InstallApkMember(path:file.path,packageName:targetPackage,
                 versionCode:version,minSdkVersion:26,targetSdkVersion:35)],
        format:InstallArtifactFormat.apk,supportedAbis:const ['x86_64'],
        expectedPackageName:targetPackage,deviceSdkVersion:36);
      expect(plan.packageName,targetPackage);
      expect(plan.versionCode,version);
      expect(plan.sessionPaths.length,1);
      debugPrint('OX_R02_RT02_DART_STAGE=INSTALL_CALL');
      final result=await StockInstaller(SettingsProvider()).installApk(
        plan.sessionPaths,appId:targetPackage,
      ).timeout(const Duration(minutes:3));
      debugPrint('OX_R02_RT02_DART_STAGE=INSTALL_RETURNED');
      expect(result.isError,isTrue,
        reason:'Android must reject a wrong-certificate update or downgrade');
    } finally {
      if (await folder.exists()) await folder.delete(recursive:true);
    }
  });
}
