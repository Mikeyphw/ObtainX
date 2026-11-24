/// R05 independent user approval policy; R07 owns the Activity Center.
library;

import 'package:flutter/material.dart';
import 'package:obtainium/services/r05_operation_receipt.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Additional confirmation is opt-in. Android's mandatory confirmation is never bypassed.
class R05ExtraApprovalTile extends StatefulWidget {
  const R05ExtraApprovalTile({super.key});
  @override
  State<R05ExtraApprovalTile> createState() => _R05ExtraApprovalTileState();
}

class _R05ExtraApprovalTileState extends State<R05ExtraApprovalTile> {
  bool enabled = false;
  bool busy = true;
  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      if (mounted) {
        setState(() {
          enabled = prefs.getBool(r05ExtraApprovalPreference) ?? false;
          busy = false;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() => busy = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) => SwitchListTile(
    key: const ValueKey('r05-extra-install-approval'),
    title: const Text('Extra install approval'),
    subtitle: const Text('Optional additional confirmation. Android security prompts always remain required. Background attempts await review when enabled.'),
    value: enabled,
    onChanged: busy ? null : (value) async {
      setState(() => busy = true);
      try {
        final prefs = await SharedPreferences.getInstance();
        if (!await prefs.setBool(r05ExtraApprovalPreference, value)) {
          throw StateError('Could not persist install approval preference');
        }
        if (mounted) {
          setState(() => enabled = value);
        }
      } catch (_) {
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Extra approval preference could not be saved')),
          );
        }
      } finally {
        if (mounted) {
          setState(() => busy = false);
        }
      }
    },
  );
}

