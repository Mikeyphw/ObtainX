import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/services/install_precommit_gate.dart';

void main() {
  group('R02F P03 native session, owner and cancellation state', () {
    test('user cancellation before platform handoff refuses the install', () {
      final registry = InstallPrecommitRegistry();
      final gate = registry.begin('example.app');
      expect(registry.canCancel('example.app'), true);
      expect(registry.requestCancel('example.app'), true);
      expect(registry.sealForHandoff(gate), false);
      expect(gate.wasCancelled, true);
      registry.finish('example.app', gate);
      expect(registry.canCancel('example.app'), false);
    });

    test('native pending-approval session remains cancellable', () {
      final registry = InstallPrecommitRegistry();
      final gate = registry.begin('example.app');
      var cancelledNative = 0;
      expect(registry.sealForHandoff(gate, nativeCancelable: true), true);
      expect(registry.canCancel('example.app'), true);
      gate.addCancelListener(() => cancelledNative++);
      expect(registry.requestCancel('example.app'), true);
      expect(cancelledNative, 1);
      expect(registry.requestCancel('example.app'), false);
      registry.finish('example.app', gate);
    });

    test('an external handoff cannot be cancelled after sealing', () {
      final registry = InstallPrecommitRegistry();
      final gate = registry.begin('example.app');
      expect(registry.sealForHandoff(gate), true);
      expect(registry.requestCancel('example.app'), false);
      expect(gate.isSealed, true);
      registry.finish('example.app', gate);
    });

    test('two listings for one package never share an owner', () {
      final registry = InstallPrecommitRegistry();
      final a = registry.begin('example.app@fdroid');
      final b = registry.begin('example.app@github');
      expect(registry.sealForHandoff(a, nativeCancelable: true), true);
      expect(registry.requestCancel('example.app@fdroid'), true);
      expect(registry.requestCancel('example.app@github'), true);
      expect(b.wasCancelled, true);
      registry.finish('example.app@fdroid', a);
      registry.finish('example.app@github', b);
    });

    test('process restart never fabricates prior success', () {
      final before = InstallPrecommitRegistry();
      before.begin('example.app').sealForHandoff(nativeCancelable: true);
      final after = InstallPrecommitRegistry();
      expect(after.canCancel('example.app'), false);
      expect(after.requestCancel('example.app'), false);
      // Native persisted session and independent PackageManager are necessary.
    });

    test('old token cannot cancel or seal a new retry', () {
      final registry = InstallPrecommitRegistry();
      final old = registry.begin('example.app');
      registry.finish('example.app', old);
      final retry = registry.begin('example.app');
      registry.finish('example.app', old);
      expect(registry.sealForHandoff(old, nativeCancelable: true), false);
      expect(registry.sealForHandoff(retry, nativeCancelable: true), true);
      registry.finish('example.app', retry);
      expect(retry.isFinished, true);
    });

    test('listeners are not run twice on double cancellation', () {
      final gate = InstallPrecommitRegistry().begin('other.app');
      var count = 0;
      gate.addCancelListener(() => count++);
      expect(gate.requestCancel(), true);
      expect(gate.requestCancel(), false);
      expect(count, 1);
    });

    test('finished token never dispatches or accepts cancellation', () {
      final registry = InstallPrecommitRegistry();
      final gate = registry.begin('other.app');
      registry.finish('other.app', gate);
      expect(registry.sealForHandoff(gate, nativeCancelable: true), false);
      expect(gate.requestCancel(), false);
    });
  });
}
