import 'package:flutter/material.dart';

/// An explicit, readable version block for the R06 app details overview.
///
/// This is presentation-only: it does not derive update eligibility or
/// reinterpret source-version evidence. The existing version decision engine
/// remains the sole authority for status and install actions.
class R06VersionTile extends StatelessWidget {
  const R06VersionTile({
    super.key,
    required this.label,
    required this.value,
    this.annotation,
    this.indicators = const <Widget>[],
  });

  final String label;
  final String value;
  final String? annotation;
  final List<Widget> indicators;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme scheme = theme.colorScheme;
    return Semantics(
      container: true,
      label: '$label: $value${annotation == null ? '' : '. $annotation'}',
      child: Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: scheme.surfaceContainerLow,
            border: Border.all(color: scheme.outlineVariant),
            borderRadius: BorderRadius.circular(16),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(
                  label,
                  style: theme.textTheme.labelMedium?.copyWith(
                    color: scheme.onSurfaceVariant,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 4),
                SelectableText(
                  value,
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontFamily: 'monospace',
                    fontWeight: FontWeight.w600,
                  ),
                ),
                if (indicators.isNotEmpty) ...<Widget>[
                  const SizedBox(height: 8),
                  Wrap(spacing: 8, runSpacing: 6, children: indicators),
                ],
                if (annotation != null && annotation!.isNotEmpty) ...<Widget>[
                  const SizedBox(height: 6),
                  SelectableText(
                    annotation!,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
