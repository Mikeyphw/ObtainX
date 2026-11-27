import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/widgets/r10_settings_navigation.dart';

const entries = [
  R10SettingsSearchEntry('updates', 'Check on start', 'Updates'),
  R10SettingsSearchEntry('sourceSpecific', 'GitHub personal access token', 'Sources'),
  R10SettingsSearchEntry('appearance', 'UI scale', 'Appearance'),
];

void main() {
  test('settings search combines case-insensitive words from public labels', () {
    expect(r10SearchSettings(entries, '  TOKEN sources '), [entries[1]]);
    expect(r10SearchSettings(entries, 'CHECK START'), [entries[0]]);
    expect(r10SearchSettings(entries, 'unknown'), isEmpty);
    expect(r10SearchSettings(entries, '  '), entries);
  });

  testWidgets('search returns owning section and reports no matches', (tester) async {
    String? chosen;
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: Builder(
      builder: (context) => TextButton(
        onPressed: () async {
          chosen = await showDialog<String>(context: context, builder: (_) =>
            const R10SettingsSearchDialog(entries: entries, searchLabel: 'Search settings',
              hint: 'Open a settings section', noMatch: 'No matching settings', closeLabel: 'Close'));
        }, child: const Text('Open search'),
      ),
    ))));
    await tester.tap(find.text('Open search'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'unmatched');
    await tester.pumpAndSettle();
    expect(find.text('No matching settings'), findsOneWidget);
    expect(find.text('UI scale'), findsNothing);
    await tester.enterText(find.byType(TextField), 'github token');
    await tester.pumpAndSettle();
    expect(find.text('GitHub personal access token'), findsOneWidget);
    await tester.tap(find.text('GitHub personal access token'));
    await tester.pumpAndSettle();
    expect(chosen, 'sourceSpecific');
    expect(tester.takeException(), isNull);
  });

  testWidgets('navigation target wraps large text and accepts keyboard activation', (tester) async {
    tester.view.physicalSize = const Size(320, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final node = FocusNode();
    addTearDown(node.dispose);
    var activated = 0;
    await tester.pumpWidget(MaterialApp(home: MediaQuery(
      data: const MediaQueryData(size: Size(320, 640), textScaler: TextScaler.linear(2)),
      child: Scaffold(body: Align(alignment: Alignment.topCenter,
        child: R10SettingsNavigationTile(
          title: 'Paramètres avancés de la configuration et de la vérification des sources',
          icon: Icons.tune, expanded: false, radius: 12, focusNode: node,
          onTap: () => activated++,
        ),
      )),
    )));
    expect(tester.takeException(), isNull);
    final tile = find.byType(R10SettingsNavigationTile);
    expect(tester.getSize(tile).height, greaterThan(56));
    node.requestFocus();
    await tester.pump();
    expect(node.hasFocus, isTrue);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(activated, 1);
    await tester.tap(tile);
    await tester.pumpAndSettle();
    expect(activated, 2);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });
}
