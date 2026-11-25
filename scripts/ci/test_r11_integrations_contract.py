"""R11 source boundary checks; Flutter and Android acceptance remain external."""
import json,re,unittest,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def read(name):return (ROOT/name).read_text()
class R11Contracts(unittest.TestCase):
 def test_native_package_only_route(self):
  root=ET.parse(ROOT/'android/app/src/main/AndroidManifest.xml').getroot();ns='{http://schemas.android.com/apk/res/android}'
  handlers=[a for a in root.findall('./application/activity') if any(x.get(ns+'name')=='android.intent.action.SHOW_APP_INFO' for x in a.findall('./intent-filter/action'))]
  self.assertEqual(len(handlers),1)
  self.assertIn('MainActivity',handlers[0].get(ns+'name'))
  native=read('android/app/src/main/kotlin/dev/imranr/obtainium/MainActivity.kt');self.assertIn('setIntent(normalizeR11AppInfoIntent(intent))',native);self.assertIn('val intent = normalizeR11AppInfoIntent(incomingIntent)',native)
  self.assertIn('Intent(Intent.ACTION_VIEW, Uri.Builder()',native)
 def test_exact_listing_resolution(self):
  home=read('lib/pages/home.dart');helper=read('lib/services/r11_external_requests.dart')
  for x in ('chooseExternalListing','candidates.length == 1','SimpleDialogOption','r11ExactLiveListing(provider.apps, selected)','AppPage(appId: live.listingKey, suppressAutoCheck: true)'):self.assertIn(x,home)
  self.assertIn('listings.containsListingKey(selected.listingKey)',helper)
  self.assertIn('listings.listingsForPackage(package)',helper)
 def test_automation_authorization_and_no_install(self):
  home=read('lib/pages/home.dart');part=home.split('Future<void> handleAutomation',1)[1].split('Future<void> interpretLink',1)[0]
  for x in ('settings.r11AutomationEnabled','approved != true','appsProvider.isForeground','getInstalledInfo(r11TaskerPackage','r11RunAutomation','r11SendTaskerResult'):self.assertIn(x,part)
  auto=read('lib/services/r11_automation.dart');self.assertIn('preserveListingIdentity: true',auto);self.assertIn('provider.fetchUpdate(app.listingKey, exactListing: app)',auto);self.assertIn('R05OperationJournal.instance.list()',auto);self.assertNotIn('downloadAndInstallLatestApps',auto);self.assertIn('package: r11TaskerPackage',auto)
  prefs=read('lib/providers/settings_provider.dart');self.assertIn("prefs?.get('r11AutomationEnabled') == true",prefs)
  imports=read('lib/providers/apps_provider_import_export.dart');self.assertIn("..remove('r11AutomationEnabled')",imports);self.assertIn("key == 'r11AutomationEnabled'",imports)
 def test_download_and_install_history_scope(self):
  source=read('lib/providers/apps_provider_install.dart');self.assertIn('newInfo.packageName != original.id',source);self.assertIn('preserveListingIdentity',source);self.assertIn('historyBinding: r11ValidPackage(app.id)',source);self.assertIn('channelFingerprint: r11ChannelFingerprint(app)',source)
  engine=read('lib/services/r03_download_engine.dart');self.assertIn('R03HistoryBinding.decode',engine);self.assertIn('_activeHistory[key] != historyBinding',engine)
  catalog=read('lib/services/r07_activity_catalog.dart');self.assertIn('historicalOwner?.listingKey',catalog);self.assertIn('historicalOwner?.packageId',catalog)
  ui=read('lib/widgets/r07_activity_center_page.dart');self.assertIn('widget.listingKey != x.listingKey',ui);self.assertIn('r11PublicHistory(records)',ui);self.assertIn('pruneTerminalBefore',ui)
  receipt=read('lib/services/r11_history.dart');self.assertIn("'historicalOnly': true",receipt)
  for secret in ('receipt.fileNames','receipt.sourceHost','receipt.sourceBranch','receipt.reason','record.download!.fileName','record.download!.origin'):self.assertNotIn(secret,receipt)
 def test_app_manager_exact_package(self):
  helper=read('lib/services/r11_external_requests.dart');self.assertIn("r11AppManagerPackage = 'io.github.muntashirakon.AppManager'",helper);self.assertIn('package: r11AppManagerPackage',helper);self.assertIn('canResolveActivity()',helper);self.assertIn('target.package == r11AppManagerPackage',read('lib/pages/settings.dart'));self.assertIn('PackageInstallerActivity',read('lib/pages/settings.dart'))
  self.assertIn('r11OpenAppManager(app.app.id)',read('lib/pages/app.dart'))
  self.assertIn('r11OpenAppManager(appId)',read('lib/providers/apps_provider_lifecycle.dart'))
 def test_schedule_uses_real_background_worker_and_transaction(self):
  policy=read('lib/services/r11_schedule.dart');self.assertIn('database.transaction',policy);self.assertIn('r11RateLimited(timestamp, previous, minutes)',policy)
  worker=read('lib/providers/apps_provider.dart').split('Future<void> bgUpdateCheck(',1)[1];self.assertLess(worker.index('r11InQuietHours'),worker.index('appsProvider.loadApps()'));self.assertLess(worker.index('r11ClaimAutomaticRun'),worker.index('_bgRunUpdateCheck('));self.assertIn('if (networkRestricted || chargingRestricted)',worker);self.assertIn('installStillAllowed',worker)
  self.assertIn('R11ScheduleSettings(settings: sp)',read('lib/pages/settings.dart'))
 def test_locale_parity_and_required_full_ci(self):
  from obtainx_ci_policy import classify
  self.assertTrue(classify(['lib/services/r11_automation.dart'])['full_flutter'])
  en=json.loads(read('assets/translations/en.json'));keys={k for k in en if k.startswith('r11')};self.assertGreaterEqual(len(keys),30)
  for lang in ['fr','ja','tr','pt','pt-BR']:
   d=json.loads(read(f'assets/translations/{lang}.json'));self.assertTrue(keys<=set(d))
   for k in keys:self.assertEqual(re.findall(r'\{[^{}]*\}',en[k]),re.findall(r'\{[^{}]*\}',d[k]))

 def test_strict_analyzer_guard_blocks(self):
  for path, guard, count in (
   ('lib/pages/home.dart', r'!settings\.r11AutomationEnabled \|\| !appsProvider\.isForeground\) \{ return; \}', 2),
   ('lib/providers/apps_provider_updates.dart', r'r11ExactLiveListing\(apps, exactListing\) == null\)\) return null;', 0),
   ('lib/providers/apps_provider_updates.dart', r'r11ExactLiveListing\(apps, exactListing\) == null\)\) \{ return null; \}', 2),
   ('lib/services/r05_operation_journal.dart', r'!item\.updatedUtc\.isBefore\(cutoff\.toUtc\(\)\)\) \{ continue; \}', 1),
   ('lib/services/r11_automation.dart', r"app\.apkUrls\.isEmpty\) \{ return \{'status': 'refused'\}; \}", 1),
   ('lib/services/r11_external_requests.dart', r"\(uri\.path\.isNotEmpty && uri\.path != '/'\)\) \{ return null; \}", 2),
   ('lib/services/r11_external_requests.dart', r'hasMatch\(request\)\) \{ return null; \}', 1),
  ):
   with self.subTest(path=path, guard=guard):
    self.assertEqual(len(re.findall(guard, ' '.join(read(path).split()))), count)
