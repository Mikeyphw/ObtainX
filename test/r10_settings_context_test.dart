import 'dart:convert';
import 'dart:io';
import 'package:easy_localization/easy_localization.dart';
import 'package:easy_localization/src/localization.dart';
import 'package:easy_localization/src/translations.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:obtainium/pages/additional_options_page.dart';
import 'package:obtainium/providers/apps_provider.dart';
import 'package:obtainium/providers/settings_provider.dart';
import 'package:obtainium/providers/source_provider.dart';
import 'package:obtainium/services/app_check_store.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/components/generated_form_model.dart';
import 'package:obtainium/components/r10_settings_context.dart';

class _Apps extends ChangeNotifier implements AppsProvider {
  _Apps(this.settingsProvider);
  @override
  final SettingsProvider settingsProvider;
  @override
  final AppListings apps = AppListings();
  @override
  Directory? cachedAppsDir;
  @override
  AppCheckStore? appCheckStore;
  @override
  DateTime? appDirectoryModifiedAt;
  @override
  DateTime? appCheckStoreModifiedAt;
  @override
  void markAppsChanged() {}
  @override
  void scheduleAutoExport() {}
  @override
  void notify() => notifyListeners();
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

const _app = App(id: 'org.example.app', url: 'https://github.com/example/app',
  author: 'Example', name: 'Example', installedVersion: '1.0.0',
  latestVersion: '1.1.0', preferredApkIndex: 0,
  additionalSettings: {'trackOnly': true, 'versionDetection': 'auto',
    'apkFilterRegEx': 'custom', 'futureSetting': 'retain'});

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Map<String, dynamic> translations;
  late Uint8List icon;
  setUpAll(() async {
    translations = (await const RootBundleAssetLoader().load(
      'assets/translations', const Locale('en')))!;
    icon = (await rootBundle.load('assets/graphics/logo_remember.png')).buffer.asUint8List();
    sqfliteFfiInit();
  });
  setUp(() {
    Localization.load(const Locale('en'), translations: Translations(translations));
    SharedPreferences.setMockInitialValues({'reduceVisualEffects': true,
      'matchAppPageToIconColors': false, 'folderCriteriaMigrationVersion': 1000});
  });
  testWidgets('real options page stages reset; decline and discard do not persist', (tester) async {
    final settings = SettingsProvider()..prefs = await SharedPreferences.getInstance();
    final apps = _Apps(settings);
    addTearDown(settings.dispose);
    addTearDown(apps.dispose);
    apps.apps[_app.id] = AppInMemory(_app, null, null, icon);
    await tester.pumpWidget(MultiProvider(providers: [
      ChangeNotifierProvider<SettingsProvider>.value(value: settings),
      ChangeNotifierProvider<AppsProvider>.value(value: apps),
    ], child: MaterialApp(home: Scaffold(body: Builder(builder: (context) =>
      TextButton(onPressed: () => Navigator.of(context).push<void>(
        MaterialPageRoute(builder: (_) => AdditionalOptionsPage(appId: _app.id))),
        child: const Text('open')))))));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    final reset = find.byKey(const ValueKey('r10-reset-options'));
    final save = find.byWidgetPredicate((widget) => widget is FloatingActionButton && widget.heroTag == 'additional_options_save');
    await tester.tap(reset);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(TextButton, tr('cancel')));
    await tester.pumpAndSettle();
    expect(tester.widget<FloatingActionButton>(save).onPressed, isNull);
    await tester.tap(reset);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, tr('r10ResetOptions')));
    await tester.pumpAndSettle();
    expect(tester.widget<FloatingActionButton>(save).onPressed, isNotNull);
    expect(apps.apps[_app.id]!.app.additionalSettings['apkFilterRegEx'], 'custom');
    await tester.tap(find.byWidgetPredicate((widget) => widget is FloatingActionButton && widget.heroTag == 'additional_options_cancel'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(TextButton, tr('discard')));
    await tester.pumpAndSettle();
    expect(find.text('open'), findsOneWidget);
    expect(apps.apps[_app.id]!.app.additionalSettings['apkFilterRegEx'], 'custom');
    expect(tester.takeException(), isNull);
  });
  test('reset save uses real persistence, keeps source and unknown settings', () async {
    final settings = SettingsProvider()..prefs = await SharedPreferences.getInstance();
    final dir = await Directory.systemTemp.createTemp('r10-reset-test-');
    final apps = _Apps(settings)..cachedAppsDir = dir
      ..appCheckStore = AppCheckStore('${dir.path}/checks.db', factory: databaseFactoryFfi);
    addTearDown(() async {
      await apps.appCheckStore!.close();
      apps.dispose();
      settings.dispose();
      await dir.delete(recursive: true);
    });
    apps.apps[_app.id] = AppInMemory(_app, null, null, icon);
    final source = SourceProvider().getSource(_app.url);
    final items = source.combinedAppSpecificSettingFormItems;
    final defaults = getDefaultValuesFromFormItems(items);
    final reset = r10ResetOptionDraft(items: items, defaults: defaults,
      current: {...defaults, ..._app.additionalSettings});
    await persistAdditionalOptionsForm(appsProvider: apps, settingsProvider: settings,
      appId: _app.id, formValues: getDefaultValuesFromFormItems(reset));
    final persisted = App.fromJson(jsonDecode(await File('${dir.path}/${_app.listingKey}.json').readAsString()) as Map<String, dynamic>);
    expect(persisted.url, _app.url);
    expect(persisted.additionalSettings['apkFilterRegEx'], defaults['apkFilterRegEx']);
    expect(persisted.additionalSettings['futureSetting'], 'retain');
    expect(persisted.additionalSettings['trackOnly'], true);
  });
  test('reset preserves protected and unavailable draft fields', () {
    final items = <List<GeneratedFormItem>>[
      [GeneratedFormTextField('apkFilterRegEx', required: false, value: 'old')],
      [GeneratedFormTextField('githubPAT', password: true, value: 'saved')],
      [GeneratedFormSwitch('includePrereleases', value: true)],
      [GeneratedFormSwitch('refreshBeforeDownload', value: true, disabled: true)],
      [GeneratedFormDropdown('versionDetection', const [MapEntry('auto', 'Auto'), MapEntry('pseudo', 'Pseudo')], value: 'pseudo', disabledOptKeys: ['auto'])],
      [GeneratedFormSwitch('trackOnly', value: true)],
      [GeneratedFormTextField('futureField', value: 'old')],
    ];
    final original = getDefaultValuesFromFormItems(items);
    final current = {...original, 'githubPAT': 'draft', 'futureField': 'draft', 'apkFilterRegEx': 'edited'};
    final result = r10ResetOptionDraft(items: items, defaults: {
      'apkFilterRegEx': '', 'githubPAT': '', 'includePrereleases': false,
      'refreshBeforeDownload': false, 'versionDetection': 'auto',
      'trackOnly': false, 'futureField': '',
    }, current: current);
    expect(getDefaultValuesFromFormItems(result), {
      ...current, 'apkFilterRegEx': '', 'includePrereleases': false,
    });
    expect(getDefaultValuesFromFormItems(items), original);
  });
  test('installer hints are selected by actual mode, unknown is explicit', () {
    expect(r10InstallerExplanationKey('system'), 'r10InstallerSystemHint');
    expect(r10InstallerExplanationKey('shizuku'), 'r10InstallerShizukuHint');
    expect(r10InstallerExplanationKey('dhizuku'), 'r10InstallerDhizukuHint');
    expect(r10InstallerExplanationKey('external'), 'r10InstallerExternalHint');
    expect(r10InstallerExplanationKey('other'), 'r10InstallerUnknownHint');
  });
}
