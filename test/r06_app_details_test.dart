import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/components/r06_version_tile.dart';

void main() {
  testWidgets('installed and available versions have distinct text labels', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: Column(
            children: <Widget>[
              R06VersionTile(label: 'Installed', value: 'v1.2.3'),
              R06VersionTile(label: 'Latest', value: 'v1.3.0'),
            ],
          ),
        ),
      ),
    );
    expect(find.text('Installed'), findsOneWidget);
    expect(find.text('Latest'), findsOneWidget);
    expect(find.text('v1.2.3'), findsOneWidget);
    expect(find.text('v1.3.0'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('unknown and long variant versions wrap without inventing truth', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(320, 720);
    addTearDown(tester.view.reset);
    const value = '20260723.00_RC11.964081323-very-long-custom-variant';
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: Center(
            child: SizedBox(
              width: 280,
              child: R06VersionTile(
                label: 'Installed',
                value: value,
                annotation: 'Version recorded by source; OS version unknown',
              ),
            ),
          ),
        ),
      ),
    );
    expect(find.text(value), findsOneWidget);
    expect(find.textContaining('OS version unknown'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('tags remain visible when skip and filtered evidence is present', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: R06VersionTile(
            label: 'Latest',
            value: '2.0',
            indicators: <Widget>[Text('Skipped'), Text('Filtered')],
          ),
        ),
      ),
    );
    expect(find.text('Skipped'), findsOneWidget);
    expect(find.text('Filtered'), findsOneWidget);
  });
}
