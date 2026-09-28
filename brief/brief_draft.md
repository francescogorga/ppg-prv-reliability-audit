# Fix beat timing before gating: a PPG quality gate cannot rescue a bad beat detector, but once beats are timed correctly a calibrated gate halves the HRV error

*Francesco Gorga, MSc student, Politecnico di Milano. Draft, 28 Sep 2026. Code, results and full method: github.com/francescogorga/ppg-sqi-hrv-audit*

## Summary

- I audited the PPG pipeline of our smart-glasses prototype app (MAX30101, 100 Hz, processing on the phone). I ported it to Python, verified it against the original Dart code, and ran it on two public datasets with an ECG reference: finger in the lab (22 subjects, 491 one-minute windows) and forehead in daily life (2 participants, 1,343 windows).
- **As deployed**, the app's signal-quality index (SQI) did not help. On the finger the median RMSSD error was **85.5 ms** (true median 22.3 ms) and the SQI discarded nothing. At the forehead it discarded 42% of the data with no meaningful gain. Even a *perfect* gate would leave 48 ms at half the finger data, because only 1% of windows were good.
- **Timing beats on the systolic peak** (a one-line change, tested offline) cut the finger error to **18.1 ms**. On top of that, a gate calibrated on other subjects halved it again: **8.5 ms** with the SQI and **6.0 ms** with an accelerometer, keeping half the data. At the forehead in daily life nothing worked.

## Method

- **Pipeline.** A line-by-line Python port of the app (0.5–3.5 Hz band-pass, adaptive-threshold peak detector, RR acceptance rules, RMSSD, SQI), matching the original Dart classes on every intermediate output.
  - *v1* is the app as deployed: it times beats on maxima of the raw light signal.
  - *v2* is identical except that the detector runs on the negated signal, i.e. on the systolic peak. It is not in the app.
- **SQI.** An unvalidated heuristic hand-calibrated on our nose-bridge prototype: `(0.4·amplitude + 0.6·periodicity) × artifact penalty`. Amplitude is AC/DC modulation (full score from 0.02%); periodicity is `1 − 0.5·CV` of the RR intervals; the penalty acts above 2–3% modulation.
- **Data.** The ECG is ground truth only; the glasses carry PPG and skin temperature, no ECG.
  - *Finger*: PhysioNet *Pulse Transit Time PPG Dataset* v1.1.0 (ODbL). Finger-clip MAX30101, raw IR, manually verified R peaks, sitting/walking/running, 100 Hz.
  - *Forehead*: *WildPPG* (NeurIPS 2024; CC BY-NC-SA 4.0). 12 h per person of free-living recordings, forehead MAX86141 IR, Lead-I ECG, 128 Hz. IR inverted to the light polarity the app receives (inferred from the waveform and the authors' code). R peaks detected automatically; validated on the finger dataset, the reference RMSSD differs by a median 0.19 ms.
- **Evaluation.** 60 s windows; RMSSD from the RR intervals each pipeline accepts vs ECG R–R RMSSD.
  - *Oracle*: keeps the windows with the lowest true error. It needs the ECG, so it is unreachable; it is the ceiling for any gate.
  - *Honest calibration*: gate thresholds set on 11 finger subjects to keep a target share of data, then tested on the other 11, over 200 random splits. At the forehead, calibrate on one participant and test on the other.
  - 95% CIs by bootstrap over subjects (finger) or 10-minute blocks (forehead). Every number comes from a saved script output, and all analyses re-run bit-identically.

## Result

| | Windows kept | Median abs. RMSSD error |
|---|---|---|
| **Finger, lab** — v1 (app), no gate | 97.8% | 85.5 ms (95% CI 65.7–101.5) |
| v1 + SQI ≥ 0.4, the app's threshold | 97.8% | 85.5 ms; reduction CI [0.0, 0.0] |
| v1 + perfect gate (oracle) | 50% | 48.4 ms |
| v2, no gate | 97.4% | 18.1 ms (10.0–34.0) |
| v2 + SQI, threshold calibrated on other subjects | 50% (28–76) | **8.5 ms** (5.7–11.9)\* |
| v2 + accelerometer, calibrated on other subjects | 50% (40–61) | **6.0 ms** (4.3–11.9)\* |
| **Forehead, daily life** — v1 (app), no gate | 67.2% | 136.1 ms (128.5–144.0) |
| v1 + SQI ≥ 0.4 | 39.2% | 130.3 ms; reduction CI [−1.6, 10.5] |
| v2, no gate | 64.3% | 113.7 ms (103.7–121.3) |

\* median and 2.5–97.5th percentile over 200 subject splits; the oracle at the same coverage is 5.5 ms.

Three findings:

1. **The deployed threshold was wrong, but that was the smaller problem.** Used as a ranking, the SQI was almost as good as the oracle on the finger (50.6 vs 48.4 ms at half the data); a threshold of 0.4 simply never fired there. The amplitude term was 1.0 in every finger window. At the forehead, the artifact penalty fired in 56–68% of seconds without selecting better windows.
2. **No gate can rescue a bad beat detector.** With v1 only 1.2% of finger windows and 0% of forehead windows had an error ≤ 5 ms. v1 times beats on the broad diastolic foot: timing spread vs the ECG was 96.8 ms (IQR) and 25.1% of beats were missed, against 24.0 ms and 4.0% on the systolic peak.
3. **After fixing beat timing, gating pays off, but only when calibrated against a reference.** With v2, 23.6% of finger windows were good, and a gate calibrated on other people halved the error at half the data. A plain accelerometer did at least as well as the SQI and its threshold transferred more consistently between people. Thresholds did **not** transfer between the two forehead participants, nor from finger to forehead; there, even the oracle stayed above 96 ms at half the data.

![Median RMSSD error vs share of windows kept, for the oracle and three gates, with the app pipeline (left) and v2 (right)](fig_gates.png)

## What this could mean for a wearable-data platform

These are modest suggestions from a small study, not recommendations.

- **Beat timing matters more than the quality flag.** Two pipelines on the same sensor differed almost fivefold in RMSSD error (85.5 vs 18.1 ms); no gate closed that gap. Knowing *how* an HRV value was computed (fiducial point, window length, beats used) says more than a quality score.
- **Quality thresholds are site- and person-specific.** A threshold calibrated on finger data kept 1–14% of forehead data, and forehead thresholds did not transfer between two people. A score passed through without its calibration context can mislead.
- **Beat-level counts are cheap and informative.** Next to an HRV value, the number of beats used and the number missed or rejected would let a consumer apply its own gate.
- For context: in Terra's public OpenAPI schema (`tryterra/openapi`, commit `9eccc73`, checked 28 Sep 2026), HR, HRV and RR-interval samples carry no quality or confidence field; HR samples carry an activity `context`. I have not checked what individual providers return in practice.

## Limitations

- **No data from the glasses.** The hardware was returned after the course and the app never stored the raw signal; neither dataset uses the nose bridge.
- **Scope of the positive result.** The calibrated-gate result holds on lab finger data (22 subjects). At the forehead only 2 of 16 WildPPG participants were analysed (download capped at ~3 GB), and their polarity was inferred.
- **Offline variant.** v2 is an offline test, not a validated change to the app. The oracle is a ceiling, not an achievable method.
- **Signal path.** Neither dataset reproduces BLE packet loss or a possible firmware FIFO read issue in the prototype.

## Next step

Run all 16 WildPPG participants (the scripts are ready; a 19.6 GB transfer). Then test a beat detector designed for daily-life head PPG, e.g. on the green channel. Finally, check whether a beat-level quality measure, such as the share of missed beats, transfers across people better than the SQI, judged against the ECG reference.
