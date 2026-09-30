# Can a smart-glasses stress index trust PPG-derived HRV?

*Francesco Gorga · MSc student, Politecnico di Milano · 29 Sep 2026*

*Code, results and methods: [github.com/francescogorga/ppg-prv-reliability-audit](https://github.com/francescogorga/ppg-prv-reliability-audit)*

## Problem and origin

Our *Smart Wearables Design and Prototyping* team built glasses with a nose-bridge MAX30101 PPG
sensor. The app converts HR and RMSSD deviations from a personal baseline into a stress index.
After returning the hardware, I reconstructed the pipeline and audited it offline against public
PPG + ECG data: **22 finger subjects in the lab and 16 forehead participants in daily life**.

**Terminology:** the app calls this HRV; PPG pulse-to-pulse variability is strictly **PRV**.
“PPG-derived HRV/RMSSD” here denotes that PRV estimate; ECG-derived RMSSD is the HRV reference,
without assuming universal interchangeability (Schäfer & Vagedes, 2013; reference in the technical README).

**Main finding:** finger median absolute RMSSD error fell from **85.5 to 18.1 ms** after moving the
beat fiducial from the diastolic foot to the systolic peak (median ECG RMSSD **22.3 ms**).
Beat consistency then identified lower-error subsets. Free-living forehead estimates remained poor:
ungated v2 median error **89.2 ms**. Quality gating cannot repair a fundamentally unreliable beat series.

## Method

- **Reconstruction:** Python processing and stress classes checked against committed outputs from
  the original Dart classes on synthetic inputs; packet/tick ordering is transcribed from the app.
  v2 changes detector polarity offline; it was not deployed on the glasses.
- **Reference:** PTT-PPG has manually verified ECG R peaks and raw MAX30101 finger PPG. WildPPG
  has MAX86141 forehead PPG and Lead-I ECG, but no manual R annotations. Its automatic detector
  was benchmarked on **PTT-PPG**, with median sensitivity/PPV 1.0 and matched-beat timing error
  1.57 ms; cleaned-detection RMSSD differed from the manual reference by 0.19 ms in median.
  These are not annotated accuracy results on WildPPG.
- **Quality:** 24 ECG-free candidate features per non-overlapping minute; eight single-feature
  rankings and multifeature models, with leave-one-subject-out fitting and direction selection.
  Error, coverage and retained-value tracking against ECG are all reported.
- **Downstream:** replay the 1 Hz stress algorithm with session-specific baseline acquisition.
  The reference is **the same app using ECG HR/RMSSD**, not psychological stress truth.
  Display thresholds use other subjects; both baseline and current windows must pass.
  CIs bootstrap subjects. Seeded code, pinned direct dependencies and saved tables support reproduction;
  cross-platform bitwise identity is not claimed.

## Main results

![PPG RMSSD gates and agreement with the ECG-based application output](fig_brief.png)

<!-- BEGIN STRESS_TABLE -->
| Stress output vs ECG-based app output | Minutes shown | Cohen’s κ (95% CI) | False alarms |
|---|---|---|---|
| Finger — original app | 100% | 0.28 (0.21–0.36) | 31% |
| Finger — systolic v2 | 100% | 0.40 (0.29–0.52) | 25% |
| Finger — v2 + consistency, 50% target | 46% | 0.68 (0.52–0.79) | 13% |
| Forehead — original app | 91% | 0.15 (0.12–0.19) | 43% |
| Forehead — v2 + consistency, 25% target | 16% | 0.33 (0.16–0.42) | 36% |
<!-- END STRESS_TABLE -->

*Coverage: displayed / evaluable non-baseline ECG-reference minutes. Gate targets are 50% for
finger and 25% for forehead; baseline/session exclusions reduce realized coverage. False alarms:
non-calm outputs among displayed ECG-reference-calm minutes. Abstentions are excluded from that rate.*

1. **Timing before gating.** The original finger fiducial had R-to-detection lag IQR 96.8 ms and
   25.1% missed beats (medians across recordings). Even ECG-oracle selection left 48.4 ms error
   at 50% coverage. Fixing timing created a much more useful pool of windows.
2. **Consistency is a strong exploratory candidate.** The mean correlation of pulses with their
   window's median beat template retained finger windows with **5.5 ms error and Spearman 0.63**
   versus ECG, compared with **8.3 ms and 0.19** for app SQI, at 50% ranking coverage. Within-activity
   checks reduced the possibility that the result merely separates sitting from movement.
3. **Low error can mislead.** On forehead data, keeping the lowest PPG RMSSD estimates lowered
   error but tracked ECG weakly (**0.20 versus 0.50** for consistency, at 25% ranking coverage).
   SHAP highlighted reliance on the estimate itself, prompting this explicit negative control.
   Even consistency-selected values remained biased: median PPG about **65 ms versus ECG 22 ms**.
4. **The stress improvement costs coverage.** Finger κ increased **0.28 → 0.40 → 0.68**, with the
   gate showing 46% of evaluable minutes. Calm-reference prevalence was similar in retained and
   overall minutes (70% versus 72%); this does not rule out other easier-window selection.
   Forehead κ reached only **0.33 at 16% coverage**, with false alarms in 36% of displayed calm-reference minutes.
5. **Uncertainty remains limiting.** Split conformal targets **90% marginal coverage under
   exchangeability**, not each person's coverage. Repeated windows challenge that assumption.

<!-- BEGIN STRESS_UNCERTAINTY_BRIEF -->
Median score-interval widths were 49 points on finger and 100 (the full scale) on forehead. Confident bands covered 34%/24% of evaluated window/split pairs, almost all calm. Forehead agreement was 83%, near always-calm (83%); κ = 0.04.
<!-- END STRESS_UNCERTAINTY_BRIEF -->

   “Confident” refers to fixed score bands, not the app's hysteretic displayed levels.

## Relevance to wearable-data platforms

If upstream partners expose beat counts, rejected-beat metadata or waveform consistency, preserving
that information beside normalized biomarkers could support downstream reliability checks. Provider
summary biomarkers alone cannot recover this waveform-based quality signal. Error, tracking, coverage
and class balance all matter when assessing quality flags or abstention.

In Terra's public OpenAPI schema at commit `5944de59e7f2ccb941254c6907d52ebee08d58d8`, the inspected
HR/HRV/RR sample objects did not expose a quality/confidence field (saved check, 28 Sep 2026).
This describes the public schema, not Terra's internal quality handling or proprietary pipeline.

## Limitations and next step

**No recordings from the glasses:** neither site reproduces nose-bridge geometry, contact or motion;
sharing a chip does not establish equivalence. Small cohorts give broad CIs. WildPPG polarity is
inferred and ECG accuracy lacks direct manual annotation. Features and interpretation were developed
on both datasets: cross-site checks are robustness evidence, not independent external validation.
The stress reference validates measurement propagation through the app, not stress physiology.

Freeze systolic timing, template extraction and threshold calibration before testing a third dataset.
A stress-protocol dataset such as WESAD could additionally assess stress labels, with predeclared
handling of processed wrist BVP and a separate ECG reference. Any adaptation belongs to a new
exploratory study, not a retroactive claim of frozen validation.
