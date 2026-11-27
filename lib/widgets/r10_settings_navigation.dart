import 'package:flutter/material.dart';

/// A navigation result, never a setting value. Search does not read or edit
/// preferences, credentials or hidden form state.
class R10SettingsSearchEntry {
  const R10SettingsSearchEntry(this.section, this.title, this.sectionTitle);

  final String section;
  final String title;
  final String sectionTitle;
}

List<R10SettingsSearchEntry> r10SearchSettings(
  List<R10SettingsSearchEntry> entries,
  String query,
) {
  final words = query.toLowerCase().trim().split(RegExp(r'\s+'));
  return entries.where((entry) {
    final haystack = '${entry.title} ${entry.sectionTitle}'.toLowerCase();
    return words.every(haystack.contains);
  }).toList(growable: false);
}

/// Search opens the real settings section, not a duplicate editable control.
/// The section retains its normal capability checks and unsaved-input policy.
class R10SettingsSearchDialog extends StatefulWidget {
  const R10SettingsSearchDialog({
    super.key,
    required this.entries,
    required this.searchLabel,
    required this.hint,
    required this.noMatch,
    required this.closeLabel,
  });

  final List<R10SettingsSearchEntry> entries;
  final String searchLabel;
  final String hint;
  final String noMatch;
  final String closeLabel;

  @override
  State<R10SettingsSearchDialog> createState() => _R10SettingsSearchDialogState();
}

class _R10SettingsSearchDialogState extends State<R10SettingsSearchDialog> {
  String _query = '';

  @override
  Widget build(BuildContext context) {
    final matches = r10SearchSettings(widget.entries, _query);
    return Dialog(
      insetPadding: const EdgeInsets.all(12),
      child: SizedBox(
        width: 560,
        height: 560,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            TextField(
              autofocus: true,
              textInputAction: TextInputAction.search,
              decoration: InputDecoration(
                labelText: widget.searchLabel,
                prefixIcon: const Icon(Icons.search),
                suffixIcon: IconButton(
                  tooltip: widget.closeLabel,
                  icon: const Icon(Icons.close),
                  onPressed: () => Navigator.of(context).pop(),
                ),
              ),
              onChanged: (query) => setState(() => _query = query),
              onSubmitted: (_) {
                if (matches.length == 1) {
                  Navigator.of(context).pop(matches.single.section);
                }
              },
            ),
            const SizedBox(height: 12),
            Text(widget.hint),
            if (matches.isEmpty)
              Semantics(liveRegion: true, child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 20),
                child: Text(widget.noMatch),
              )),
            for (final entry in matches)
              ListTile(
                title: Text(entry.title),
                subtitle: entry.title == entry.sectionTitle
                    ? null : Text(entry.sectionTitle),
                leading: const Icon(Icons.tune),
                onTap: () => Navigator.of(context).pop(entry.section),
              ),
          ],
        ),
      ),
    );
  }
}

/// The same wrapping, focus-visible navigation target is used on both layouts.
/// The minimum height is not a fixed height, so translations and large text
/// can grow without clipping. InkWell supplies native keyboard/D-pad activation.
class R10SettingsNavigationTile extends StatelessWidget {
  const R10SettingsNavigationTile({
    super.key,
    required this.title,
    required this.icon,
    required this.onTap,
    required this.radius,
    this.expanded,
    this.selected,
    this.focusNode,
  });

  final String title;
  final IconData icon;
  final VoidCallback onTap;
  final double radius;
  final bool? expanded;
  final bool? selected;
  final FocusNode? focusNode;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final active = expanded == true || selected == true;
    final background = active ? cs.secondaryContainer : cs.surfaceContainer;
    final foreground = active ? cs.onSecondaryContainer : cs.onSurface;
    final shape = BorderRadius.circular(radius);
    return Semantics(
      button: true,
      expanded: expanded,
      selected: selected,
      child: Material(
        color: background,
        borderRadius: shape,
        child: InkWell(
          focusNode: focusNode,
          borderRadius: shape,
          focusColor: cs.primary.withValues(alpha: 0.20),
          onTap: onTap,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 56),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              child: Row(
                children: [
                  Icon(icon, color: foreground),
                  const SizedBox(width: 12),
                  Expanded(child: Text(title, style: TextStyle(color: foreground,
                    fontWeight: active ? FontWeight.w600 : FontWeight.w500))),
                  const SizedBox(width: 8),
                  Icon(expanded == true ? Icons.expand_more : Icons.chevron_right,
                    color: foreground),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
