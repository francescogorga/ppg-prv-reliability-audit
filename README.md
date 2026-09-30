# Can a smart-glasses stress index trust PPG-derived HRV?

[![tests](https://github.com/francescogorga/ppg-sqi-hrv-audit/actions/workflows/tests.yml/badge.svg)](https://github.com/francescogorga/ppg-sqi-hrv-audit/actions/workflows/tests.yml)

Our university team built smart glasses with a nose-bridge PPG sensor and an app that converts
heart rate and HRV (RMSSD) into a personal-baseline stress index. After returning the hardware,
I audited the application offline against public PPG + ECG recordings: **22 finger subjects in
laboratory activities and 16 forehead participants in daily life**.

**Terminology:** the app calls this HRV. PPG pulse-to-pulse variability is strictly **PRV**;
“PPG-derived HRV/RMSSD” here means that PRV estimate. ECG-derived RMSSD is the HRV reference.
They are not universally interchangeable ([reference and method](analysis/README.md)).

**Short answer.**

- **Fix beat timing first.** On finger data, the ungated app pipeline had median absolute error
  **85.5 ms**, against median ECG RMSSD **22.3 ms**. Offline systolic timing reduced error to
  **18.1 ms**; the original detector used an unstable diastolic-foot fiducial.
- **Then assess beat consistency.** Beat-template correlation was one of the strongest interpretable
  candidates in this audit of 24 ECG-free features. Its selection is exploratory, not externally validated.
- **Follow the error downstream.** Finger stress-level κ rose from **0.28 → 0.40 → 0.68** with
  timing correction and consistency gating, at **46% realized display coverage**. Conditional false
  alarms fell from **31% to 13%**. The reference is the same app using ECG-derived HR/RMSSD,
  **not psychological stress ground truth**.
- **Free-living forehead PPG still fails.** Ungated v2 RMSSD error remains **89.2 ms**. A more
  aggressive display gate reaches only **κ = 0.33 at 16% coverage**. Quality ranking cannot rescue
  a fundamentally unreliable beat series.
- **Uncertainty exposes the problem.** Split conformal targets 90% marginal coverage under
  exchangeability, not coverage for each person. Forehead score intervals span the full 0–100 scale
  in the median; confident score bands are overwhelmingly calm.

Read the [two-page brief](brief/brief.pdf), then the [full method in English](analysis/README.md).
The Python reconstruction is checked against committed outputs from the original Dart classes;
unit tests and saved-table analyses need no raw-data download.

![PPG RMSSD selection and agreement with the ECG-based application output](brief/fig_brief.png)

<!-- BEGIN STRESS_TABLE -->
| Stress output vs ECG-based app output | Minutes shown | Cohen’s κ (95% CI) | False alarms |
|---|---|---|---|
| Finger — original app | 100% | 0.28 (0.21–0.36) | 31% |
| Finger — systolic v2 | 100% | 0.40 (0.29–0.52) | 25% |
| Finger — v2 + consistency, 50% target | 46% | 0.68 (0.52–0.79) | 13% |
| Forehead — original app | 91% | 0.15 (0.12–0.19) | 43% |
| Forehead — v2 + consistency, 25% target | 16% | 0.33 (0.16–0.42) | 36% |
<!-- END STRESS_TABLE -->

“Minutes shown” uses evaluable non-baseline minutes with a screened ECG reference as its denominator.
The finger gate targets 50% before baseline/session exclusions; the forehead gate targets 25%.
False alarms are non-calm outputs among **displayed ECG-reference-calm minutes**. Abstentions are
not counted as errors or successes. CIs resample participants, not individual minutes.

## Why low error alone is insufficient

A rule that keeps low PPG RMSSD can look accurate simply because ECG RMSSD is often low.
The explicit `ppg_rmssd_low` negative control exposes this: on the forehead, its retained estimates
track ECG weakly (Spearman **0.20**, versus **0.50** for template consistency, both at 25% ranking
coverage). SHAP highlighted reliance on the estimate itself and motivated this check; it did not
prove circularity. Tracking supplements error and coverage, and does not eliminate bias.

LOSO excludes each test subject from model fitting and direction selection. Cross-site rankings
provide a robustness check, but both datasets influenced feature development and interpretation.
An independent third dataset is needed for external validation.

## Repository map

| Path | Purpose |
|---|---|
| `brief/` | Research brief, PDF and build script |
| `analysis/README.md` | Methods, definitions, tables, caveats and reproduction |
| `analysis/app_pipeline.py`, `analysis/stress.py` | Reconstructed application processing and stress algorithm; `systolic=True` enables offline v2 |
| `analysis/tests/`, `analysis/dart_ref/out/` | Synthetic regression tests and committed Dart equivalence fixtures |
| `analysis/features.py`, `quality_models.py`, `robustness_quality.py` | ECG-free features, LOSO rankings and selection-bias checks |
| `analysis/ecg_rpeaks.py`, `validate_rpeaks.py` | WildPPG R detector benchmarked on annotated **PTT-PPG** ECG |
| `analysis/build_stress.py`, `stress_eval.py`, `conformal.py` | Downstream replay, display gates and uncertainty |
| `analysis/results/` | Saved results and figures traceable to scripts |
| `docs/PIPELINE_ATTUALE.md` | Original implementation audit, in Italian |
| `docs/FINAL_REVIEW.md` | Local review findings, verification, interview preparation and frozen-validation proposal |

## Reproduce

Lightweight checks (Python 3.14; this review used 3.14.3):

```bash
python3 -m venv analysis/.venv
analysis/.venv/bin/python -m pip install -r analysis/requirements.txt
analysis/.venv/bin/python -m pytest analysis/tests/
analysis/.venv/bin/python analysis/check_doc_numbers.py
analysis/.venv/bin/python brief/build_pdf.py  # Chrome/Chromium required
```

For a full raw-data rerun: `cd analysis && ./reproduce.sh`. It transfers ~410 MB PTT-PPG plus
~19.6 GB WildPPG; allow several GB free disk and hours of runtime. Raw WildPPG files are deleted
after extraction, but extracted data accumulate. CI runs only the unit tests.

The model, robustness, conformal and stress-evaluation scripts can rerun from committed CSVs.
Direct dependencies and random seeds are fixed. Prior runs produced identical saved outputs in
the recorded environment; cross-platform bitwise identity is not guaranteed. See the technical
README for checksums, input verification and the review's count-feature correction.

## Scope and provenance

The Flutter/STM32 glasses prototype was a **team project** in *Smart Wearables Design and
Prototyping*, Politecnico di Milano (2026). This repository contains Francesco Gorga's independent
post-course audit. Original app source is not redistributed. The hardware was returned; no glasses
recordings are claimed. **v2 is an offline experiment, not a deployed application change.**

Dart reference outputs are committed. Regenerating them requires the original app sources and
Dart SDK; ordinary tests read the fixtures. The Flutter page's packet/tick ordering is transcribed
in Python and standalone Dart wrappers rather than executed inside Flutter.

AI coding tools were used during implementation and review. Existing authorship metadata and
Git history are preserved. Scientific claims and this review remain subject to the author's final review.

## Relevance to wearable-data platforms

Derived scores inherit upstream measurement error. If device partners expose beat-level quality
metadata, preserving it beside normalized biomarkers could support downstream reliability audits.
Platforms receiving only provider summaries cannot reconstruct raw-waveform template consistency.

At commit `5944de59e7f2ccb941254c6907d52ebee08d58d8`, the inspected HR, HRV and RR sample objects
in Terra's public OpenAPI schema did not expose a quality/confidence field
([saved check](analysis/results/terra_schema_check.txt)). This says nothing about Terra's internal
quality handling or proprietary pipeline. It is a schema observation, not a product recommendation.

## Limitations

- **No glasses data.** Finger and forehead differ from nose bridge in geometry, contact, vascular
  bed and motion. PTT-PPG shares the MAX30101 chip; WildPPG uses MAX86141.
- **Reference scope.** WildPPG has ECG but no manual R annotations. The detector's median 1.57 ms
  timing error and 0.19 ms cleaned-RMSSD difference are from **PTT-PPG validation only**.
  Accuracy on WildPPG itself remains unannotated.
- **Exploratory selection.** Small cohorts, correlated windows, broad subject-bootstrap CIs and
  no independent third-dataset confirmation. Selected-window results do not describe all-day reliability.
- **Stress validity.** Agreement with an ECG-based version of the app does not validate the app's
  psychological interpretation. The conformal score-band analysis also differs from hysteretic app levels.
- **Forehead failure remains.** Relative quality improvement leaves large absolute PRV error,
  weak downstream agreement and mostly uninformative uncertainty.

## Data and licences

- Code: MIT ([LICENSE](LICENSE)).
- PTT-PPG: Mehrgardt et al., *Pulse Transit Time PPG Dataset* v1.1.0, PhysioNet (2022),
  [dataset DOI](https://doi.org/10.13026/jpan-6n92), ODbL 1.0.
- WildPPG: Meier, Demirel and Holz, *WildPPG: A Real-World PPG Dataset of Long Continuous Recordings*,
  NeurIPS 2024 Datasets and Benchmarks; CC BY-NC-SA 4.0 (non-commercial). Forehead-derived results
  retain that licence, including the forehead CSVs and WildPPG outputs.
- Raw datasets are not redistributed; scripts fetch the original sources. The saved API check
  and dataset access notes describe dated observations.
