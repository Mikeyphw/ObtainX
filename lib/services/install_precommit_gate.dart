import 'package:flutter/foundation.dart';

/// R02F P03: an exact-listing, single-use cancellation owner. A cancelled
/// request is not a verified rollback until Android has independently reported
/// abandonment and the installed baseline was compared.
class InstallPrecommitGate {
  InstallPrecommitGate(this.listingKey, this.generation);

  final String listingKey;
  final int generation;
  bool _cancelRequested = false;
  bool _sealed = false;
  bool _nativeCancelable = false;
  bool _finished = false;
  final Set<VoidCallback> _cancelListeners = {};

  bool get canCancel => !_cancelRequested && !_finished &&
      (!_sealed || _nativeCancelable);
  bool get wasCancelled => _cancelRequested;
  bool get isSealed => _sealed;
  bool get nativeCancelable => _nativeCancelable;
  bool get isFinished => _finished;

  bool requestCancel() {
    if (!canCancel) return false;
    _cancelRequested = true;
    for (final listener in _cancelListeners.toList(growable: false)) {
      listener();
    }
    _cancelListeners.clear();
    return true;
  }

  /// This synchronous barrier must be adjacent to the platform handoff.
  /// Only a stock installer with a known, app-owned session can remain
  /// cancelable after sealing; external/privileged routes cannot be undone.
  bool sealForHandoff({bool nativeCancelable = false}) {
    if (_cancelRequested || _sealed || _finished) return false;
    _sealed = true;
    _nativeCancelable = nativeCancelable;
    return true;
  }

  void addCancelListener(VoidCallback listener) {
    if (_cancelRequested) {
      listener();
    } else if (!_finished) {
      _cancelListeners.add(listener);
    }
  }

  void removeCancelListener(VoidCallback listener) {
    _cancelListeners.remove(listener);
  }

  void finish() {
    _finished = true;
    _nativeCancelable = false;
    _cancelListeners.clear();
  }
}

class InstallPrecommitRegistry {
  final Map<String, InstallPrecommitGate> _gates = {};
  int _nextGeneration = 0;

  bool canCancel(String listingKey) => _gates[listingKey]?.canCancel ?? false;

  InstallPrecommitGate begin(String listingKey) {
    if (_gates.containsKey(listingKey)) {
      throw StateError('Install preparation already active for $listingKey');
    }
    final gate = InstallPrecommitGate(listingKey, ++_nextGeneration);
    _gates[listingKey] = gate;
    return gate;
  }

  bool requestCancel(String listingKey) =>
      _gates[listingKey]?.requestCancel() ?? false;

  bool sealForHandoff(InstallPrecommitGate gate, {bool nativeCancelable = false}) {
    if (!identical(_gates[gate.listingKey], gate)) return false;
    return gate.sealForHandoff(nativeCancelable: nativeCancelable);
  }

  void finish(String listingKey, InstallPrecommitGate gate) {
    if (!identical(_gates[listingKey], gate)) return;
    gate.finish();
    _gates.remove(listingKey);
  }
}
