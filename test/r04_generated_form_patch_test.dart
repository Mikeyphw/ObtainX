import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/components/generated_form_renderer.dart';
import 'package:obtainium/providers/settings_provider.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// The history picker patches a dropdown plus several text fields at once.
/// The visible channel and saved form values must agree.
void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  testWidgets('history assist updates Actions dropdown and persisted source identity',
      (tester) async {
    Map<String, dynamic> seen = <String, dynamic>{};
    await tester.pumpWidget(
      ChangeNotifierProvider<SettingsProvider>(
        create: (_) => SettingsProvider(),
        child: MaterialApp(
          theme: ThemeData(useMaterial3: true),
          home: Scaffold(
            body: GeneratedForm(
              items: <List<GeneratedFormItem>>[
                <GeneratedFormItem>[
                  GeneratedFormDropdown(
                    'r04GitHubSourceMode',
                    const <MapEntry<String, String>>[
                      MapEntry('releases', 'Releases'),
                      MapEntry('actions', 'Actions'),
                    ],
                    value: 'releases',
                    label: 'GitHub source channel',
                  ),
                ],
                <GeneratedFormItem>[
                  GeneratedFormTextField(
                    'r04RunId',
                    value: '',
                    required: false,
                    label: 'Run ID',
                    assistTooltip: 'Choose Actions history',
                    assistAction: (_, patch, values) async {
                      patch(<String, String>{
                        'r04GitHubSourceMode': 'actions',
                        'r04RunId': '42',
                      });
                    },
                  ),
                ],
              ],
              onValueChanges: (values, valid, building) {
                seen = Map<String, dynamic>.from(values);
              },
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(seen['r04GitHubSourceMode'], 'releases');
    await tester.tap(find.byTooltip('Choose Actions history'));
    await tester.pumpAndSettle();
    expect(seen['r04GitHubSourceMode'], 'actions');
    expect(seen['r04RunId'], '42');
    expect(find.text('Actions'), findsWidgets);
  });
}
