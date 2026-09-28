// Reference runner: feeds a CSV of IR samples (nA) through the app's ORIGINAL
// Dart classes (imported read-only from the app) and dumps per-sample outputs.
// The per-packet order of operations transcribes home_page.dart:151-199.
//
// usage: dart run ref.dart <in.csv> <out_prefix> <fs> <gate|none>
import 'dart:io';

import '../../smart_wearables_app_stress/lib/processing/ppg_processor.dart';
import '../../smart_wearables_app_stress/lib/processing/sqi.dart';
import '../../smart_wearables_app_stress/lib/processing/stress_detector.dart';

void main(List<String> args) {
  final input = File(args[0]).readAsLinesSync().where((l) => l.trim().isNotEmpty);
  final outPrefix = args[1];
  final fs = double.parse(args[2]);
  final gate = args[3] == 'none' ? null : double.parse(args[3]);
  final warmup = (3.0 * fs).round();
  final tickEvery = fs.round();

  final ppg = PpgProcessor(fs: fs);
  final sqi = SignalQualityIndex(fs: fs);

  final perSample = StringBuffer('filtered,peak,sqi_after\n');
  final ticks = StringBuffer('sample,sqi,rmssd,hr,n_intervals\n');
  var warm = 0;
  var i = 0;
  for (final line in input) {
    final x = double.parse(line);
    warm++;
    final good = gate == null ? true : sqi.value >= gate;
    ppg.process(x, goodQuality: good);
    if (warm > warmup) {
      sqi.push(filtered: ppg.lastFiltered, raw: x);
      sqi.updateIntervals(ppg.recentIntervalsMs);
    }
    perSample.writeln(
        '${ppg.lastFiltered},${ppg.lastPeak ? 1 : 0},${sqi.value}');
    if ((i + 1) % tickEvery == 0) {
      final hr = ppg.heartRateBpm;
      ticks.writeln('$i,${sqi.value},'
          '${StressDetector.computeRmssd(ppg.recentIntervalsMs)},'
          '${hr ?? ''},${ppg.recentIntervalsMs.length}');
    }
    i++;
  }
  File('${outPrefix}_samples.csv').writeAsStringSync(perSample.toString());
  File('${outPrefix}_ticks.csv').writeAsStringSync(ticks.toString());
  File('${outPrefix}_intervals.csv')
      .writeAsStringSync('${ppg.recentIntervalsMs.join('\n')}\n');
}
