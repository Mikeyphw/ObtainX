/// User-initiated, read-only GitHub Actions history browser. The UI does not
/// dispatch workflows, download archives or request installation privileges.
library;

import 'package:flutter/material.dart';
import 'package:obtainium/services/r04_github_actions.dart';

typedef R04ActionsHistoryLoader = Future<List<R04ActionsHistoryItem>> Function(
  String repositoryUrl,
  String? branch,
  String? workflow,
);

class R04ActionsHistoryDialog extends StatefulWidget {
  const R04ActionsHistoryDialog({
    super.key,
    required this.loadHistory,
    this.initialRepositoryUrl = '',
    this.initialBranch = '',
    this.initialWorkflow = '',
    this.now,
  });

  final R04ActionsHistoryLoader loadHistory;
  final String initialRepositoryUrl;
  final String initialBranch;
  final String initialWorkflow;
  final DateTime Function()? now;

  @override
  State<R04ActionsHistoryDialog> createState() => _R04ActionsHistoryDialogState();
}

class _R04ActionsHistoryDialogState extends State<R04ActionsHistoryDialog> {
  late final TextEditingController repository;
  late final TextEditingController branch;
  late final TextEditingController workflow;
  DateTime now() => widget.now?.call() ?? DateTime.now();
  bool busy = false;
  bool searched = false;
  String? error;
  List<R04ActionsHistoryItem> rows = const [];

  @override
  void initState() {
    super.initState();
    repository = TextEditingController(text: widget.initialRepositoryUrl);
    branch = TextEditingController(text: widget.initialBranch);
    workflow = TextEditingController(text: widget.initialWorkflow);
  }

  @override
  void dispose() {
    repository.dispose();
    branch.dispose();
    workflow.dispose();
    super.dispose();
  }

  Future<void> search() async {
    if (busy) {
      return;
    }
    setState(() { busy = true; searched = true; error = null; rows = const []; });
    try {
      final result = await widget.loadHistory(
        repository.text.trim(),
        branch.text.trim().isEmpty ? null : branch.text.trim(),
        workflow.text.trim().isEmpty ? null : workflow.text.trim(),
      );
      if (!mounted) {
        return;
      }
      setState(() { rows = result; busy = false; });
    } catch (_) {
      if (!mounted) {
        return;
      }
      // Do not print tokens, private API bodies or signed redirect URLs.
      setState(() {
        error = 'Could not list Actions runs. Check repository, permissions, branch and rate limit.';
        busy = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Manual GitHub Actions history'),
      content: SizedBox(
        width: 560,
        height: (MediaQuery.sizeOf(context).height * 0.62)
            .clamp(230.0, 460.0).toDouble(),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('Only completed successful runs with an advertised SHA-256 Android ZIP are selectable. The downloaded bytes are verified later.'),
            const SizedBox(height: 12),
            TextField(
              controller: repository,
              readOnly: true,
              keyboardType: TextInputType.url,
              decoration: const InputDecoration(
                labelText: 'GitHub repository URL',
                hintText: 'https://github.com/owner/repo',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 8),
            Wrap(spacing: 8, runSpacing: 8, children: [
              SizedBox(width: 240, child: TextField(
                controller: branch,
                enabled: !busy,
                onChanged: (_) => setState(() { rows = const []; searched = false; error = null; }),
                decoration: const InputDecoration(labelText: 'Branch (default if blank)',
                  border: OutlineInputBorder()),
              )),
              SizedBox(width: 240, child: TextField(
                controller: workflow,
                enabled: !busy,
                onChanged: (_) => setState(() { rows = const []; searched = false; error = null; }),
                decoration: const InputDecoration(labelText: 'Workflow ID/name (optional)',
                  border: OutlineInputBorder()),
              )),
            ]),
            const SizedBox(height: 8),
            Row(children: [
              FilledButton.icon(onPressed: busy ? null : search,
                icon: const Icon(Icons.search), label: const Text('Browse runs')),
              if (busy) const Padding(padding: EdgeInsets.only(left: 16),
                child: SizedBox(width: 18, height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))),
            ]),
            const SizedBox(height: 8),
            Expanded(child: error != null
              ? Center(child: Text(error!, textAlign: TextAlign.center))
              : rows.isEmpty
                ? Center(child: Text(searched && !busy
                    ? 'No matching runs/artifacts in the bounded history.'
                    : 'Browse to inspect workflows, attempts and artifacts.'))
                : ListView.builder(
                    itemCount: rows.length,
                    itemBuilder: (context, index) {
                      final row = rows[index];
                      return Card(
                        child: ListTile(
                          isThreeLine: true,
                          title: Text('${row.workflowName} · run ${row.runId} · attempt ${row.runAttempt}'),
                          subtitle: Text(
                            '${row.status} · ${row.branch} · ${row.commitSha.substring(0, 12)}\n'
                            '${row.artifactName ?? 'No artifact'}'
                            '${row.artifactId == null ? '' : ' · ID ${row.artifactId}'} · ${row.reason}\n'
                            'Size: ${row.sizeBytes ?? 'unknown'} B · Expires: ${row.expiresAt?.toUtc().toIso8601String() ?? 'unknown'}\n'
                            '${row.archiveSha256 == null ? 'No ZIP digest' : 'Advertised ZIP SHA-256 (not APK signer)'} · APK metadata pending download',
                          ),
                          trailing: row.canSelectAt(now())
                            ? TextButton(onPressed: () {
                                if (row.canSelectAt(now())) {
                                  Navigator.of(context).pop(row);
                                } else {
                                  setState(() {});
                                }
                              },
                                child: const Text('Select'))
                            : const Icon(Icons.block, semanticLabel: 'Unavailable'),
                        ),
                      );
                    },
                  )),
          ],
        ),
      ),
      actions: [TextButton(onPressed: () => Navigator.of(context).pop(),
        child: const Text('Close'))],
    );
  }
}
