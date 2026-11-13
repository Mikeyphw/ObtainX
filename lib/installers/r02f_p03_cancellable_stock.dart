import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:obtainium/installers/installer.dart';
import 'package:obtainium/services/install_precommit_gate.dart';

/// The private first-party PackageInstaller bridge is used only for explicit
/// foreground ObtainX operations. Old silent/background paths retain their
/// existing plugin and semantics.
class R02fP03CancellableStock {
  R02fP03CancellableStock._();
  static final instance = R02fP03CancellableStock._();
  static const channel = MethodChannel('dev.imranr.obtainium/r02f_p03_session');

  Future<InstallResult> install(
    List<String> paths, {
    required String appId,
    required InstallPrecommitGate owner,
  }) async {
    if (!Platform.isAndroid || !owner.isSealed || !owner.nativeCancelable) {
      return InstallResult.error(-1);
    }
    if (owner.wasCancelled) return InstallResult.cancelled();
    final Map<dynamic, dynamic>? staged = await channel.invokeMethod<Map<dynamic, dynamic>>(
      'stage', <String, Object>{
        'paths': paths,
        'packageName': appId,
        'listingKey': owner.listingKey,
      },
    );
    final id = staged?['id']?.toString();
    if (id == null || id.isEmpty) {
      throw PlatformException(code: 'P03_STAGE_REFUSED');
    }
    // Listener and completion may race. Only one native cancellation request
    // is issued for this exact operation; a late result is never rounded up to
    // success. The native commit response remains the terminal authority.
    Future<Map<dynamic, dynamic>?>? cancellation;
    Future<Map<dynamic, dynamic>?> cancelOnce() => cancellation ??= channel
        .invokeMethod<Map<dynamic, dynamic>>('cancel', {'id': id})
        .catchError((Object _) => <dynamic, dynamic>{'status': 'unknown'});
    void onCancel() { unawaited(cancelOnce()); }
    if (!owner.wasCancelled) owner.addCancelListener(onCancel);
    try {
      if (owner.wasCancelled) {
        final response = await cancelOnce();
        return response?['status'] == 'cancelled'
            ? InstallResult.cancelled() : InstallResult.handedOff();
      }
      final Map<dynamic, dynamic>? terminal = await channel
          .invokeMethod<Map<dynamic, dynamic>>('commit', {'id': id})
          .timeout(const Duration(minutes: 3), onTimeout: () => null);
      final outcome = terminal?['outcome'];
      if (outcome == 'success') return InstallResult.success();
      if (outcome == 'cancelled') return InstallResult.cancelled();
      if (outcome == 'unknown' || terminal == null) return InstallResult.handedOff();
      return InstallResult.error(-1);
    } finally {
      owner.removeCancelListener(onCancel);
      // No operation may remain falsely cancellable after a terminal/unknown
      // native reply; unknown stays in Android's durable journal for recovery.
      owner.finish();
    }
  }

  /// Returns the durable native journal for recovery after route changes or
  /// Android process recreation. A null value is NOT a verified terminal state.
  Future<Map<String, dynamic>> snapshot() async {
    if (!Platform.isAndroid) return <String, dynamic>{};
    final data = await channel.invokeMethod<Map<dynamic, dynamic>>('pending');
    if (data == null) throw const FormatException('Missing native P03 journal response');
    Map<String, dynamic>? decodeMap(Object? raw) {
      if (raw is! String) return null;
      final result = jsonDecode(raw);
      if (result is! Map<String, dynamic>) {
        throw const FormatException('Malformed native P03 journal entry');
      }
      return result;
    }
    return <String, dynamic>{
      'active': decodeMap(data['active']),
      'terminal': decodeMap(data['terminal']),
      'orphanStatus': decodeMap(data['orphanStatus']),
    };
  }

  Future<Map<String, dynamic>?> pending() async {
    final state = await snapshot();
    return state['active'] as Map<String, dynamic>?;
  }

  Future<String> cancelRecovered(String id) async {
    if (!Platform.isAndroid) return 'unknown';
    final data = await channel.invokeMethod<Map<dynamic, dynamic>>('cancel', {'id': id});
    return data?['status']?.toString() ?? 'unknown';
  }
}
