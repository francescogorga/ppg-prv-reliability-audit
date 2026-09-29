# Judge a PPG quality gate by whether the HRV it keeps follows the truth: beat-to-beat consistency does; the app's SQI, motion and "trust low values" rules do not

*Francesco Gorga, MSc student, Politecnico di Milano. Draft, 29 Sep 2026. Code, results and full method: github.com/francescogorga/ppg-sqi-hrv-audit*

## Summary

- **Question.** Which ECG-free signal tells you when a PPG-derived HRV value (RMSSD, 1-minute windows) can be trusted? I tested 24 ECG-free features, alone and combined in ML models, from our smart-glasses app's signal-quality index (SQI) to beat-level statistics, on two public datasets with an ECG reference: finger in the lab (22 subjects) and forehead in daily life (16 participants, 10,945 windows). Every score is leave-one-subject-out.
- **Answer.** One simple, explainable feature, the correlation of each beat with the window's average beat, was the best or joint-best gate on both datasets. On the finger it matched a perfect gate's error, 5.5 ms keeping half the data, and the kept values tracked the ECG (Spearman 0.63 vs 0.08 without a gate). The app's SQI was worse on both counts (8.3 ms, 0.19).
- **Trap.** Judged only by the error of the windows it keeps, a rule that simply keeps the *lowest* HRV estimates looked as good as any model at the forehead. But the values it kept barely followed the truth (0.20 vs 0.50 for beat consistency). An accelerometer gate looked good on the finger only because it separated sitting from moving. At the forehead in daily life, no gate made the values usable.

## Method

- **Pipeline.** A Python port of the app, verified against the original Dart code on every intermediate output. Its beat detector was then fixed to time beats on the systolic peak, which alone cut the finger error from 85.5 to 18.1 ms. All results use this fixed version.
- **Data.** The ECG is ground truth only; the glasses carry PPG and skin temperature.
  - *Finger*: PhysioNet *Pulse Transit Time PPG* (MAX30101, the glasses' chip), sitting/walking/running, manually verified R peaks.
  - *Forehead*: *WildPPG* (NeurIPS 2024, CC BY-NC-SA 4.0), about 12 h of free-living recordings per person, MAX86141, Lead-I ECG with R peaks detected automatically. On the finger data, those R peaks change the reference RMSSD by a median 0.19 ms.
- **Candidates**, all computed without the ECG:
  - the app's SQI and its parts;
  - beat statistics: rejected and missed beats, RR jumps;
  - beat-to-template correlation, waveform shape and accelerometer;
  - logistic regression and gradient boosting on all 24 features.
- **Evaluation.** Each gate keeps its best-scored windows (50% on the finger, 25% at the forehead, where good windows are rarer). Two criteria:
  - the median |RMSSD error| of the kept windows;
  - whether the kept PPG RMSSD **follows** the ECG RMSSD (Spearman), with 95% CIs from a bootstrap over subjects.
- **Robustness checks.** Ranking within one activity and within one person's day; a gate with no model that keeps the lowest estimates; a model without any RR-derived feature.

## Result

![Error of kept windows vs whether kept values follow the ECG, for each gate](fig_tracking.png)

| Gate (keeps 50% finger / 25% forehead) | Finger: error | Finger: follows ECG | Forehead: error | Forehead: follows ECG |
|---|---|---|---|---|
| No gate (all windows) | 18.1 ms | 0.08 | 89.2 ms | 0.20 |
| **Beat-template correlation** | **5.5 ms** | **0.63** (0.15–0.90) | 33.7 ms | **0.50** (0.20–0.70) |
| Gradient boosting, all features | 5.5 ms | 0.70 | 30.9 ms | 0.44 |
| Keep lowest HRV estimates (no model) | 6.2 ms | 0.52 | 32.2 ms | 0.20 (0.03–0.38) |
| Accelerometer | 6.0 ms | 0.41 | 81.2 ms | 0.15 |
| App SQI | 8.3 ms | 0.19 (−0.18–0.50) | 58.9 ms | 0.36 |
| Oracle (keeps the truly best; needs ECG) | 5.5 ms | 0.82 | 29.4 ms | 0.70 |

1. **Beat consistency is the signal to use.** On the finger it did better than the SQI on both criteria; the difference in how well kept values follow the ECG has a CI of 0.18–0.71. It still ranked windows within a single activity (98% of the oracle's gain, against 28% for the accelerometer), so it detects bad beats, not just movement. The best ML model barely added anything, and a model without any RR-derived feature performed the same.
2. **Low error is not enough; check that kept values follow the truth.** At the forehead the errors were so large that the error mostly equals the estimate (in the median window, 79% of the estimate is error). Keeping low estimates therefore lowered the error by construction (96% of the oracle's gain) while the kept values stayed uninformative; beat consistency was better by 0.10–0.42 (CI). SHAP flagged this: the forehead model's most important feature was the RMSSD estimate itself.
3. **At the forehead in daily life, gating is not enough.** Even the best gate kept values about three times the truth (median PPG 65 ms vs ECG 22 ms). The limit is the signal (only 3% of windows had error ≤ 5 ms), not the gate.
4. **Uncertainty can be calibrated on average, not per person.** Split-conformal intervals whose width adapts to the predicted error covered 89% of true values against a 90% target, even when calibrated on the other site; fixed-width intervals fell to 68% from finger to forehead. But 3 of 22 finger subjects and 3 of 16 forehead participants stayed below 80%, and forehead intervals were very wide (median width 223 ms).

## What this could mean for a wearable-data platform

These are modest suggestions from a small study, not recommendations.

- **Evaluate quality flags against a reference on two criteria**: the error of what they keep, and whether the kept values still track the truth. A gate that favours low values, or that simply detects rest, passes the first test and fails the second.
- **Beat-level consistency is cheap, explainable and worked on both sensors tested.** Carried next to an HRV value (for example the mean beat-template correlation and the number of beats rejected), it would let a consumer apply its own gate.
- **Gating changes the population.** On the finger the kept windows had higher true HRV (25.8 vs 19.6 ms) because more of them were at rest (55% sitting vs 34% overall); gated HRV over-represents rest.
- **Per-value uncertainty is feasible but its guarantee is average, not per user.** Calibrating per user or per device would be needed before exposing intervals as guarantees.
- For context: in Terra's public OpenAPI schema (`tryterra/openapi`, checked 28 Sep 2026), HR, HRV and RR-interval samples carry no quality or confidence field.

## Limitations

- **No data from the glasses.** The hardware was returned after the course, so neither dataset is at the nose bridge.
- **Sample size.** 22 and 16 people; the CIs are wide.
- **Assumptions and design.** The forehead signal polarity was inferred and its R peaks are automatic. The 24 features are hand-designed. The fixed beat timing is an offline change, not a validated app update.

## Next step

Test whether beat consistency transfers to a third device and site (e.g. wrist or ear PPG with ECG). Then calibrate uncertainty per person, e.g. with a short per-user calibration period, and check whether per-person coverage reaches the target.
