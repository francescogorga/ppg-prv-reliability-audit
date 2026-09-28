# Our PPG quality gate did not reduce HRV error: in the lab it never fired, in daily life it discarded data without improving accuracy

*Francesco Gorga, MSc student, Politecnico di Milano. Draft, 28 Sep 2026. Code, results and full method: github.com/francescogorga/ppg-sqi-hrv-audit*

## Summary

- I ran our smart-glasses app's PPG pipeline (MAX30101, 100 Hz, processing on the phone), ported to Python and verified against the Dart code, on two public datasets with an ECG reference. One is finger/lab (22 subjects, 491 one-minute windows), the other forehead/daily life (2 participants, 1,343 windows).
- **Finger**: median RMSSD error **85.5 ms** (true median 22.3 ms). At the app's threshold (0.4) the signal-quality index (SQI) discarded nothing and removed nothing. **Forehead**: **136 ms** (true 14.8 ms). The SQI discarded 42% of usable windows, and the error moved to 130 ms, a change not distinguishable from zero.
- The error comes from beat detection, which the SQI does not measure. Timing beats on the systolic peak (offline only, not in the app) cut the finger error to **18.1 ms**.

## Method

- **Pipeline.** A line-by-line Python port of the app (0.5–3.5 Hz band-pass, adaptive-threshold peak detector, RR acceptance rules, RMSSD, SQI). It matches the original Dart classes on every intermediate output. The sampling rate is a parameter: a 100 Hz re-run of the 128 Hz forehead data gave 134.7 vs 136.1 ms.
- **SQI.** The SQI is **an unvalidated heuristic, hand-calibrated on our nose-bridge prototype**:
  `SQI = (0.4·amplitude + 0.6·periodicity) × artifact penalty`.
  - Amplitude is the AC/DC modulation, at full score from 0.02%.
  - Periodicity is `1 − 0.5·CV` of the RR intervals.
  - The penalty halves the score above 2% modulation and zeroes it above 3%.
- **Data.** Both datasets have an ECG, used only as ground truth (the glasses carry PPG and skin temperature, no ECG).
  - *Finger*: PhysioNet *Pulse Transit Time PPG Dataset* v1.1.0 (ODbL). Finger-clip MAX30101 raw IR with DC, manually verified R peaks, sitting/walking/running, resampled to 100 Hz.
  - *Forehead*: *WildPPG* (ETH Zurich, NeurIPS 2024; CC BY-NC-SA 4.0). 12 h per person of free-living recordings, forehead MAX86141 PPG, Lead-I ECG, 128 Hz. WildPPG stores PPG in blood-volume polarity, so I inverted the IR channel to the light polarity the app receives; this is inferred from the waveform and the authors' code. R peaks were detected automatically: validated at 128 Hz on the finger dataset's manual annotations, the reference RMSSD differs by a median 0.19 ms (90th percentile 0.66 ms).
- **Evaluation.** Non-overlapping 60 s windows; reference RMSSD from ECG R–R intervals; PPG RMSSD from the intervals the app accepts (at least 10 per window). A window is kept if its median 1 Hz SQI is ≥ τ, with τ swept from 0 to 1. Ablation: full SQI vs each term alone. Comparison: an accelerometer gate keeping the same share of windows. 95% CIs by bootstrap over subjects (finger) or 10-minute blocks (forehead). Every number comes from a saved script output, and both analyses re-run bit-identically.

## Result

| | Windows kept | Median abs. RMSSD error (95% CI) |
|---|---|---|
| **Finger, lab** — app pipeline, no gate | 97.8% | 85.5 ms (65.7–101.5); r = 0.11 |
| + SQI ≥ 0.4 (the app's threshold) | 97.8% | 85.5 ms; reduction CI [0.0, 0.0] ms |
| + SQI ≥ 0.97 (post hoc) | 40.3% | 45.8 ms (38.3–52.7); accelerometer gate, same coverage: 57.8 ms |
| Systolic-peak timing, no gate (offline only) | 97.4% | 18.1 ms (10.0–34.0); sitting: 4.2 ms |
| **Forehead, daily life** — app pipeline, no gate | 67.2% | 136.1 ms (128.5–144.0); r = 0.12 |
| + SQI ≥ 0.4, per window | 39.2% | 130.3 ms; reduction CI [−1.6, 10.5] ms |
| + SQI ≥ 0.4 inside the loop, as the app does | 40.4% | 125.2 ms; reduction CI [3.5, 15.6] ms |
| Systolic-peak timing, no gate (offline only) | 64.3% | 113.7 ms (103.7–121.3) |

Why the gate failed, in two opposite ways:

1. **In the lab it never fired.** The amplitude term was 1.0 in all 491 finger windows (median modulation 0.35–0.49% vs a 0.02% full-score point), and the median window SQI was 0.96–0.97 even while running.
2. **In daily life it fired without tracking the error.** At the forehead the modulation index was 2.5–4.5%, so the artifact penalty was active in 56–68% of seconds. It discarded windows, but the kept ones had a median error of 130 ms against 140 ms for the dropped ones, both about nine times the median true RMSSD. Inside the loop, as the app applies it, it removed 3.5–15.6 ms (95% CI) while keeping 40% of windows instead of 67%.
3. **The error sits in beat detection, which the SQI does not see.**
   - *Finger.* The detector times beats on the maxima of the raw light signal, the broad diastolic foot: timing IQR vs ECG 96.8 ms and 25.1% of beats missed, against 24.0 ms and 4.0% on the systolic peak.
   - *Forehead.* 49–61% of ECG beats had no PPG peak. The IR channel carried little cardiac signal: in the quietest windows its spectral heart rate matched the ECG within 5 bpm in 30% and 5% of cases, against 76% and 56% for green. Even green with systolic timing gave 63–69 ms.

![RMSSD error and share of windows kept as a function of the SQI threshold, finger (top) and forehead (bottom)](fig_sqi_tradeoff.png)

## What this could mean for a wearable-data platform

These are modest suggestions from a small study, not recommendations.

- **A quality score can fail in both directions.** It can stay high while the output is wrong (lab), or reject data without selecting better output (daily life). If a device's quality metadata is passed through, the useful information is what it was validated against, not the number alone.
- **Beat-level counts flagged the problem; the quality score did not.** "25% of beats missed" (finger) and "49–61% missed" (forehead) were the warning signs. Two cheap fields next to an HRV value would let a consumer apply its own gate: beats used, and beats rejected or missing in the window. The same holds for window length and method.
- For context: in Terra's public OpenAPI schema (`tryterra/openapi`, commit `9eccc73`, checked 28 Sep 2026), HR, HRV (RMSSD/SDNN) and RR-interval samples carry no quality or confidence field. HR samples carry an activity `context`. I have not checked what individual providers return in practice.

## Limitations

- **No data from the glasses.** The hardware was returned at the end of the course, and the app never stored the raw signal. Neither dataset uses the nose bridge.
- **Forehead sample.** Only 2 of 16 WildPPG participants were analysed, because I capped the download at ~3 GB (the full raw set is 19.6 GB). Its CIs capture variation within these two people, not between people. The polarity of the forehead signal was inferred.
- **Thresholds and variants.** The SQI thresholds were tuned for the nose. Thresholds of 0.96–0.98 were picked after seeing the data. The systolic-peak variant is an offline test, not a validated change.
- **Signal path.** Neither dataset reproduces BLE packet loss or a possible firmware FIFO read issue in the prototype.

## Next step

Run the forehead analysis on all 16 WildPPG participants; the scripts are ready, and only the 19.6 GB transfer is missing. Then test whether a beat-level quality measure, such as the share of missed beats or beat-to-template correlation, tracks RMSSD error better than this SQI. Both should be judged against the ECG reference, not by eye.
