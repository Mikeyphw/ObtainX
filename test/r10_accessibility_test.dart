import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/components/app_dropdown_field.dart';
import 'package:obtainium/components/r10_accessibility.dart';
import 'package:obtainium/providers/settings_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  test('original source URL is retained and unsafe schemes are refused', () {
    const source = 'https://github.com/example/project?tab=readme';
    expect(r10SourceHomepage(source)?.toString(), source);
    for (final input in ['file:///data/app.apk', 'intent://app',
      'https://user:secret@example.com/', 'https://', 'obtainium://app/a']) {
      expect(r10SourceHomepage(input), isNull);
    }
  });
  test('swipe threshold arms once per direction and re-arms after retreat', () {
    final threshold = R10SwipeThreshold();
    bool update(double value) => threshold.update(value, left: true, right: true);
    expect(update(79), isFalse);
    expect(update(80), isTrue);
    expect(update(120), isFalse);
    expect(update(0), isFalse);
    expect(update(-80), isTrue);
    expect(update(-120), isFalse);
    threshold.reset();
    expect(threshold.update(-120, left: false, right: true), isFalse);
    expect(R10SwipeThreshold.direction(80, left: true, right: false), 0);
  });
  test('saved swipe indices stay stable and new action persists by name', () async {
    SharedPreferences.setMockInitialValues({'rightSwipeAction': 7});
    final settings = SettingsProvider()..prefs = await SharedPreferences.getInstance();
    addTearDown(settings.dispose);
    expect(SwipeAction.none.index, 7);
    expect(SwipeAction.openSource.index, 8);
    expect(settings.rightSwipeAction, SwipeAction.none);
    settings.rightSwipeAction = SwipeAction.openSource;
    expect(settings.rightSwipeAction, SwipeAction.openSource);
    expect(settings.prefs!.getString('rightSwipeActionName'), 'openSource');
  });
  testWidgets('navigation targets are focusable, scrollable and at least 48dp', (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(280, 640);
    addTearDown(tester.view.reset);
    int selected = -1;
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: Align(
      alignment: Alignment.topLeft,
      child: R10NavigationStrip(children: [
        for (int i = 0; i < 8; i++) R10NavigationTarget(
          key: ValueKey(i), label: 'Tab $i', selected: i == 0,
          onTap: () => selected = i,
          child: const Icon(Icons.apps),
        ),
      ]),
    ))));
    for (int i = 0; i < 8; i++) {
      final target = find.byKey(ValueKey(i));
      expect(tester.getSize(target).width, greaterThanOrEqualTo(48));
      expect(tester.getSize(target).height, greaterThanOrEqualTo(48));
    }
    for (int i = 0; i < 8; i++) {
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.pumpAndSettle();
    }
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(selected, 7);
    expect(tester.takeException(), isNull);
  });
  testWidgets('long action and dropdown labels grow at large text scale', (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(320, 800);
    addTearDown(tester.view.reset);
    const long = 'Une description plus longue de la source de l’application';
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: MediaQuery(
      data: const MediaQueryData(size: Size(320, 800), textScaler: TextScaler.linear(2)),
      child: Builder(builder: (context) => SingleChildScrollView(child: Column(children: [
        R10PrimaryActions(first: FilledButton(onPressed: () {}, child: const Text(long)),
          second: FilledButton(onPressed: () {}, child: const Text('第二の操作'))),
        appDropdownField<int>(context: context, value: 1, items: const [
          DropdownMenuItem(value: 1, child: Text(long)),
          DropdownMenuItem(value: 2, child: Text('Option 2')),
        ], onChanged: (_) {}),
      ]))),
    ))));
    final buttons = find.byType(FilledButton);
    expect(tester.getTopLeft(buttons.last).dy, greaterThan(tester.getBottomLeft(buttons.first).dy));
    await tester.tap(find.byType(DropdownButton<int>));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
}
