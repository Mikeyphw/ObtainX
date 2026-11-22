import 'package:flutter/material.dart';
import 'package:obtainium/providers/apps_provider.dart';
import 'package:provider/provider.dart';

/// The same production provider-bound Cancel action used in App details,
/// app-list rows and the hosted Flutter integration test. Tapping this widget
/// never calls `adb install-abandon` or a test-only installer implementation.
class R02fP03CancelButton extends StatelessWidget {
  const R02fP03CancelButton({
    super.key,
    required this.listingKey,
    required this.label,
    this.compact = false,
  });

  final String listingKey;
  final String label;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<AppsProvider>();
    if (!provider.canCancelInstallPreparation(listingKey)) {
      return const SizedBox.shrink();
    }
    final theme = Theme.of(context);
    void cancel() => context.read<AppsProvider>()
        .cancelInstallPreparation(listingKey);
    if (compact) {
      return IconButton.filledTonal(
        key: Key('p03-cancel-$listingKey'),
        tooltip: label,
        style: IconButton.styleFrom(
          fixedSize: const Size.square(32),
          minimumSize: const Size.square(32),
          padding: EdgeInsets.zero,
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
          backgroundColor: theme.colorScheme.errorContainer,
          foregroundColor: theme.colorScheme.onErrorContainer,
        ),
        icon: const Icon(Icons.stop_rounded, size: 19),
        onPressed: cancel,
      );
    }
    return TextButton(
      key: Key('p03-cancel-$listingKey'),
      onPressed: cancel,
      child: Text(label),
    );
  }
}
