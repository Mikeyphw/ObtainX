/// Positive process ownership for interrupted journal recovery. No signal is
/// sent and unreadable process identity is never treated as proof of death.
library;

import 'dart:io';

import 'package:obtainium/services/r07_journal_guard.dart';

enum R07ProcessState { live, dead, unknown }

class R07ProcessOwner {
  const R07ProcessOwner._(this.processId, this.startTicks, this.boot);
  final int processId;
  final int? startTicks;
  final String? boot;

  String encode() => '$processId:${startTicks ?? 'unknown'}:${boot ?? 'unknown'}';

  static R07ProcessOwner decode(String value) {
    final match = RegExp(r'^([1-9][0-9]{0,9}):([0-9]{1,18}|unknown):([a-f0-9]{64}|unknown)$').firstMatch(value);
    if (match == null) throw const FormatException('Invalid process owner');
    return R07ProcessOwner._(int.parse(match.group(1)!), int.tryParse(match.group(2)!),
      match.group(3) == 'unknown' ? null : match.group(3));
  }

  static Future<String?> _boot() async {
    try {
      final value = (await File('/proc/sys/kernel/random/boot_id').readAsString()).trim();
      return RegExp(r'^[a-fA-F0-9-]{36}$').hasMatch(value) ? r07JournalFingerprint(value) : null;
    } on FileSystemException { return null; }
  }

  static Future<int?> _ticks(int processId) async {
    final stat = await File('/proc/$processId/stat').readAsString();
    final end = stat.lastIndexOf(')');
    if (end < 0) return null;
    final fields = stat.substring(end + 1).trim().split(RegExp(r'\s+'));
    return fields.length > 19 ? int.tryParse(fields[19]) : null;
  }

  static Future<R07ProcessOwner> capture() => observe(pid);

  static Future<R07ProcessOwner> observe(int processId) async {
    if (processId <= 0) { throw ArgumentError.value(processId); }
    int? ticks;
    try { ticks = await _ticks(processId); } on FileSystemException { /* unknown */ }
    return R07ProcessOwner._(processId, ticks, await _boot());
  }

  Future<R07ProcessState> inspect() async {
    final currentBoot = await _boot();
    if (boot != null && currentBoot != null && boot != currentBoot) return R07ProcessState.dead;
    if (startTicks == null) return R07ProcessState.unknown;
    try {
      final ticks = await _ticks(processId);
      if (ticks == null) return R07ProcessState.unknown;
      if (ticks != startTicks) return R07ProcessState.dead;
      // A matching PID and tick after an unidentifiable reboot cannot
      // prove continuity; same current process is sufficient for liveness.
      return processId == pid || (boot != null && boot == currentBoot)
          ? R07ProcessState.live : R07ProcessState.unknown;
    } on FileSystemException catch (error) {
      // Same-app processes share a UID. ENOENT with a readable self identity
      // and the same known boot can establish absence of the captured owner.
      // EACCES, other I/O errors, or missing boot identity stay unknown.
      if (error.osError?.errorCode == 2 && boot != null && boot == currentBoot) {
        try {
          if (await _ticks(pid) != null) return R07ProcessState.dead;
        } on FileSystemException { /* no positive observation */ }
      }
      return R07ProcessState.unknown;
    }
  }
}
