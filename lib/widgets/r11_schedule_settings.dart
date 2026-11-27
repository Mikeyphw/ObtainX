import 'package:easy_localization/easy_localization.dart';
import 'package:flutter/material.dart';
import 'package:obtainium/providers/settings_provider.dart';
import 'package:obtainium/services/r11_schedule.dart';

class R11ScheduleSettings extends StatefulWidget {
  const R11ScheduleSettings({super.key, required this.settings});
  final SettingsProvider settings;

  @override
  State<R11ScheduleSettings> createState() => _R11ScheduleSettingsState();
}

class _R11ScheduleSettingsState extends State<R11ScheduleSettings>
    with WidgetsBindingObserver {
  late Future<R11ScheduleObservation?> _observation;
  SettingsProvider get settings => widget.settings;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _observation = r11ReadScheduleObservation();
  }

  void _reload() => setState(() { _observation = r11ReadScheduleObservation(); });

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && mounted) { _reload(); }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  String _time(BuildContext context, int minutes) => TimeOfDay(
    hour: minutes ~/ 60, minute: minutes % 60).format(context);

  Future<void> _configure(BuildContext context) async {
    var start = settings.r11QuietStart;
    var end = settings.r11QuietEnd;
    var interval = settings.r11RateMinutes;
    final accepted = await showDialog<bool>(context: context, builder: (dialog) => StatefulBuilder(
      builder: (context, refresh) => AlertDialog(
        title: Text(tr('r11Schedule')),
        content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
          Text(tr('r11ScheduleHelp')),
          ListTile(title: Text(tr('r11QuietStart')), subtitle: Text(_time(context, start)),
            onTap: () async {
              final time = await showTimePicker(context: context,
                initialTime: TimeOfDay(hour: start ~/ 60, minute: start % 60));
              if (context.mounted && time != null) refresh(() { start = time.hour * 60 + time.minute; });
            }),
          ListTile(title: Text(tr('r11QuietEnd')), subtitle: Text(_time(context, end)),
            onTap: () async {
              final time = await showTimePicker(context: context,
                initialTime: TimeOfDay(hour: end ~/ 60, minute: end % 60));
              if (context.mounted && time != null) refresh(() { end = time.hour * 60 + time.minute; });
            }),
          Text(tr('r11MinimumInterval')),
          DropdownButton<int>(isExpanded: true, value: interval,
            items: [for (final minutes in ({0, 15, 30, 60, 120, 360, 720, 1440, interval}.toList()..sort()))
              DropdownMenuItem(value: minutes, child: Text(tr('r11Minutes', args: ['$minutes'])))],
            onChanged: (value) { if (value != null) refresh(() { interval = value; }); }),
        ])),
        actions: [TextButton(onPressed: () => Navigator.pop(dialog, false), child: Text(tr('cancel'))),
          FilledButton(onPressed: () => Navigator.pop(dialog, true), child: Text(tr('save')))],
      ),
    ));
    if (accepted == true && context.mounted) await settings.setR11Schedule(start, end, interval);
  }

  @override
  Widget build(BuildContext context) => Column(children: [ListTile(
    title: Text(tr('r11Schedule')),
    subtitle: Text('${_time(context, settings.r11QuietStart)} – ${_time(context, settings.r11QuietEnd)} · '
      '${tr('r11Minutes', args: ['${settings.r11RateMinutes}'])}\n${tr('r11ScheduleHelp')}'),
    onTap: () => _configure(context),
  ), FutureBuilder<R11ScheduleObservation?>(future: _observation,
    builder: (context, snapshot) {
      final observation = snapshot.data;
      final String message;
      if (snapshot.connectionState != ConnectionState.done) {
        message = tr('r11ScheduleReading');
      } else if (snapshot.hasError) {
        message = tr('r11ScheduleUnavailable');
      } else if (observation == null) {
        message = tr('r11ScheduleNoObservation');
      } else {
        message = '${tr('r11ScheduleReason_${observation.reason.name}')}\n'
          '${observation.observedUtc.toLocal()}';
      }
      return ListTile(title: Text(tr('r11ScheduleLastObservation')),
        subtitle: Text(message), trailing: IconButton(
          tooltip: tr('r07Refresh'), onPressed: _reload,
          icon: const Icon(Icons.refresh)));
    }),
  ]);
}
