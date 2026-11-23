// P04B P03: real Android native third-party handoff adversarial acceptance.
// Every signal remains UNVERIFIED; no broadcast substitutes for installed APK bytes.
import 'dart:convert';
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:obtainium/providers/installer_provider.dart';
import 'package:obtainium/services/third_party_install_evidence.dart';
import 'package:path_provider/path_provider.dart';

const _sha=String.fromEnvironment('OX_P04B_P03_BASE_SHA');
const _fixture='dev.bikram.obtainx.rt02.fixture';
const _target='dev.bikram.obtainx.p04b.target';
const _component='dev.bikram.obtainx.p04b.target.DeclineActivity';
const _port=18785;

Future<void> _probe(String label) async {
  if (label!='spoof' && label!='late') throw StateError('invalid adversarial probe');
  final client=HttpClient()..connectionTimeout=const Duration(seconds:10);
  try {
    final request=await client.getUrl(Uri.parse('http://127.0.0.1:$_port/p03/$label'));
    final response=await request.close().timeout(const Duration(seconds:25));
    final body=await response.transform(const Utf8Decoder()).join();
    if (response.statusCode!=200 || body!='untrusted_broadcast_sent') {
      throw StateError('host did not execute the bounded untrusted broadcast probe');
    }
  } finally {client.close(force:true);}
}

void _requireUnverified(bool observed) {
  // Even a delayed/stale package signal is never an APK installation receipt.
  final verdict=classifyUnverifiedThirdPartyHandoff(observed);
  expect(verdict.isHandedOff,isTrue);
  expect(verdict.isSuccess,isFalse);
  expect(verdict.isCancelled,isFalse);
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('P03 parallel, spoof, delayed and mismatched versions remain unverified', (tester) async {
    if (!Platform.isAndroid || !RegExp(r'^[0-9a-f]{64}$').hasMatch(_sha)) {
      throw StateError('real hosted Android and exact signed fixture required');
    }
    await tester.pumpWidget(const MaterialApp(home:Scaffold(body:Text('P04B P03'))));
    final root=await getTemporaryDirectory();
    final file=File('${root.path}/p04b-p03-${DateTime.now().microsecondsSinceEpoch}.apk');
    final http=HttpClient()..connectionTimeout=const Duration(seconds:12);
    try {
      final req=await http.getUrl(Uri.parse('http://127.0.0.1:$_port/base_v2.apk'));
      final resp=await req.close().timeout(const Duration(seconds:25));
      if (resp.statusCode!=200) throw StateError('P03 source fixture HTTP refused');
      final bytes=await resp.fold<List<int>>([], (buf,part)=>buf..addAll(part));
      if (bytes.length<300 || bytes.length>16*1024*1024 ||
          sha256.convert(bytes).toString()!=_sha) {
        throw StateError('P03 signed v2 fixture integrity refused');
      }
      await file.writeAsBytes(bytes,flush:true);
      // Two immediate MethodChannel calls. The first watcher must retain its
      // receiver, cache ownership, and response; the second must be rejected.
      final first=installApkViaThirdParty(file.path,
        targetPackage:_target,targetActivity:_component,expectedPackageName:_fixture);
      String? refusal;
      try {
        await installApkViaThirdParty(file.path,
          targetPackage:_target,targetActivity:_component,expectedPackageName:_fixture)
          .timeout(const Duration(seconds:12));
      } on PlatformException catch (e) {refusal=e.code;}
      expect(refusal,'INSTALL_IN_PROGRESS',reason:'parallel native handoff must refuse, not replace watcher');
      debugPrint('OX_P04B_P03_PARALLEL_HANDOFF_REFUSED_PASS');
      // This is an *unprotected custom action*, not PACKAGE_REPLACED. It must
      // never complete a watcher or change the signed v1 installed package.
      await _probe('spoof');
      debugPrint('OX_P04B_P03_SPOOF_ACTION_UNTRUSTED_PASS');
      final firstObserved=await first.timeout(const Duration(seconds:85));
      expect(firstObserved,isFalse,reason:'declined external session must not inherit spoofed change');
      _requireUnverified(firstObserved);
      // Deliver a late custom signal after the first handoff has completed;
      // it must not be replayed as evidence for a later new watcher.
      await _probe('late');
      debugPrint('OX_P04B_P03_DELAYED_SIGNAL_UNVERIFIED_PASS');
      final wrongPackage=await installApkViaThirdParty(file.path,
        targetPackage:_target,targetActivity:_component,
        expectedPackageName:'$_fixture.mismatched')
        .timeout(const Duration(seconds:85));
      expect(wrongPackage,isFalse);
      _requireUnverified(wrongPackage);
      _requireUnverified(true); // even a matching broadcast is only a handoff
      debugPrint('OX_P04B_P03_MISMATCHED_PACKAGE_NO_FALSE_SUCCESS_PASS');
    } finally {
      http.close(force:true);
      if (await file.exists()) await file.delete();
    }
  });
}
