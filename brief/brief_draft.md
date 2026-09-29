# Can a smart-glasses stress index trust its heart-rate variability? A course prototype, re-tested on public PPG + ECG data

*Francesco Gorga, MSc student, Politecnico di Milano. Draft, 29 Sep 2026. Code, results and full method: github.com/francescogorga/ppg-sqi-hrv-audit*

## Summary

- **Where this comes from.** In the *Smart Wearables Design and Prototyping* course our team built smart glasses with a PPG sensor on the nose bridge (MAX30101). The phone app turns heart rate (HR) and heart-rate variability (RMSSD) into a stress index relative to a personal baseline, and uses a hand-made signal-quality index (SQI). The hardware was returned after the exam. I continued offline on two public datasets with an ECG reference, finger in the lab (22 subjects) and forehead in daily life (16 participants), to ask: **when can the app's HRV, and therefore its stress output, be trusted?**
- **The HRV was wrong, for a reason the SQI could not see.** The app timed beats on the diastolic foot of the pulse. RMSSD was off by 85.5 ms (true median 22.3 ms); timing beats on the systolic peak cut this to 18.1 ms. Among 24 ECG-free quality signals, the best was also the simplest: how similar each beat is to the window's average beat.
- **The errors reached the stress index.** Compared with the level the same app would show from ECG-derived HR/HRV, the app as deployed agreed with Cohen's kappa 0.28 on the finger, with false alarms in 31% of calm minutes. With fixed beat timing and a beat-consistency gate, kappa rose to 0.68 on the 46% of minutes shown. At the forehead in daily life it stayed at or below 0.33, and calibrated uncertainty could only confirm "calm".

## Method

- **Pipeline.** A line-by-line Python port of the app's signal processing and stress index. It is verified against the original Dart classes on every intermediate output and on the stress score and level, second by second.
- **Data.** The ECG is the reference only; the glasses carry PPG and skin temperature.
  - *Finger*: PhysioNet *Pulse Transit Time PPG* (same chip), sitting/walking/running, manually verified R peaks.
  - *Forehead*: *WildPPG* (NeurIPS 2024, CC BY-NC-SA 4.0), about 12 h of free-living recordings per person, MAX86141, Lead-I ECG. R peaks were detected automatically; validated on the finger data, they shift the reference RMSSD by a median 0.19 ms.
- **HRV quality.** 24 ECG-free features per one-minute window (the SQI and its parts, beat statistics, beat-to-template correlation, waveform, accelerometer), alone or in ML models, all leave-one-subject-out. A gate keeps its best windows; I report the error of what it keeps and whether the kept RMSSD still follows the ECG (Spearman).
- **Stress.** The app's 1 Hz loop is replayed with a 60 s baseline at the start of each session. The reference is the app's own stress index fed with ECG-derived HR/HRV, i.e. what the app would show with perfect beats. It is not an independent measure of stress. Display gates use thresholds chosen on the other subjects. Split-conformal intervals on the stress score give "confident" levels.
- **Statistics.** 95% CIs from a bootstrap over subjects. Every number comes from a saved script output; analyses re-run bit-identically.

## Result

![HRV gates (A) and agreement of the stress index with its ECG-based version (B)](fig_brief.png)

| Stress level shown vs ECG-based level | Minutes shown | Cohen's kappa (95% CI) | False alarms¹ |
|---|---|---|---|
| **Finger, lab** — app as deployed | 100% | 0.28 (0.21–0.36) | 31% |
| Fixed beat timing | 100% | 0.40 (0.29–0.52) | 25% |
| + beat-consistency gate | 46% | **0.68** (0.52–0.79) | 13% |
| **Forehead, daily life** — app as deployed | 91% | 0.15 (0.12–0.19) | 43% |
| Fixed beat timing + beat-consistency gate | 16% | 0.33 (0.16–0.42) | 36% |

¹ Share of minutes that are calm by the ECG-based index in which the app shows "aroused" or "stressed".

1. **Beat timing first.** The deployed detector timed beats on a broad, unstable point of the pulse: its timing spread against the ECG R peak was 96.8 ms (IQR), and 25% of beats were missed. No quality gate could compensate: even a gate that knew the true error kept 48 ms of RMSSD error at half the data.
2. **Beat consistency is the quality signal to use, and "low error" is not enough to judge one.**
   - With fixed timing, the beat-template correlation kept finger windows with 5.5 ms error whose RMSSD followed the ECG (Spearman 0.63), against 8.3 ms and 0.19 for the app's SQI. It kept working within a single activity, whereas the accelerometer mostly separated rest from movement.
   - At the forehead, a rule that keeps the lowest HRV estimates matched ML models on error, but its kept values barely followed the truth (0.20 vs 0.50 for beat consistency). SHAP showed the forehead model leaning on the estimate itself, which exposed this.
3. **What this means for the stress index.** On the finger, fixing beat timing and hiding inconsistent minutes more than doubled agreement (kappa 0.28 → 0.68) and cut false alarms from 31% to 13%, at the cost of showing a level on about half the minutes. The kept minutes had the same share of calm minutes as all minutes (70% vs 72%), so the gain is not from keeping the easy ones. At the forehead in daily life the index stayed unreliable: even the best gate reached kappa 0.33, with false alarms in about a third of calm minutes.
4. **Uncertainty is honest but not yet useful here.** Conformal intervals on the stress score held their 90% coverage, but they were wide (median 49 points on the finger, the full 0–100 scale at the forehead). A level was "confident" in 34% and 24% of minutes, and those levels were almost always "calm". At the forehead their agreement (83%) equalled always answering "calm", with kappa 0.03. Evaluating a confident output only by its agreement would have hidden this.

## What this could mean for a wearable-data platform

These are modest suggestions from a small study, not recommendations.

- **Scores derived from HRV inherit beat-level errors.** Stress and readiness scores built on HRV are only as good as beat timing. A platform typically receives the score, not the pulse, so the useful thing to ask device partners for is beat-level metadata: beats used, beats rejected, beat-to-template consistency.
- **Judge quality flags and confident outputs against a reference, on more than one number.** Check that kept values follow the truth, not only their error, and that the kept output is not simply the majority class ("calm").
- **Prefer abstaining to showing every minute.** On the finger, hiding low-consistency minutes raised kappa from 0.40 to 0.68, more than fixing beat timing did (0.28 to 0.40).
- For context: in Terra's public OpenAPI schema (`tryterra/openapi`, checked 28 Sep 2026), HR, HRV and RR-interval samples carry no quality or confidence field.

## Limitations

- **No data from the glasses.** The hardware was returned; neither dataset is at the nose bridge.
- **The stress reference is the app's own index on ECG,** not a validated stress measure. Sessions start with a 60 s baseline, which the finger dataset (single-activity recordings) exercises only mildly.
- **Sample and assumptions.** 22 and 16 people, so the CIs are wide. The forehead polarity was inferred and its R peaks are automatic. The fixed beat timing is an offline change.

## Next step

Test the same chain against real stress labels, e.g. a dataset with a stress protocol and chest ECG such as WESAD. Then calibrate uncertainty per person, so that a confident "stressed" becomes possible when it is true.
