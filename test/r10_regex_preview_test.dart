import 'package:easy_localization/easy_localization.dart';
import 'package:flutter/material.dart';
import 'package:obtainium/components/version_regex_assist_dialog.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:obtainium/components/r10_regex_preview.dart';

R10RegexPreviewRequest request(String pattern, {bool extract = false,
  bool apk = false, bool invert = false, String group = '',
  List<String> samples = const ['app-v1.2.apk', 'app-v2.3.zip']}) =>
  R10RegexPreviewRequest(pattern: pattern, group: group, extraction: extract,
    apkNames: apk, invert: invert, samples: samples);

void main() {
  testWidgets('actual assistant applies the edited pattern and cancel leaves draft unchanged', (tester) async {
    Map<String, String>? applied;
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: Builder(builder: (context) =>
      TextButton(onPressed: () => showRegexAssistDialog(context: context,
        kind: RegexAssistKind.apkFilter, initialRaw: 'app.apk',
        rawLineSuggestions: const ['app.apk', 'app.zip'],
        filterFieldKey: 'apkFilterRegEx', initialPattern: 'apk',
        patch: (patch) => applied = patch), child: const Text('open'))))));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    final pattern = find.byKey(const ValueKey('r10-regex-pattern'));
    await tester.ensureVisible(pattern);
    await tester.enterText(pattern, r'\.apk$');
    await tester.tap(find.text(tr('versionRegexAssistApply')));
    await tester.pumpAndSettle();
    expect(applied, {'apkFilterRegEx': r'\.apk$'});
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tester.tap(find.text(tr('cancel')));
    await tester.pumpAndSettle();
    expect(applied, {'apkFilterRegEx': r'\.apk$'});
  });
  test('APK preview shares filename-only filter and inversion', () {
    expect(evaluateR10RegexPreview(request(r'\.apk$', apk: true)).rows.map((r) => r.matches), [true, false]);
    expect(evaluateR10RegexPreview(request(r'\.apk$', apk: true, invert: true)).rows.map((r) => r.matches), [false, true]);
  });
  test('actual extraction groups and missing matches', () {
    final result = evaluateR10RegexPreview(request(r'v([0-9]+\.[0-9]+)\.apk', extract: true, group: r'$1'));
    expect(result.rows.first.extracted, '1.2');
    expect(result.rows.last.matches, false);
    expect(result.rows.last.extracted, isNull);
  });
  test('invalid, bounded and empty preview', () {
    expect(evaluateR10RegexPreview(request('[')).status, R10RegexPreviewStatus.invalid);
    expect(evaluateR10RegexPreview(request(List.filled(2049, 'a').join())).status, R10RegexPreviewStatus.limited);
    final limited = request('', samples: List.generate(80, (i) => 'v$i'));
    expect(limited.samples.length, 40);
    expect(evaluateR10RegexPreview(limited).rows.every((r) => r.matches), true);
  });
  test('worker returns actual result and cancellation refuses an outcome', () async {
    final result = await R10RegexPreviewJob().run(request(r'\.apk$', apk: true));
    expect(result.status, R10RegexPreviewStatus.ready);
    expect(result.rows.first.matches, true);
    final job = R10RegexPreviewJob();
    final pending = job.run(request('.*'));
    job.cancel();
    expect((await pending).status, R10RegexPreviewStatus.unavailable);
  });
}
