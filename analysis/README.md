# Analysis: how much PPG RMSSD error does the app's SQI remove, and how much data does it cost?

Two datasets: laboratory finger PPG (PTT-PPG, §§3–7) and free-living forehead PPG
(WildPPG, §8). Sections 8–9 retain the initial two-participant forehead experiment;
sections 10–11 use all 16 participants. Outputs are saved in `results/`.

**Terminology.** The application calls its PPG-derived quantity HRV. Strictly it is pulse rate
variability (PRV); here “PPG HRV/RMSSD” retains the app's terminology for that PRV estimate.
ECG-derived RMSSD is the HRV reference. PRV and HRV are not universally interchangeable
([Schäfer and Vagedes, 2013](https://pubmed.ncbi.nlm.nih.gov/22809539/)). Neither dataset
measures the nose bridge, and sharing the MAX30101 chip does not establish equivalent measurement conditions.

Prior development logs report repeated identical outputs in the recorded environment. This is
not a cross-platform bitwise guarantee: direct dependencies are pinned, transitive dependencies and
BLAS/platform details are not. See §12 for reproduction and the review's result provenance.

## 1. Contents of this directory

| File | Contents |
|---|---|
| `app_pipeline.py` | Line-by-line Python port of the processing classes plus packet ordering from `home_page.dart`. Sampling rate is a parameter throughout. |
| `dart_ref/ref.dart`, `dart_ref/gen_reference.py` | Execute the original, unmodified Dart processing classes on synthetic inputs; outputs are committed in `dart_ref/out/`. Regeneration requires the separate team app source. |
| `synthetic.py` | Seeded synthetic signals, not real recordings. |
| `tests/test_ecg_and_options.py` | Synthetic ECG R detection, RR cleaning with a missed beat, and invariance of peak detection to the `record_sqi` option. |
| `tests/test_port.py` | Dart equivalence, filter coefficients versus SciPy, cutoff response, RMSSD, Dart rounding, synthetic HR/RMSSD recovery, sensor-off SQI and gate startup. |
| `load_ptt.py`, `download_ptt_ppg.sh` | Dataset download with SHA-256 verification and loading. |
| `run_analysis.py`, `fiducial_check.py`, `make_figure.py` | Original SQI audit, timing relative to ECG R peaks, and SQI tradeoff figure. |
| `check_terra_schema.sh` | Inspect quality-related fields in a pinned public Terra OpenAPI schema snapshot. |
| `ecg_rpeaks.py`, `validate_rpeaks.py` | Automatic R detector used on WildPPG; benchmarked against PTT-PPG manual annotations after ECG resampling to 128 Hz. |
| `load_wildppg.py`, `download_wildppg.sh` | ETH polybox download, extraction of required channels, deletion of raw files. |
| `run_wildppg.py`, `wildppg_channel_check.py` | Initial two-participant forehead audit and IR/green channel check. |
| `oracle_check.py`, `calibrate_sqi.py` | Oracle ranking ceiling and thresholds calibrated on separate subjects. |
| `tests/test_v2.py` | Systolic v2 behavior and unchanged v1 behavior. |
| `features.py`, `build_features.py` | ECG-free minute features and a separate ECG error label. |
| `quality_models.py` | Single-feature rankings, logistic regression, gradient boosting and ECG oracle; LOSO evaluation. |
| `conformal.py`, `tests/test_conformal.py` | Split-conformal intervals targeting marginal coverage under exchangeability; finite-sample quantile tests. |
| `explain.py` | SHAP error-model explanations and logistic coefficients. |
| `robustness_quality.py`, `fig_tracking.py` | Within-activity/person checks, low-estimate negative control, reference tracking, and figure. |
| `tests/test_features.py` | Feature completeness, template sensitivity to motion, count-proxy boundaries and absent-signal behavior. |
| `stress.py`, `dart_ref/stress_ref.dart`, `tests/test_stress.py` | Stress algorithm and 1 Hz loop port verified against Dart fixtures. |
| `build_stress.py`, `stress_eval.py`, `fig_brief.py` | Stress replay, ECG-based application comparison, display gates, uncertainty and brief figure. |
| `reproduce.sh` | Full reproduction, including large downloads; see §12 first. |
| `results/` | Intentionally committed CSV, JSON, figures and logs. |

## 2. Port verification

`tests/test_port.py` compares Python with original Dart outputs on five synthetic signals:
100, 64 and 125 Hz; clean, motion-contaminated and sensor-off segments; gate 0.4 and gate disabled.
Filtered samples match within 1e-9, peaks exactly, per-sample SQI within 1e-12, and 1 Hz RMSSD,
interval-buffer length and final RR buffer agree. The original suite had 39 passing tests;
review-added regression tests are reported in `../docs/FINAL_REVIEW.md`.

The packet operation ordering (`home_page.dart:151–199`) is a transcription: the Flutter-dependent
page cannot run as a standalone Dart program. The processing classes themselves ran unmodified.
Committed fixtures make equivalence tests usable without redistributing the original app; they do
not let an external reviewer independently regenerate the Dart reference without that source.

## 3. Dataset choice

Access observations below were recorded on 2026-09-28, not a claim about future availability.

| Candidate | Recorded size / access / licence | PPG | Used? |
|---|---|---|---|
| WESAD | 2.25 GB ZIP (HTTP header), public link without registration | Empatica E4 wrist BVP, 64 Hz | No |
| PPG-DaLiA | 2.87 GB ZIP (UCI page), CC BY 4.0, no registration | Empatica E4 wrist BVP, 64 Hz | No; a partial download was stopped and deleted |
| TROIKA (IEEE SPC 2015) | Not verified | Wrist PPG, 125 Hz, treadmill running | No |
| **PhysioNet Pulse Transit Time PPG v1.1.0** | 2.9 GB overall; ~410 MB WFDB subset used here; ODbL 1.0, open access | Raw MAX30101 IR/red/green with DC, 500 Hz | **Yes** |

The app's SQI amplitude term divides by raw DC. Processed, near-zero-centred E4 BVP would not
support that term as written. This was a dataset-selection rationale based on E4 documentation,
not verified by downloading WESAD/DaLiA in this audit. PTT-PPG supplies raw DC-bearing data from
the same MAX30101 chip, synchronous ECG with automatically detected, manually verified R peaks,
and accelerometry. It includes 22 subjects, sitting, walking on the spot and running, with roughly
8.5 minutes per recording. Raw light intensity peaks near the pulse foot and falls during systole;
this polarity was checked against ECG-aligned waveforms. Finger placement still differs in vascular
bed, optical path, contact pressure and motion from the glasses' nose bridge.

Reference: Mehrgardt P., Khushi M., Poon S., Withana A. *Pulse Transit Time PPG Dataset*, v1.1.0.
PhysioNet, 2022. <https://doi.org/10.13026/jpan-6n92>.

### If using WESAD or PPG-DaLiA later

- PPG-DaLiA: <https://archive.ics.uci.edu/dataset/495/ppg+dalia>. The ZIP contains `data.zip`,
  with `SX/SX.pkl` files: `signal['wrist']['BVP']` at 64 Hz, chest ECG at 700 Hz and wrist ACC.
- WESAD: the recorded download command was
  `curl -L -o WESAD.zip https://uni-siegen.sciebo.de/s/HGdUkoNlW1Ub0Gx/download`.
  It uses a similar subject pickle structure. Check current access and the dataset licence before use.
- Do not apply the DC-dependent SQI amplitude term unchanged. Freeze a compatible feature subset
  or predeclare an adaptation before inspecting reference errors; see `../docs/FINAL_REVIEW.md`.

## 4. Method

- **Input:** sensor 1 IR (`pleth_1`), converted to nA (×16384/2¹⁸, relevant to the 10 nA presence
  threshold) and decimated from 500 to 100 Hz with a zero-phase FIR. No missing samples in the
  PPG channels used here.
- **Pipeline:** `app_pipeline.run_session`. Ungated mode always accepts the quality flag but
  still computes SQI each second. In-loop modes use SQI ≥ g at each beat, g = 0.2/0.3/0.4.
- **Windows:** 60 s, non-overlapping, beginning at t = 10 s after filter warmup. There are
  491 finger windows, all with valid ECG references.
- **ECG reference:** annotated R intervals in 300–2000 ms; successive differences only between
  adjacent valid intervals; at least 20 valid RR intervals.
- **PPG RMSSD:** the app's formula on accepted intervals whose closing packet falls in the
  window; at least 10 accepted intervals or the estimate is unavailable. Rejected intervals are
  removed as in the app, so adjacent accepted intervals need not be consecutive physiological beats.
- **Window SQI gate:** median of 1 Hz SQI values; retain SQI ≥ τ. Sweep τ from 0 to 1 in steps of
  0.05 below 0.8 and 0.01 thereafter.
- **Ablation:** full SQI, amplitude-only (modulation × penalty with its rejection checks), periodicity-only.
- **Coverage:** retained calculable windows / all 491 ECG-reference windows. Metrics: median
  absolute and percentage errors, Pearson/Spearman, Bland–Altman bias ±1.96 SD. Subject bootstrap:
  2,000 resamples, seed 20260928.
- **Comparator:** accelerometer magnitude SD at matched coverage.

## 5. Results

ECG RMSSD: median **22.3 ms**, IQR 16.4–30.6 ms (`summary.json`).

| Condition | Windows retained | Median absolute error (95% CI) | BA bias [limits] | Pearson r |
|---|---|---|---|---|
| App pipeline, no gate | 97.8% | **85.5 ms** (65.7–101.5) | +89.9 [−14.3; 194.0] | 0.11 |
| Window SQI ≥ 0.4 | 97.8% | 85.5 ms; reduction CI [0.0; 0.0] | Same | 0.11 |
| In-loop SQI ≥ 0.4, as in app | 97.8% | 85.5 ms; reduction CI [0.00; 0.05] | +89.8 | 0.11 |
| SQI ≥ 0.96, post hoc | 66.2% | 61.2 ms (50.5–72.6) | | |
| SQI ≥ 0.97, post hoc | 40.3% | 45.8 ms (38.3–52.7) | | |
| SQI ≥ 0.98, post hoc, 12 subjects | 10.6% | 23.7 ms (19.3–31.2) | | |
| Accelerometer at the three matched coverages | 66 / 40 / 11% | 73.9 / 57.8 / 60.3 ms | | |
| Hypothetical inverted-input systolic timing, ungated | 97.4% | **18.1 ms** (10.0–34.0) | +44.1 [−65.6; 153.8] | 0.06 |
| Sensor 2 (`pleth_4`), ungated | 95.7% | 110.6 ms | | −0.01 |

By activity, app pipeline ungated (inverted-input variant in parentheses): sitting 50.0 ms (4.2),
walking 101.8 ms (41.4), running 95.4 ms (33.2).

1. **The app threshold rejects no additional finger windows.** Median window SQI is 0.974 sitting,
   0.962 walking, 0.964 running. In-loop thresholds 0.2, 0.3 and 0.4 behave similarly.
2. **The amplitude score is 1 in all 491 windows.** Median modulation is 0.35–0.49%, versus full
   score at 0.02%. The >2% artefact penalty occurs in about 0.2–0.3% of seconds. Variation in SQI
   is therefore almost entirely periodicity.
3. **SQI ranks some error within its narrow 0.94–0.98 range.** Thresholds 0.96–0.98 were chosen
   after inspecting the sweep; these are descriptive operating points. Median ECG RMSSD in retained
   windows is 22.9/25.0/22.4 ms versus 21.5/20.2/22.3 ms discarded. This check argues against a
   simple lower-reference-RMSSD explanation; it does not rule out other selection effects.
4. **Fiducial timing is a major error source.** Raw-light maxima place detected beats near the
   broad diastolic foot. Medians of recording-level statistics (`fiducial_check.json`): R-to-pulse
   lag 193 ms, lag IQR **96.8 ms**, **25.1%** unmatched R beats and 2.2% with multiple detections.
   Inverting the input narrows lag IQR to **24.0 ms**, with 4.0% missed beats. The sitting result
   also improves markedly. These lags include processing delay and physiology; they are not a
   direct measurement of pulse transit time. The variant was tested offline, not deployed in the app.

Figure: `results/fig_sqi_tradeoff.png` (also PDF).

## 6. Terra's public OpenAPI schema

`check_terra_schema.sh` produces `results/terra_schema_check.txt`. The saved observation is at
commit **5944de59e7f2ccb941254c6907d52ebee08d58d8** of `tryterra/openapi`, first checked 2026-09-28 and rechecked during this review.
`HeartRateDataSample` exposes timestamp, bpm, timer_duration_seconds and context (Not Set / Active /
Not Active); RMSSD samples expose timestamp and hrv_rmssd; RR samples expose rr_interval_ms,
timestamp and hr_bpm. The inspected HR/HRV/RR objects have no quality/confidence field. The saved
keyword search found no quality/confidence/accuracy/reliability/artefact matches in heart-related
schema files; other matches were in Sleep, SleepLevel, GlucoseData and LabReportArtifactsResponse.

This is a **public schema observation**, not evidence about Terra's internal processing or what
individual device partners provide. A keyword search also cannot establish the semantics of every
field. If upstream partners expose beat-quality metadata, preserving it beside normalized biomarkers
could make downstream audits possible. A platform receiving only summary biomarkers cannot recreate
the waveform-based template feature used here.

The script defaults to the saved commit. Pass another commit explicitly for a new observation;
network or missing-file failures must not be interpreted as absence of quality fields.

## 7. Limitations of the initial finger audit

- No glasses recordings: 22 healthy adults, finger placement, laboratory activities, 491 minutes.
  The original app did not save raw PPG. The separate team project contains a proposed raw-export
  patch; that patch is not distributed in this audit repository.
- SQI is an unvalidated heuristic hand-calibrated on the nasal prototype. Its amplitude term
  saturates here. The original code comments report nasal modulation of 0.04–0.07%, also above
  the 0.02% full-score threshold, but saturation on the glasses was not measured in this audit.
- Pulse morphology and the appropriate fiducial may differ at the nose bridge.
- The 0.96–0.98 thresholds are post hoc.
- WFDB stores PPG at 12-bit resolution with gain/offset, then it is decimated to 100 Hz. BLE packet
  loss and the possible duplicate FIFO read described in `../docs/PIPELINE_ATTUALE.md` §1 are absent.
- The initial window RMSSD analysis is not the app's rolling 60-interval calculation. Section 11
  evaluates the rolling application output separately.
- ECG annotations are the reference, not infallible timing truth; the dataset authors note noisy
  ECG during walking.

## 8. Second analysis: forehead in daily life (WildPPG)

Added after the glasses were returned, to inspect a head site.

**Dataset.** Meier, Demirel and Holz, *WildPPG: A Real-World PPG Dataset of Long Continuous
Recordings*, NeurIPS 2024 Datasets and Benchmarks. Data: CC BY-NC-SA 4.0, non-commercial.
Forehead reflectance PPG (MAX86141, green 530/red 660/IR 950 nm), sternum Lead-I ECG and ACC,
all at 128 Hz, roughly 12 hours per person during hiking, transport, meals and rest.

- Full raw data: 16 files, 19.6 GB. This initial experiment used the two smallest participants,
  `an0` and `e61` (2.2 GB transfer). Required channels were extracted to NPZ and raw MAT files deleted.
  `download_wildppg.sh all` downloads all 16; `run_wildppg.py` defaults explicitly to the original two.
- The smaller Hugging Face derivative has preprocessed windows and HR but lacks ECG, so it cannot
  provide the RMSSD reference needed here.

**Polarity: inferred, not documented by the authors.** ECG-aligned IR maxima occur 336–367 ms
post-R and green maxima 273–320 ms post-R. Green rising/falling slope ratios are 1.74–1.81, versus
0.19–0.61 for PTT-PPG raw MAX30101 data. Official WildPPG code passes green PPG unchanged to
*ppg-beats*, which expects volume polarity. Hence IR is inverted for the app/light-polarity run;
uninverted IR corresponds to systolic timing. Evidence: `wildppg_polarity.json`.

**Units.** ADC full-scale fraction is multiplied by 4096 to make the 10 nA presence threshold
operational. This is an assumed nA-equivalent scale, not a recovered physical sensor range.
Other SQI terms and timing are scale-free.

**Reference and validation scope.** The Pan–Tompkins-style R detector has sub-sample refinement.
It was benchmarked on **PTT-PPG ECG resampled to 128 Hz**, not on manually annotated WildPPG ECG:
median sensitivity and PPV 1.0 (minima about 0.94), pooled median absolute matched-beat timing
error **1.57 ms**. Detected-and-cleaned RMSSD versus the manual PTT-PPG reference differs by
**0.19 ms** in median, 0.66 ms at the 90th percentile. Both-cleaned comparison: 0.18 ms median.
Cleaning rejects RR more than 20% from the surrounding 11-interval median. WildPPG windows with
>10% rejected RR are excluded, leaving 1,343 of 1,479 windows. WildPPG detector accuracy itself
is not directly annotated and remains a limitation; passing this screen does not prove reference accuracy.

**Results** (`wildppg_summary.json`). Median ECG RMSSD **14.8 ms**, IQR 10.4–20.8.
CIs use resampled 10-minute participant-specific blocks, describing these two recordings rather
than uncertainty across a population of participants. Coverage denominator is the 1,343 screened ECG windows.

| Condition | Retained | Median absolute error (95% CI) |
|---|---|---|
| App IR light polarity, ungated | 67.2% | **136.1 ms** (128.5–144.0); bias +141.7, r = 0.12 |
| Window SQI ≥ 0.4 | 39.2% | 130.3 ms; reduction CI [−1.6; 10.5] |
| Discarded by that SQI gate | 28.0% | 140.2 ms |
| In-loop SQI ≥ 0.4 | 40.4% | 125.2 ms; reduction CI [3.5; 15.6] |
| SQI ≥ 0.96 / 0.97, post hoc | 14.0% / 4.6% | 115.2 / 96.7 ms |
| Accelerometer at matched coverage | 14.0% / 4.6% | 137.4 / 114.2 ms |
| App run resampled to 100 Hz | 66.3% | 134.7 ms |
| Systolic IR timing, offline | 64.3% | 113.7 ms (103.7–121.3) |
| Green, light polarity | 89.4% | 109.0 ms |

- Here the SQI gate activates: median modulation 2.45%/4.46%; penalties in 56%/68% of seconds;
  median SQI 0.47/0.0. It rejects many windows but leaves large error: retained 130 ms versus
  discarded 140 ms, both far above the ECG RMSSD scale.
- IR carries weak usable pulse information in this check (`wildppg_channel_check.json`). In the
  quietest 20% of windows, spectral HR agrees with ECG within ±5 bpm in 30.2%/4.6% of IR windows,
  versus 75.5%/56.2% for green. Even green systolic timing has median error 69.0/62.8 ms overall
  and 62.5/54.1 ms in quiet windows.
- App-run missed beats: 49.3%/60.6%; R-to-detection lag IQR 607/435 ms.

**Specific limits:** two participants here, inferred polarity, automatic ECG reference with validation
only on another dataset, different chip and anatomical site from the glasses, non-commercial data licence.

## 9. Was the gate wrong, or can no gate help? Experiments 1 and 2

**v2 is offline only.** `PpgProcessor(systolic=True)` negates the filtered detector input; the
filter and SQI input stay unchanged. v1 equivalence tests remain. Ungated v2 error: finger 18.1 ms
(bias +43.8 ms, r = 0.06, reflecting some very large movement errors), forehead 113.7 ms in the
initial two-person sample. Rounded median errors match the earlier inverted-input experiment;
that earlier variant has slightly different bias/limits and is not numerically identical throughout.

**Experiment 1: oracle** (`oracle_check.json`, `fig_oracle.png`). Rank windows by ECG error and
retain the best. This is an unattainable error-ranking ceiling, not a deployable gate. At 50% of
ECG-reference windows:

| Dataset/pipeline | Oracle | App SQI | Periodicity | ACC | Ungated | Good ≤5 ms, among calculable windows |
|---|---|---|---|---|---|---|
| Finger v1 | 48.4 | 50.6 | 50.6 | 62.2 | 85.5 | 1.2% |
| Finger v2 | 5.5 | 8.3 | 8.3 | 6.0 | 18.1 | 23.6% |
| Forehead v1, two participants | 120.7 | 133.2 | 132.0 | 138.1 | 136.1 | 0% |
| Forehead v2, two participants | 96.5 | 109.0 | 109.6 | 109.9 | 113.7 | 0.1% |

Finger v1 SQI ranking is close to the oracle at this coverage; its 0.4 threshold is ineffective.
Even oracle selection leaves about 48 ms error in v1 at half coverage. On the finger, amplitude
saturation makes full SQI and periodicity rankings equal. Ranking cannot create accurate windows
where the beat series rarely supplies them.

**Experiment 2: thresholds calibrated on different people** (`sqi_calibration.json`).
Finger: 200 random 11-person calibration / 11-person test splits. Thresholds aim to retain
75/50/25% of calibration windows, then apply unchanged to test subjects. Forehead: each of the
initial two participants calibrates the other. Transfer: calibrate on finger, test on forehead.

Finger v2 test results: median [2.5th–97.5th percentile] across splits, not a confidence interval
for a single fitted model. Ungated median across splits: 18.0 ms.

| Target | Gate | Retained | Error (ms) | Oracle at realized coverage |
|---|---|---|---|---|
| 50% | SQI / periodicity | 50% [28–76] | 8.5 [5.7–11.9] | 5.5 |
| 50% | ACC | 50% [40–61] | 6.0 [4.3–11.9] | 5.5 |
| 25% | SQI | 25% [10–45] | 7.6 [4.9–11.4] | 3.1 |
| 25% | ACC | 24% [11–33] | 3.7 [2.3–5.4] | 2.7 |
| 75% | SQI | 74% [50–92] | 10.0 [7.7–16.5] | 9.1 |
| 75% | ACC | 75% [63–88] | 11.9 [6.2–28.3] | 9.3 |

After correcting timing, these gates lower error on held-out subjects at a coverage cost. ACC is
competitive in this laboratory mix; SQI's realized coverage varies widely across splits. v1 remains
poor: calibrated median error 50.7 ms at the 50% target, versus 84.4 ms ungated across splits.
Forehead thresholds transfer poorly between the two participants: calibrating on `e61` rejects
nothing on `an0`, while the reverse keeps less than intended; errors remain 80–146 ms. Finger SQI
thresholds 0.95–0.985 retain only 1–14% of forehead windows, with errors 39–75 ms.

The threshold was a problem, but fiducial timing was the larger finger failure. No tested gate
makes these free-living forehead estimates sufficiently accurate.

## 10. Which signals identify useful windows? Quality models, uncertainty and robustness

Starting from v2, `features.py` extracts **24 ECG-free candidate features**: SQI/components;
detected and accepted beat counts, rejection/missed-beat proxies and interval changes;
beat-template similarity; skewness/kurtosis/spectral features; and accelerometry. Eight single
features are compared explicitly, alongside multifeature models; not all 24 receive a standalone ranking.
ECG enters label construction outside `window_features`, never its inputs. “Good” means absolute
RMSSD error ≤5 ms, an audit threshold rather than a clinical tolerance.

The template is the pointwise **median** of demeaned −0.25 to +0.45 s pulse segments around detected
systolic peaks; each segment's normalized correlation is computed against that same window's template.
The mean correlation is the feature. A beat contributes to its own template: this is unsupervised
within-window self-inclusion, not ECG leakage, and can inflate similarity. At least five complete
segments are required; a repeated artefact can also look consistent.

**Count-feature correction during review.** The former `reject_frac = 1 − n_accepted/(n_peaks−1)`
could be negative: accepted intervals are assigned by their closing packet and can start before the
window. It is now a bounded count proxy, `clip(1 − n_accepted/max(n_peaks,1), 0, 1)`, or 1 with no
peaks. Peak positions precede decision packets by one sample, so it is not an exact decision-level
rejection rate. The saved counts permit this correction without reconstructing raw beats. All other
CSV fields were preserved; dependent models, uncertainty outputs and figures were rerun. The exact
rejected-decision fraction would require re-extracting per-beat decisions from raw recordings.

This stage uses **all 16 WildPPG participants**: 12,998 non-overlapping minutes, 10,945 passing the
ECG reference screen. v1 median error 106.1 ms, v2 89.2 ms; median ECG RMSSD 21.3 ms. Of calculable
v2 forehead windows, 3.2% meet the 5 ms threshold.

**Subject separation and evaluation.** For each held-out subject, `quality_models.fit_score`
fits the imputer/scaler/logistic or seeded GBM only on labelled windows from other subjects.
Single-feature direction is chosen from those other subjects' error correlations. Cross-site
models fit only the source dataset. Stress display thresholds use other subjects' features, and
conformal train/calibration/test subject sets are disjoint. The held-out subject's ECG error is not
used to fit its direction, model, threshold or conformal calibration. ECG screening defines which
windows can be evaluated; it is not itself an available deployment-time quality signal.

This separation does **not** remove study-level feature selection bias: candidate design and the
choice of template consistency for the narrative used these two datasets. Cross-site checks are
robustness analyses, not independent external confirmation. Freeze the method before a third dataset.

The quality curves sort held-out scores together and retain the top k calculable windows. They
measure retrospective ranking at a chosen coverage, not the behavior of a fixed deployable threshold.
Coverage denominator is all screened ECG-reference windows (491 finger / 10,945 forehead), so
curves stop when calculable windows run out. The nonstandard AURC here is the arithmetic mean of
**median absolute error** at available 5-percentage-point coverages from 10% upward. It is not a
standard classification-risk integral. Gap closed is `(ungated AURC − method AURC)/(ungated − oracle)`.
AUROC and average precision assess the ≤5 ms label. Subject-bootstrap CIs resample saved out-of-fold
scores, without refitting models or repeating feature selection; they do not capture all selection uncertainty.

<!-- BEGIN QUALITY_TABLE -->
| Method | Finger AURC (gap closed) | Error at 50% | AUROC | Forehead AURC (gap closed) | Error at 25% | AUROC |
|---|---|---|---|---|---|---|
| Ungated | 18.1 | 18.1 | — | 89.2 | 89.2 | — |
| Oracle (ECG) | 6.9 (100%) | 5.5 | — | 48.8 (100%) | 29.4 | — |
| Gradient boosting | 7.1 (98%) | 5.5 | 0.96 | 49.6 (98%) | 30.9 | 0.98 |
| Logistic regression | 7.2 (97%) | 5.7 | 0.94 | 51.8 (93%) | 32.4 | 0.97 |
| Beat-template correlation | 7.0 (99%) | 5.5 | 0.97 | 53.3 (89%) | 33.7 | 0.96 |
| Rejection count proxy | 7.6 (93%) | 5.6 | 0.84 | 53.3 (89%) | 34.8 | 0.95 |
| Accelerometer | 8.1 (89%) | 6.0 | 0.88 | 82.8 (16%) | 81.2 | 0.62 |
| App SQI | 9.4 (78%) | 8.3 | 0.68 | 71.0 (45%) | 58.9 | 0.39 |
<!-- END QUALITY_TABLE -->

Template correlation is a strong interpretable candidate in this audit, particularly on finger data.
Model rankings and their corrected values are shown above; a small numerical lead does not establish
universal superiority. On the forehead, even the oracle at 25% coverage leaves about 29 ms error.

Selection changes the population represented: at 50% finger coverage, template-selected windows
have median ECG RMSSD 25.8 ms versus 19.6 ms discarded (oracle: 26.5 versus 19.1). Rest is represented
more strongly. Forehead selection shifts this less (20.7 versus 23.4 ms at 50% in the quality-model check).
Cross-site GBM results are reported in `quality_models.json`; transferring a ranking differs from
transferring an absolute threshold and does not imply that either anatomical site validates the glasses.

**Uncertainty: split conformal** (`conformal.json`, `fig_conformal.png`). The interval is
PPG RMSSD ± q·σ(x); σ(x) is a GBM absolute-error prediction (fit on log(1+error), then transformed
back) plus 1 ms. Compare adaptive and constant-width intervals. For each held-out subject, split
other subjects roughly 2/3 training and 1/3 calibration, repeating 20 times. The finite-sample
quantile includes the infinite (n+1)th score when calibration is too small.

<!-- BEGIN CONFORMAL_TABLE -->
| RMSSD interval metric | Finger | Forehead |
|---|---|---|
| Pooled coverage, adaptive / constant | 89.4% / 88.0% | 89.3% / 89.3% |
| Median width, adaptive / constant | 58 / 263 ms | 223 / 341 ms |
| Subjects below 80%, adaptive / constant | 3 / 6 (adaptive minimum 44%) | 3 / 2 (adaptive minimum 63%) |
| Width ≤20 ms: retained labelled windows; error; coverage | 24.8%; 3.3 ms; 83% | 2.6%; 3.4 ms; 88% |
| Calibrate on other site: adaptive / constant coverage | 89.2% / 96.2% | 89.5% / 68.1% |
<!-- END CONFORMAL_TABLE -->

The procedure **targets 90% marginal coverage under exchangeability**. Similar pooled empirical
coverage does not verify that assumption: within-person temporal dependence, unequal recording
lengths and new-subject/domain shifts matter. There is no per-person, post-selection or clinical
reliability guarantee. The width-based selective denominator is calculable labelled windows,
with each test window repeated across calibration splits. Narrow intervals can under-cover;
forehead intervals are often much wider than the underlying ECG RMSSD.

**SHAP** (`explain.json`, `fig_shap.png`). The explanation model is fitted on all labelled data;
its SHAP values are descriptive, not held-out performance evidence. Template similarity is important
on finger data; the estimate itself and interval changes are important on forehead data. Removing
`ppg_rmssd` alone leaves correlated interval-derived information, so SHAP importance is not necessity.
The logistic coefficients provide a second descriptive view. Updated magnitudes are in the saved JSON.

**Robustness checks** (`robustness_quality.json`, `fig_tracking.png`) use held-out scores.
Within each finger activity, template similarity retains useful error ranking whereas ACC's pooled
success largely reflects separation of rest from movement. Within-person forehead checks test
whether rankings distinguish windows within a day, not just participants with different signal quality.
Threshold sensitivity includes ≤5/10/20 ms labels, and average precision supplements AUROC for rare good windows.

**Circularity / low-estimate control.** The target contains the estimate: `|RMSSD_PPG − RMSSD_ECG|`.
When ECG RMSSD is relatively low, simply preferring low PPG estimates can reduce absolute error
without preserving physiological tracking. `ppg_rmssd_low` tests this explicitly. SHAP's reliance
on the estimate motivated the check; SHAP does not prove circularity. `gbm_signal_only` removes
RMSSD and selected interval-variability features, but still includes HR/count-related features;
its legacy name must not be read as “independent of all beat information.”

<!-- BEGIN TRACKING_TABLE -->
| Retained-value tracking (Spearman; 95% CI) | Finger, 50% | Forehead, 25% |
|---|---|---|
| Ungated | 0.08 (-0.17…0.34) | 0.20 (0.04…0.35) |
| Beat-template correlation | 0.63 (0.15…0.90) | 0.50 (0.20…0.70) |
| Rejection count proxy | 0.45 (0.11…0.76) | 0.52 (0.26…0.70) |
| Gradient boosting | 0.70 (0.28…0.91) | 0.45 (0.19…0.65) |
| GBM excluding selected RR-variability features | 0.59 (0.21…0.91) | 0.43 (0.14…0.65) |
| Keep lowest estimates | 0.52 (0.07…0.70) | 0.20 (0.03…0.38) |
| Accelerometer | 0.41 (0.07…0.65) | 0.15 (-0.02…0.38) |
| App SQI | 0.19 (-0.18…0.50) | 0.36 (0.16…0.50) |
| Oracle | 0.82 (0.38…0.93) | 0.70 (0.42…0.83) |
<!-- END TRACKING_TABLE -->

Tracking is Spearman correlation of retained PPG and ECG RMSSD, with subject-bootstrap CIs,
at 50% finger and 25% forehead coverage. Low error alone is insufficient; tracking is an additional
sanity check, not proof of unbiased measurement (correlation can coexist with large bias and be affected
by range restriction). The forehead low-estimate rule tracks weakly (~0.20) compared with template
consistency (~0.50). Even the latter retains median PPG RMSSD about 65 ms versus ECG about 22 ms.
The paired bootstrap difference in tracking between template and low-estimate gates is positive on
forehead data; its finger CI includes zero. See JSON for all paired differences and precision–recall results.

## 11. Does measurement error reach the application's stress index?

The app converts HR and RMSSD deviations from a personal baseline into a 0–100 score, then calm /
aroused / stressed levels. This replay isolates measurement effects on that algorithm; it does not
validate psychological stress or treat ECG as a stress ground truth.

- **Verified port:** `stress.py` preserves `StressDetector` and 1 Hz loop ordering (`update` only
  when previous displayed SQI ≥0.4, then `compute`). Three synthetic sequences match Dart
  score and level second by second.
- **Four streams in `build_stress.py`:** ECG-based application output; v1 with in-loop SQI gate;
  systolic v2; and v2 with SQI-gated stress updates. ECG HR is the median of up to 10 clean
  intervals within the last 60 RR; RMSSD uses adjacent valid pairs among the last 60 RR.
  ECG cleaning uses a centred 11-interval median, so this reference is offline, not causal.
- **Sessions:** start at t=10 s, one per finger recording, 30-minute sessions on forehead.
  Baseline starts at session start. The algorithm collects 60 accepted update ticks; with SQI
  gating this can take longer than 60 wall-clock seconds. The first 60 s window is excluded from
  evaluation; levels remain unknown until baseline acquisition succeeds.
- **Dependence:** feature windows do not overlap, but 1 Hz stress outputs reuse rolling interval
  buffers, accepted-value means, EMA/hysteresis and a shared session baseline. Stored stress rows
  sample the output at minute ends; they are not independent biological observations. A display
  gate uses completed-window quality retrospectively. Quality metrics include accepted intervals
  carried from before a window and SQI based on a rolling buffer.
- **Evaluation:** non-baseline rows passing the ECG reference screen with known ECG-based level:
  **424 finger / 10,208 forehead minutes**. Each model uses its own measured baseline. This is
  a matched algorithm comparison, not a common error-free baseline supplied to PPG.
- **Display gates:** choose other-subject feature quantiles for 50%/25% targets. Require both the
  current window and session baseline window to pass. This can reject a whole session. The target
  is calibrated on finite feature values among evaluable non-baseline minutes, before this additional
  baseline restriction; realized display coverage is shown below.

<!-- BEGIN STRESS_FULL_TABLE -->
| Stress output vs ECG-based app output | Minutes shown | Cohen’s κ (95% CI) | False alarms | Misses |
|---|---|---|---|---|
| Finger — original app | 100% | 0.28 (0.21–0.36) | 31% | 26% |
| Finger — systolic v2 | 100% | 0.40 (0.29–0.52) | 25% | 22% |
| Finger — v2 + consistency, 50% target | 46% | 0.68 (0.52–0.79) | 13% | 8% |
| Finger — v2 + consistency, 25% target | 19% | 0.79 (0.55–1.00) | 13% | 0% |
| Finger — v2 + low estimate, 25% target | 21% | 0.61 (0.34–0.89) | 9% | 23% |
| Forehead — original app | 91% | 0.15 (0.12–0.19) | 43% | 35% |
| Forehead — systolic v2 | 100% | 0.13 (0.08–0.19) | 51% | 31% |
| Forehead — v2 + consistency, 25% target | 16% | 0.33 (0.16–0.42) | 36% | 17% |
<!-- END STRESS_FULL_TABLE -->

Coverage = known displayed levels / all evaluable minutes. False alarms = non-calm output among
**displayed** minutes whose ECG-based app level is calm. Misses = calm output among displayed
minutes whose ECG-based level is non-calm; abstentions are not counted as misses. Thus a lower
false-alarm percentage is conditional on a selected set, not a reduction demonstrated on identical minutes.

At the finger 50% target, calm-reference share is about 70% retained versus 72% overall. This argues
against a simple majority-class explanation but **does not exclude selection of easier minutes**.
The low-estimate 25% gate retains only one stressed-reference minute among 89 displayed minutes.
Overlapping CIs alone cannot establish equality or the absence of a paired difference between gates.

**Stress uncertainty:** train and calibrate on other subjects, repeating 10 splits per held-out subject.
Intervals target ECG-based **scores**. “Confident” means the interval is wholly inside a fixed
score band (<35, 35≤score<65, ≥65). These bands differ from the app's stateful hysteretic levels
(35/25 and 65/55 entry/exit thresholds), so confident-band kappa is not directly comparable with
level kappa in the table. Pooling repeats does not create more independent test participants.

<!-- BEGIN STRESS_CONFORMAL -->
Empirical score-interval coverage: finger 90.4%, forehead 90.0%; median width 49 and 100 points. Confident-band outputs occur in 34% and 24% of evaluated window/split pairs; 98.5% and 99.6% of those outputs are calm. Forehead confident-band agreement is 83.0%, versus 82.7% for always calm on the same subset; κ = 0.04, with 98% of non-calm reference bands missed.
<!-- END STRESS_CONFORMAL -->

The overwhelmingly calm outputs and near-majority-baseline forehead agreement make high raw
agreement misleading. Quality estimation identifies relatively safer windows but cannot compensate
for a fundamentally unreliable beat series.

## 12. Reproduction

Recommended Python: **3.14**; this review used CPython **3.14.3 on macOS arm64**. Direct pins
in `requirements.txt` were installed and checked locally; transitive packages are not fully locked.
Seed: 20260928 for simulations, subject splits, bootstraps and GBM. Logistic fitting uses its
non-stochastic default solver. Numerical libraries and platforms may still alter floating-point results.

Lightweight checks, from repository root:

```bash
python3 -m venv analysis/.venv
analysis/.venv/bin/python -m pip install -r analysis/requirements.txt
analysis/.venv/bin/python -m pip check
analysis/.venv/bin/python -m pytest analysis/tests/
analysis/.venv/bin/python analysis/check_doc_numbers.py
analysis/.venv/bin/python brief/build_pdf.py
```

The PDF script requires Chrome/Chromium; `CHROME_BIN` can specify its executable. Dart is not
needed to use committed equivalence fixtures. Regeneration needs both Dart and the separate
original app sources. CI installs the same pins and runs unit tests only: no datasets or full reproduction.

Full reproduction, only when prepared for the download and runtime:

```bash
cd analysis
./reproduce.sh
```

This downloads ~410 MB PTT-PPG (official SHA-256 manifest checked) and ~19.6 GB WildPPG transfer,
one raw participant at a time, keeping extracted NPZs. Budget several GB of free disk for the venv,
accumulating extracted data and the largest temporary MAT file; there is no verified universal
2.5 GB total-disk bound. The historical runtime estimate is about 3 hours, network/machine dependent.
WildPPG downloads lack an upstream checksum verification step. Do not infer identical source bytes
from a successful extraction alone. The initial `run_wildppg.py an0 e61` output stays explicitly scoped
to two people; feature/stress extraction uses all downloaded participants.

`quality_models.py`, `conformal.py`, `explain.py`, `robustness_quality.py`, `stress_eval.py` and
figure scripts run from saved CSVs without raw data. Following the count-feature correction these
were regenerated from cached counts. Raw-data-dependent timing, reference and stress-replay tables
were not changed by that correction. The review report records executed commands, limitations and
current hashes in `results/review_checksums.txt`. Old hashes below document earlier snapshots only.

### Historical hash records (not current-output assertions)

Finger before v2, reported identical on two runs:

```
f9585a79e486cd682141654a385de11b8aea14648cd63fd108cd33fa6c23719c  results/summary.json
64a32f45c3a7d369860b9ba5c393c8ddbffe4448c6a02dc78a19bb017c71b93e  results/sweep.csv
b02f17d2a137315de1a867f1d5551aa9d0e085c917525ad9b2f3bd9cb60a72b1  results/fiducial_check.json
```

Forehead before v2, reported identical on two runs:

```
c4587a81cc8eb61f0e466e8098253ed7f34eac42af6c6ac6e91f0eee8deccdda  results/wildppg_summary.json
89ec51b9b95b1fd6b6f865e78b8dc3a28d12188233d2210546d3e4e8d57d6eb6  results/wildppg_sweep.csv
f69e947435323ce9f2a771dac8357c567f452a66a79ea5fac09d681208773bc2  results/wildppg_windows.csv
```

After v2 and experiments 1–2 (v1 values checked key by key at that stage):

```
3e08eeb89edcef759ed3f4787a7f9dd280a2fe75bd2e8acd2da08e3264fcac69  results/summary.json
e07742d15e1f3d39fc6a653b0ffd1a411807a7ba03874fb1a59d8ecbf7e54a00  results/sweep.csv
d7ee80ad8c4828990ee720aa8c01ade15ad91b35f876ab87be44b472424ea76e  results/wildppg_summary.json
c7c36aabfd3b416dd4f65ad3fb3b4aefb6dc12fd26cba42f3caf487c99cee6a9  results/wildppg_sweep.csv
0788494a683c284bcae563b84773e14e17f0be741ef30a23912506ca3d0cfa31  results/oracle_check.json
bfb3d2b6af0198315bffa69950bdaa828f4ff7f7f29e63cf6491d7c3a1ac77a3  results/sqi_calibration.json
```

Original §10 outputs, reported identical on two runs before the count-feature correction;
feature extraction was not repeated at that stage (about 15 minutes):

```
b5ff68ae0feeab04f437d44e72823184f9a79b7b00b42c98871197c4154f956e  results/quality_models.json
8bec761f335418e0ff184ee7c9f1b69472dca30fd77f8e3089378612298c6356  results/robustness_quality.json
20b19b2cf75dea517e9266be47f1d370e1e791b100ac57f2480be9275dbfb7c5  results/conformal.json
3ab751d8133b598d209db93651c5b3034d05f0c389c024ab67f805de3e1363a5  results/explain.json
```

Original stress outputs (evaluation reported identical on two runs; replay deterministic):

```
4aac5823108b2a18f0d70d2c3f7217753595a4e2a3570e636d0b175df937336e  results/stress_finger.csv
72ab83355ad7cd3affbec9dbb66c2135791e270ab6d10623058563fd0ca20524  results/stress_forehead.csv
690aef26171442739d51a35449ec10acd072e55176945a03bfa94f49cf7bdaf6  results/stress_eval.json
```
