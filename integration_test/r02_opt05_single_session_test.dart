// OPT05 P02: two real Android install transitions in ONE Flutter session.
// Host acknowledgements are unavailable until independently verified signed
// installed APK bytes, version and the required Android approval path.
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:obtainium/installers/stock_installer.dart';
import 'package:obtainium/providers/settings_provider.dart';
import 'package:obtainium/services/install_bundle_plan.dart';

const packageName = 'dev.bikram.obtainx.rt02.fixture';
const v1Digest = String.fromEnvironment('OX_R02_P02_V1_SHA');
const v2Digest = String.fromEnvironment('OX_R02_P02_V2_SHA');
const splitDigest = String.fromEnvironment('OX_R02_P02_SPLIT_SHA');
const fixturePort = 18782;
const scenarios = <String>['standalone','split'];

Future<File> exactFixture(String name, String expected, Directory directory) async {
  if (!RegExp(r'^[0-9a-f]{64}$').hasMatch(expected)) {
    throw StateError('Missing signed source-bound fixture digest');
  }
  final client = HttpClient()..connectionTimeout=const Duration(seconds:10);
  try {
    final req=await client.getUrl(Uri.parse('http://127.0.0.1:$fixturePort/$name'));
    final resp=await req.close().timeout(const Duration(seconds:25));
    if (resp.statusCode!=HttpStatus.ok) throw StateError('Signed fixture unavailable');
    final bytes=await resp.fold<List<int>>(<int>[],(out,chunk)=>out..addAll(chunk));
    if (bytes.length<250 || bytes.length>70*1024*1024 ||
        sha256.convert(bytes).toString()!=expected) {
      throw StateError('Signed fixture SHA-256 or size mismatch');
    }
    final file=File('${directory.path}/${name=='config.x86_64.apk' ? name : 'base.apk'}');
    await file.writeAsBytes(bytes,flush:true);
    return file;
  } finally {
    client.close(force:true);
  }
}

Future<void> awaitHostAck(String scenario) async {
  // HTTP 425 means that the independent host has not yet verified Android's
  // installed package paths, exact APK hashes, version, and approval path.
  for (var attempt=0;attempt<120;attempt++) {
    final client=HttpClient()..connectionTimeout=const Duration(seconds:5);
    try {
      final request=await client.getUrl(Uri.parse('http://127.0.0.1:$fixturePort/ack/$scenario'));
      final response=await request.close().timeout(const Duration(seconds:10));
      await response.drain<void>();
      if (response.statusCode==HttpStatus.ok)return;
      if (response.statusCode!=425)throw StateError('Host refused real Android proof');
    } finally {
      client.close(force:true);
    }
    await Future<void>.delayed(const Duration(seconds:2));
  }
  throw StateError('Host did not confirm real Android installation');
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('RT02 fresh APK then split update through real StockInstaller', (tester) async {
    if (!Platform.isAndroid) throw StateError('Android API36 emulator required');
    final digests=<String>[v1Digest,v2Digest,splitDigest];
    if (digests.any((d)=>!RegExp(r'^[0-9a-f]{64}$').hasMatch(d)) ||
        digests.toSet().length!=3) {
      throw StateError('Three distinct signed fixture hashes required');
    }
    for (final scenario in scenarios) {
      debugPrint('OX_R02_P02_EVENT=$scenario:START');
      debugPrint('OX_R02_RT02_DART_STAGE=SCENARIO_STARTED');
      final directory=await Directory.systemTemp.createTemp('obtainx-rt02-p02-');
      try {
        final version=scenario=='standalone'?1:2;
        final base=await exactFixture('base_v$version.apk',
                                      version==1?v1Digest:v2Digest,directory);
        final members=<InstallApkMember>[
          InstallApkMember(path:base.path,packageName:packageName,
                           versionCode:version,minSdkVersion:26,targetSdkVersion:35),
        ];
        if (scenario=='split') {
          final split=await exactFixture('config.x86_64.apk',splitDigest,directory);
          members.add(InstallApkMember(path:split.path,packageName:packageName,
                                       versionCode:2,minSdkVersion:26));
        }
        final plan=resolveInstallBundlePlan(
          members:members,
          format:scenario=='standalone'?InstallArtifactFormat.apk:InstallArtifactFormat.apks,
          supportedAbis:const ['x86_64'],deviceSdkVersion:36,
          expectedPackageName:packageName);
        expect(plan.packageName,packageName);
        expect(plan.versionCode,version);
        expect(plan.sessionPaths.length,scenario=='split'?2:1);
        expect(plan.requiresSplitSession,scenario=='split');
        debugPrint('OX_R02_P02_EVENT=$scenario:INSTALL_CALL');
        debugPrint('OX_R02_RT02_DART_STAGE=INSTALL_CALL');
        final result=await StockInstaller(SettingsProvider()).installApk(
          plan.sessionPaths,appId:packageName,
        ).timeout(const Duration(minutes:3));
        debugPrint('OX_R02_RT02_DART_STAGE=INSTALL_RETURNED');
        expect(result.isSuccess,isTrue,reason:'Real system installer must commit the signed APK');
        debugPrint('OX_R02_P02_EVENT=$scenario:INSTALL_RETURNED');
        await awaitHostAck(scenario);
        debugPrint('OX_R02_P02_EVENT=$scenario:ACKED');
      } finally {
        if (await directory.exists())await directory.delete(recursive:true);
      }
    }
  },timeout:const Timeout(Duration(minutes:35)));
}
