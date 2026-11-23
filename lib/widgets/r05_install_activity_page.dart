/// Minimal R05 recovery surface; R07 expands this into the full Activity Center.
library;

import 'package:flutter/material.dart';
import 'package:obtainium/providers/apps_provider.dart';
import 'package:obtainium/services/r05_operation_journal.dart';
import 'package:obtainium/services/r05_operation_receipt.dart';
import 'package:provider/provider.dart';
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

class R05InstallActivityPage extends StatefulWidget {
  const R05InstallActivityPage({super.key});
  @override
  State<R05InstallActivityPage> createState() => _R05InstallActivityPageState();
}

class _R05InstallActivityPageState extends State<R05InstallActivityPage> {
  late Future<List<R05OperationReceipt>> _operations;
  bool _checking = false;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  void _reload() {
    _operations = R05OperationJournal.instance.list();
  }

  Future<void> _reconcile() async {
    if (_checking) {
      return;
    }
    setState(() => _checking = true);
    try {
      await context.read<AppsProvider>().reconcileR05OperationReceipts();
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Reconciliation could not complete. No installation was assumed successful.')),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _checking = false;
          _reload();
        });
      }
    }
  }

  Future<void> _retry(R05OperationReceipt receipt) async {
    final provider = context.read<AppsProvider>();
    if (provider.apps[receipt.listingKey]?.app.id != receipt.packageId) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Tracked listing changed; retry requires reviewing the app again.')),
      );
      return;
    }
    try {
      await provider.downloadAndInstallLatestApps(<String>[receipt.listingKey], context);
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Retry could not finish. Check the operation log.')),
        );
      }
    } finally {
      if (mounted) {
        setState(_reload);
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Install activity'),
      actions: <Widget>[
        IconButton(
          tooltip: 'Recheck installed packages', icon: const Icon(Icons.refresh_rounded),
          onPressed: _checking ? null : _reconcile,
        ),
      ],
    ),
    body: FutureBuilder<List<R05OperationReceipt>>(
      future: _operations,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return const Center(child: Text(
            'Install history could not be read. Data was not erased; inspect the app diagnostics.',
          ));
        }
        if (!snapshot.hasData) {
          return const Center(child: CircularProgressIndicator());
        }
        final records = snapshot.data!;
        if (records.isEmpty) {
          return const Center(child: Text('No recorded installation attempts'));
        }
        return ListView.separated(
          itemCount: records.length,
          separatorBuilder: (_, _) => const Divider(height: 1),
          itemBuilder: (context, index) {
            final record = records[index];
            final unresolved = record.stage == R05InstallStage.unknown ||
                record.stage == R05InstallStage.awaitingApproval ||
                record.stage == R05InstallStage.handedOff;
            return Semantics(
              label: 'Install attempt for ${record.packageId}, ${record.stage.name}',
              child: ListTile(
                key: ValueKey('r05-receipt-${record.id}'),
                leading: Icon(record.stage == R05InstallStage.confirmed
                    ? Icons.verified_rounded
                    : unresolved ? Icons.help_outline_rounded : Icons.info_outline_rounded),
                title: Text(record.packageId),
                subtitle: Text('${record.stage.name} • ${record.backend} • ${record.updatedUtc.toLocal()}\n'
                    '${record.reason ?? 'Only independently verified installs are confirmed.'}'),
                isThreeLine: true,
                onTap: () => showDialog<void>(
                  context: context,
                  builder: (dialog) => AlertDialog(
                    title: Text(record.stage.name),
                    content: SingleChildScrollView(child: SelectableText(
                      'Package: ${record.packageId}\n'
                      'Source host: ${record.sourceHost ?? 'unknown'}\n'
                      'Commit: ${record.commitSha ?? 'unknown'}\n'
                      'Workflow/run/artifact: ${record.workflow ?? '-'}/${record.runId ?? '-'}/${record.artifactId ?? '-'}\n'
                      'Downloaded SHA-256: ${record.downloadSha256 ?? 'not recorded'}\n'
                      'Installed signer: ${record.installedSignerSha256 ?? 'not independently verified'}\n'
                      'Backend: ${record.backend}\nAndroid result code: ${record.androidCode ?? 'none'}\n'
                      'Status: ${record.stage.name}\nVerified at: ${record.verifiedUtc ?? 'not verified'}',
                    )),
                    actions: <Widget>[TextButton(onPressed: () => Navigator.pop(dialog),
                      child: const Text('Close'))],
                  ),
                ),
                trailing: unresolved ? TextButton(
                  onPressed: () => _retry(record), child: const Text('Review / retry'),
                ) : null,
              ),
            );
          },
        );
      },
    ),
  );
}
