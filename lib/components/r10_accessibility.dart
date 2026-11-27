import 'dart:async' show unawaited;

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

/// One threshold state for visual arming, feedback and release. The caller
/// supplies the existing production capability checks and guarded haptic helper.
class R10SwipeThreshold {
  static const double distance = 80;
  int _armed = 0;

  static int direction(double offset, {required bool left, required bool right}) {
    if (right && offset >= distance) return 1;
    if (left && offset <= -distance) return -1;
    return 0;
  }

  bool update(double offset, {required bool left, required bool right}) {
    final int next = direction(offset, left: left, right: right);
    final bool pulse = next != 0 && next != _armed;
    _armed = next;
    return pulse;
  }

  void reset() => _armed = 0;
}

/// A drag-end callback alone does not establish a successful release: Flutter
/// also ends accepted drags on pointer cancellation. Authorize one action only
/// after the actual single-pointer up event, before recognizer dispatch.
class R10SwipeRelease {
  final Set<int> _pointers = <int>{};
  bool _single = false;
  bool _released = false;

  void pointerDown(int pointer) {
    _single = _pointers.isEmpty;
    _released = false;
    _pointers.add(pointer);
  }

  void pointerUp(int pointer) {
    final only = _pointers.length == 1;
    final tracked = _pointers.remove(pointer);
    _released = tracked && only && _single;
  }

  void pointerCancel(int pointer) {
    _pointers.remove(pointer);
    invalidate();
  }

  void invalidate() {
    _single = false;
    _released = false;
  }

  bool consumeRelease() {
    final result = _released;
    invalidate();
    return result;
  }
}

/// Direct manipulation retains its existing visual proportions. The platform
/// accessibility preference disables scaling; both motion preferences still
/// suppress the time-driven settle animation in the row.
double r10SwipeRevealScale(double progress, {required bool disableAnimations}) =>
    disableAnimations ? 1.0 : 0.88 + 0.12 * progress;

/// The tracked listing's original source, not its latest artifact or a
/// different listing's URL. Reject non-web schemes and embedded credentials.
Uri? r10SourceHomepage(String source) {
  final uri = Uri.tryParse(source);
  if (uri == null ||
      !const {'http', 'https'}.contains(uri.scheme.toLowerCase()) ||
      uri.host.isEmpty || uri.userInfo.isNotEmpty) {
    return null;
  }
  return uri;
}

Future<bool> r10OpenSourceHomepage(String source) async {
  final uri = r10SourceHomepage(source);
  if (uri == null) return false;
  try {
    return await launchUrl(uri, mode: LaunchMode.externalApplication);
  } catch (_) {
    // Never log a possibly credential-bearing query or use an implicit
    // fallback to a different source or to an install action.
    return false;
  }
}

bool r10ReduceMotion(BuildContext context, bool preference) =>
    preference || MediaQuery.disableAnimationsOf(context);

/// Horizontal navigation never scales down touch targets. The scrollable
/// keeps every item reachable even with narrow split-screen constraints.
class R10NavigationStrip extends StatelessWidget {
  const R10NavigationStrip({super.key, required this.children});
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return FocusTraversalGroup(
      child: LayoutBuilder(builder: (context, constraints) {
        return SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: ConstrainedBox(
            constraints: BoxConstraints(minWidth: constraints.maxWidth),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              mainAxisAlignment: MainAxisAlignment.center,
              children: children,
            ),
          ),
        );
      }),
    );
  }
}

/// Material keyboard activation, a real focus indicator, and the same label
/// for touch, TalkBack and remote input. Reveal focused items when scrolled.
class R10NavigationTarget extends StatelessWidget {
  const R10NavigationTarget({super.key, required this.label, required this.selected,
    required this.onTap, required this.child});
  final String label;
  final bool selected;
  final VoidCallback onTap;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Semantics(
      button: true,
      selected: selected,
      label: label,
      child: Tooltip(
        message: label,
        excludeFromSemantics: true,
        child: InkWell(
          borderRadius: BorderRadius.circular(22),
          focusColor: cs.primary.withValues(alpha: 0.24),
          onFocusChange: (focused) {
            if (focused) {
              unawaited(Scrollable.ensureVisible(context, duration: Duration.zero,
                alignment: 0.5));
            }
          },
          onTap: onTap,
          child: ExcludeSemantics(
            child: ConstrainedBox(
              constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
              child: child,
            ),
          ),
        ),
      ),
    );
  }
}

/// Full text can wrap instead of being shrunk inside a fixed-height bar.
class R10PrimaryActions extends StatelessWidget {
  const R10PrimaryActions({super.key, required this.first, required this.second});
  final Widget first;
  final Widget second;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, constraints) {
      final textScale = MediaQuery.textScalerOf(context).scale(16) / 16;
      if (constraints.maxWidth < 360 * textScale) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [first, const SizedBox(height: 8), second],
        );
      }
      return Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [Expanded(child: first), const SizedBox(width: 10),
          Expanded(child: second)],
      );
    });
  }
}
