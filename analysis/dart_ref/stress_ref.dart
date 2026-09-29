// Runs the app's ORIGINAL StressDetector (imported read-only) on a CSV of 1 Hz inputs
// "hr,hrv,gate" (hr empty = null) and writes "score,level" per tick. Mirrors
// home_page._tickSecond: update only when gate == 1, then compute.
// usage: dart run stress_ref.dart <in.csv> <out.csv>
import 'dart:io';

import '../../smart_wearables_app_stress/lib/processing/stress_detector.dart';

void main(List<String> args) {
  final lines = File(args[0]).readAsLinesSync().where((l) => l.trim().isNotEmpty);
  final det = StressDetector(baselineSeconds: 60, updateRateHz: 1, slowWindowSeconds: 12);
  det.startBaselineAcquisition();
  final out = StringBuffer('score,level\n');
  for (final l in lines) {
    final p = l.split(',');
    final hr = p[0].isEmpty ? null : double.parse(p[0]);
    final hrv = double.parse(p[1]);
    if (p[2] == '1') {
      det.update(StressSample(hrBpm: hr, hrvRmssdMs: hrv));
    }
    final s = det.compute();
    out.writeln('${s.score},${s.level.index}');
  }
  File(args[1]).writeAsStringSync(out.toString());
}
