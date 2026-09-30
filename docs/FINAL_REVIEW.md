# Final review record for Terra

The review was developed on `review/terra-final-polish` from `main` at `1921f37` and committed as
`1dcbeaf`. It was pushed to GitHub, and the remote unit-test workflow passed. The adjacent
university `Project` repository was not edited. This document records the review and its local
verification; the commands, file list and diff below describe that review snapshot.

## A. Executive assessment

The reviewed repository is prepared for an external technical review.
The contribution is now framed as measurement reliability, quality selection, downstream consequences,
uncertainty and limitations. It is not publication-grade validation or evidence that the glasses measure
stress reliably. The negative free-living forehead result remains prominent.

This was more than copy editing: a count-feature denominator bug was found, corrected as an explicitly
bounded proxy, and all dependent saved-table analyses were regenerated. Timing/RMSSD measurements and
all stress display-gate results, including CIs, remain unchanged. The uncertainty/model outputs that
actually changed were updated rather than cosmetically held to their old values.

## B. Scientific corrections and material wording changes

| Before | After / reason |
|---|---|
| “HRV was wrong”; “true median” | PPG-derived RMSSD is a PRV estimate; ECG-derived RMSSD is the HRV reference. The distinction appears at first use. |
| WildPPG detector “validated on manual annotations,” without clear dataset scope | Detector benchmarked on PTT-PPG ECG resampled to 128 Hz. The 1.57 ms timing and 0.19 ms RMSSD results do not measure annotated WildPPG accuracy. |
| “best of 24 signals”; “quality signal to use” | A strong interpretable candidate in this exploratory audit. There are 24 model inputs but only eight explicitly compared standalone features. |
| Window's “average beat” | Pointwise median of demeaned pulse segments, followed by mean normalized correlation; this matches the implementation. |
| “intervals held their 90% coverage”; “honest intervals” | Targets 90% marginal coverage under exchangeability; empirical pooled coverage does not establish exchangeability, per-person coverage or post-selection coverage. |
| “what the app would show with perfect beats” | The same application using ECG-derived HR/RMSSD, with its own measured baseline and reference-cleaning choices; not psychological stress truth. |
| “confident levels” compared directly with app levels | Confident fixed score bands are distinguished from the app's hysteretic levels. |
| Similar calm prevalence means the gate is “not keeping easy ones” | Similar prevalence only argues against one majority-class explanation; other selection effects remain. |
| Analyses rerun “bit-identically” | Previous identical-output observations are scoped to the recorded environment. Direct pins and seeds do not guarantee cross-platform identity. |
| Terra schema commit `9eccc73` in technical prose | Actual saved/rechecked revision `5944de59e7f2ccb941254c6907d52ebee08d58d8`. Only inspected public sample objects are described. |
| “50% gate” without its denominator | 50% calibration target versus 46% realized finger display coverage; 25% target versus 16% forehead coverage after baseline/session restrictions. |
| “60 s baseline” / “12 s means” as unconditional wall-clock durations | 60 accepted update ticks; rolling means of 12 accepted valid values. Gating can extend elapsed time. |

The PRV distinction is supported by [Schäfer and Vagedes (2013)](https://pubmed.ncbi.nlm.nih.gov/22809539/).
The paper is context for terminology, not external validation of this audit's algorithm.

## C. Methodological findings

### Fixed: invalid negative rejection fraction

Previously `reject_frac = 1 − n_accepted/(n_peaks−1)`. Accepted intervals are assigned by closing
packet, so the first interval can begin before the window. This yielded negative values in **187/491
finger** and **201/12,998 forehead** rows. Two finger and four forehead rows even had one more
accepted closing packet than in-window peak locations because the detector reports a peak one sample later.

The replacement is `clip(1 − n_accepted/max(n_peaks,1), 0, 1)`, with 1 when no peaks occur.
It is explicitly a **count proxy**, not an exact decision-level rejection fraction. The existing field
name is retained for compatibility; prose and SHAP labels identify the proxy. Exact per-decision
rejection rates would require raw beat re-extraction and remain a possible future improvement.

The change can be reproduced exactly from saved counts without downloading raw recordings. A cellwise
comparison against `main` confirmed that **only `reject_frac` changed in each feature CSV**. These outputs
were rerun: quality models/OOF scores, robustness, RMSSD conformal intervals, SHAP, stress evaluation,
and their figures. No model hyperparameters or selected feature were retuned after seeing these reruns.

| Result affected by count-feature correction | Before | After |
|---|---|---|
| Finger GBM AURC (ms) | 7.142808 | 7.129110 |
| Forehead GBM AURC (ms) | 49.593388 | 49.594320 |
| Finger rejection-proxy AURC (ms) | 7.358471 | 7.644861 |
| Forehead rejection-proxy AURC (ms) | 53.355890 | 53.341738 |
| Finger adaptive RMSSD coverage (fraction) | 0.893828 | 0.893515 |
| Forehead adaptive RMSSD coverage (fraction) | 0.892566 | 0.892812 |
| Finger adaptive RMSSD median width (ms) | 58.252255 | 57.841969 |
| Forehead adaptive RMSSD median width (ms) | 222.656462 | 222.685971 |
| Forehead confident-score-band kappa | 0.030275 | 0.037044 |

### Fixed: conformal finite-sample boundary

The prior quantile code clamped an out-of-range rank to the maximum calibration score. For very small
calibration sets, the augmented `(n+1)`th order statistic must instead be infinite. Both RMSSD and stress
calibration now use the corrected helper; empty calibration raises an explicit error. Regression tests
cover eight, nine and nineteen calibration scores. Existing calibration sets are larger, so this boundary
fix itself does not alter saved results. The table above reflects the feature correction.

### Fixed: full-reproduction cohort drift

`reproduce.sh` downloaded all 16 WildPPG participants and then `run_wildppg.py` used every available file,
although its committed historical outputs and the early technical sections described only `an0/e61`.
The historical analysis now defaults explicitly to those two participants, and reproduction passes the
IDs. Full-cohort feature and stress analysis still uses all downloaded participants. Missing extracted
data now fails explicitly. This correction was checked by code inspection/compilation; the large raw-data
pipeline was not run in this review.

### Documented: separation, dependence and selection

- Inspected LOSO fitting, feature-direction selection, preprocessing, cross-site training, stress
  thresholds, and conformal train/calibration/test splits. No held-out subject's ECG error was found
  entering its fitted model, direction, display threshold or conformal calibration. ECG is absent from
  `window_features` inputs; an artificial test of changing a non-input would add no useful coverage.
- This does not remove study-level selection bias: both datasets influenced candidate design and the
  narrative. Cross-site checks are not a third independent confirmation.
- Quality risk/coverage curves sort pooled OOF scores at a requested retained fraction. They evaluate
  ranking retrospectively, not a threshold that necessarily attains that fraction on a new person.
- Sixty-second feature windows do not overlap, but SQI/interval buffers and stress state span windows.
  Stress rows sample minute-end outputs from a 1 Hz replay. Temporal dependence persists.
- Subject-bootstrap CIs retain within-person dependence, but reuse fitted OOF scores and do not refit
  models or repeat feature selection. The initial two-person forehead study uses 10-minute blocks;
  it cannot estimate population-level between-person uncertainty.
- ECG cleaning for stress uses a centred local median; this is an offline reference. WildPPG reference
  screening is imperfect and unavailable as a deployment-time quality flag.
- Template segments contribute to their own median template. This is not label leakage, but a
  self-inclusion effect and a repeated-artefact failure mode remain.
- The `gbm_signal_only` ablation removes specified variability-derived features, not every feature
  related to beats: HR and beat counts remain. Its legacy name is now explained.
- All display-rule results are conditioned on evaluable ECG-reference minutes. False alarms/misses are
  conditional on displayed minutes; abstentions are separate. Similar class prevalence is not proof
  that selection is unbiased. Overlapping CIs alone do not establish equal performance.

### Stale claims corrected

The public-schema commit, unconditional reproducibility claim, “all 24 individually compared” implication,
median-versus-average template wording, baseline duration, and two-person versus full-cohort distinction
were corrected. The translated calibration table uses the saved 28.3 ms upper percentile, previously
rounded as 28.4 ms. None of these prose corrections changes experimental data.

## D. Engineering and reproducibility

- Added push/PR unit-test CI on Python 3.14, with read-only repository permissions and a timeout.
  It installs the existing requirement pins and runs `pip check` and `pytest analysis/tests/` only.
- Kept dependency pins unchanged. Installation succeeded in a project-local venv on **CPython 3.14.3,
  macOS arm64**. A Linux x86_64 Python 3.14 binary-wheel resolution dry run also succeeded.
- Added four meaningful regression cases: count-proxy boundaries; absent-signal features;
  small-sample conformal rank; empty calibration failure.
- Added a standard-library numerical checker for marked tables/snippets, headline values, count proxies,
  and RMSSD medians independently recomputed from CSVs. Historical translated result tables are also
  checked cell by cell. `--write` refreshes marked result blocks; default mode is read-only.
- Reproduction installs/checks pins even if a venv already exists, preserves the initial WildPPG cohort,
  copies the regenerated brief figure, refreshes marked tables and builds the PDF.
- PDF building detects Chrome/Chromium or accepts `CHROME_BIN`, uses a temporary browser profile,
  has a timeout and cleans temporary HTML. The enlarged figure and wrapped caption improve legibility.
- The Terra check is pinned by default, cleans temporary files, checks expected files exist and only
  replaces the evidence output after successful completion.
- Removed a tautological feature-list assertion. No packaging framework or unrelated refactoring added.
- Direct dependencies are pinned; the entire transitive environment is not locked. WildPPG lacks an
  upstream checksum verification step. Those are disclosed limitations, not guarantees supplied by CI.

## E. Documentation

Rewrote the root overview around the measurement-to-downstream chain, translated the full technical
README with its original section structure and historical experiments, corrected the brief, and rebuilt
its two-page PDF. The original Italian technical version remains available in Git history rather than
being duplicated as a second potentially stale document. The historical pipeline note remains Italian,
with terminology, baseline and fixture-count clarifications.

The scope note distinguishes the original team prototype, Francesco's independent follow-up and offline
v2. The AI-development note confirms tool use without claiming that the author has already personally
reviewed every new conclusion. Existing AI co-author metadata and all history remain untouched.

## F. Terra positioning

The public schema observation is tied to the exact saved revision, rechecked during this review. It makes
no assertion about internal quality processing, product flaws or proprietary architecture. Platform
relevance is posed as a question of preserving upstream quality metadata when available, while making
clear that waveform template consistency cannot be recovered from summary biomarkers alone.

## G. Files changed

The following files were added or modified by the review commit. No files were deleted.

- `.github/workflows/tests.yml` (new)
- `README.md` (modified)
- `analysis/README.md` (modified)
- `analysis/build_features.py` (modified)
- `analysis/build_stress.py` (modified)
- `analysis/check_doc_numbers.py` (new)
- `analysis/check_terra_schema.sh` (modified)
- `analysis/conformal.py` (modified)
- `analysis/explain.py` (modified)
- `analysis/features.py` (modified)
- `analysis/fig_brief.py` (modified)
- `analysis/fig_tracking.py` (modified)
- `analysis/load_wildppg.py` (modified)
- `analysis/quality_models.py` (modified)
- `analysis/reproduce.sh` (modified)
- `analysis/results/conformal.json` (modified)
- `analysis/results/explain.json` (modified)
- `analysis/results/features_finger.csv` (modified)
- `analysis/results/features_forehead.csv` (modified)
- `analysis/results/fig_brief.pdf` (modified)
- `analysis/results/fig_brief.png` (modified)
- `analysis/results/fig_conformal.pdf` (modified)
- `analysis/results/fig_conformal.png` (modified)
- `analysis/results/fig_quality_models.pdf` (modified)
- `analysis/results/fig_quality_models.png` (modified)
- `analysis/results/fig_shap.pdf` (modified)
- `analysis/results/fig_shap.png` (modified)
- `analysis/results/fig_tracking.pdf` (modified)
- `analysis/results/fig_tracking.png` (modified)
- `analysis/results/oof_scores_finger.csv` (modified)
- `analysis/results/oof_scores_forehead.csv` (modified)
- `analysis/results/pytest_output.txt` (modified)
- `analysis/results/quality_models.json` (modified)
- `analysis/results/review_checksums.txt` (new)
- `analysis/results/robustness_quality.json` (modified)
- `analysis/results/stress_eval.json` (modified)
- `analysis/results/stress_eval_stdout.txt` (modified)
- `analysis/results/terra_schema_check.txt` (modified)
- `analysis/robustness_quality.py` (modified)
- `analysis/run_wildppg.py` (modified)
- `analysis/stress.py` (modified)
- `analysis/stress_eval.py` (modified)
- `analysis/tests/test_conformal.py` (new)
- `analysis/tests/test_features.py` (modified)
- `brief/brief.pdf` (modified)
- `brief/brief_draft.md` (modified)
- `brief/build_pdf.py` (modified)
- `brief/fig_brief.png` (modified)
- `docs/FINAL_REVIEW.md` (new)
- `docs/PIPELINE_ATTUALE.md` (modified)

## H. Important commands actually executed

Commands were run from the target checkout unless a temporary verification script is indicated.

```bash
git status --short --branch
git branch --list
git remote -v
git switch -c review/terra-final-polish
python3 --version
python3 -m venv analysis/.venv
analysis/.venv/bin/python -m pip install -r analysis/requirements.txt
analysis/.venv/bin/python -m pip check
analysis/.venv/bin/python -m pytest -q analysis/tests/
analysis/.venv/bin/python -m pytest -q analysis/tests/test_features.py analysis/tests/test_conformal.py
analysis/.venv/bin/python analysis/quality_models.py
analysis/.venv/bin/python analysis/conformal.py
analysis/.venv/bin/python analysis/robustness_quality.py
analysis/.venv/bin/python analysis/explain.py
analysis/.venv/bin/python analysis/stress_eval.py
analysis/.venv/bin/python analysis/fig_tracking.py
analysis/.venv/bin/python analysis/fig_brief.py
analysis/.venv/bin/python analysis/check_doc_numbers.py --write
analysis/.venv/bin/python analysis/check_doc_numbers.py
analysis/.venv/bin/python brief/build_pdf.py
analysis/check_terra_schema.sh
bash -n analysis/reproduce.sh analysis/check_terra_schema.sh analysis/download_ptt_ppg.sh analysis/download_wildppg.sh
pdftoppm -scale-to 1400 -png brief/brief.pdf /tmp/terra-polish/final-brief
analysis/.venv/bin/python /tmp/terra-polish/verification.py
git diff --check
git diff --stat main
```

Reruns used `OMP_NUM_THREADS=1`, with `OPENBLAS_NUM_THREADS=1` for model computations and
`MPLCONFIGDIR=/tmp/terra-mpl`. Output logs were inspected; stress stdout was copied to its tracked log.
Additional executed checks: Ruby YAML parsing/assertions for triggers and test command; pypdf page/text
inspection; cellwise CSV comparison against `git show main:...`; raw-derived output byte comparisons;
local Markdown link checks; result SHA-256 capture; and the following dependency dry run:

```bash
analysis/.venv/bin/python -m pip install --dry-run --ignore-installed --only-binary=:all: \
  --platform manylinux_2_28_x86_64 --platform manylinux_2_27_x86_64 \
  --platform manylinux2014_x86_64 --python-version 3.14 --implementation cp \
  --abi cp314 --abi abi3 -r analysis/requirements.txt
```

## I. Actual verification outcomes

- Original suite: **39 passed in 37.44 s**. One sandbox-related pytest-cache write warning; no test failure.
- Focused added tests: **6 passed in 2.32 s**. An earlier draft of the new absent-signal test used
  nonzero DC and encountered filter startup ringing; the fixture was corrected to a zero input.
- Final full suite: **43 passed in 13.45 s**, no warnings.
- `pip check`: **No broken requirements found**.
- Linux dependency dry run: all pinned requirements resolved to binary distributions. This is
  resolution evidence, not an executed Linux test suite.
- CI: YAML parses; push/PR triggers and test path checked. No local GitHub Actions runner was used.
  After the review commit was pushed, the GitHub Actions unit-test workflow passed
  ([run 36692343691](https://github.com/francescogorga/ppg-prv-reliability-audit/actions/runs/36692343691)).
- All five dependent analysis scripts and both figure scripts completed with exit code 0.
- Numerical checker: all eight generated result blocks, historical table cells, headline values,
  CSV-derived medians, corrected count proxies and schema revision passed.
- CSV audit: only `reject_frac` changed in feature tables. All stress display-rule dictionaries,
  including CIs and coverage, equal their original versions. Raw-derived timing/reference/stress
  tables listed in the verification script are byte-identical to `main`.
- Pinned Terra check completed successfully: sample properties/search findings unchanged; check timestamp updated.
- Brief PDF built successfully, remains **two pages**, and both rendered pages were inspected for
  clipping, table fit, URLs and readable labels. Figure caption was shortened/wrapped after inspection.
- Shell syntax, local Markdown links and `git diff --check` passed.

Not executed during the review: full `reproduce.sh`, raw dataset downloads, fresh Dart reference
generation, new glasses recordings and independent third-dataset validation. The saved artifacts
are evidence of the executed cached-table reruns, not a claim that the entire acquisition pipeline was rerun.

## J. Diff summary

Most changed lines are regenerated CSV rows (one feature column and dependent OOF model scores).
The remaining substantial diff is the English technical translation. Timing and reference estimates were
not cosmetically altered. Current output hashes are in `analysis/results/review_checksums.txt`; historical
hashes remain labelled as historical in the technical README.

```text
 README.md                                |   223 +-
 analysis/README.md                       |   991 +-
 analysis/build_features.py               |     3 +-
 analysis/build_stress.py                 |     2 +-
 analysis/check_terra_schema.sh           |    17 +-
 analysis/conformal.py                    |    13 +-
 analysis/explain.py                      |     2 +-
 analysis/features.py                     |    13 +-
 analysis/fig_brief.py                    |    11 +-
 analysis/fig_tracking.py                 |     4 +-
 analysis/load_wildppg.py                 |     5 +-
 analysis/quality_models.py               |     2 +-
 analysis/reproduce.sh                    |     9 +-
 analysis/results/conformal.json          |   200 +-
 analysis/results/explain.json            |   216 +-
 analysis/results/features_finger.csv     |   980 +-
 analysis/results/features_forehead.csv   | 25888 ++++++++++++++---------------
 analysis/results/fig_brief.pdf           |   Bin 27618 -> 27452 bytes
 analysis/results/fig_brief.png           |   Bin 180275 -> 179576 bytes
 analysis/results/fig_conformal.pdf       |   Bin 19786 -> 19791 bytes
 analysis/results/fig_conformal.png       |   Bin 69050 -> 69103 bytes
 analysis/results/fig_quality_models.pdf  |   Bin 28437 -> 28424 bytes
 analysis/results/fig_quality_models.png  |   Bin 173459 -> 173764 bytes
 analysis/results/fig_shap.pdf            |   Bin 21462 -> 21482 bytes
 analysis/results/fig_shap.png            |   Bin 112654 -> 110799 bytes
 analysis/results/fig_tracking.pdf        |   Bin 28724 -> 28942 bytes
 analysis/results/fig_tracking.png        |   Bin 156200 -> 157646 bytes
 analysis/results/oof_scores_finger.csv   |   982 +-
 analysis/results/oof_scores_forehead.csv | 21890 ++++++++++++------------
 analysis/results/pytest_output.txt       |     3 +-
 analysis/results/quality_models.json     |   176 +-
 analysis/results/robustness_quality.json |   612 +-
 analysis/results/stress_eval.json        |    52 +-
 analysis/results/stress_eval_stdout.txt  |     5 +-
 analysis/results/terra_schema_check.txt  |     2 +-
 analysis/robustness_quality.py           |     4 +-
 analysis/run_wildppg.py                  |    15 +-
 analysis/stress.py                       |     2 +-
 analysis/stress_eval.py                  |     3 +-
 analysis/tests/test_features.py          |    17 +
 brief/brief.pdf                          |   Bin 288861 -> 283691 bytes
 brief/brief_draft.md                     |   147 +-
 brief/build_pdf.py                       |    24 +-
 brief/fig_brief.png                      |   Bin 180275 -> 179576 bytes
 docs/PIPELINE_ATTUALE.md                 |    12 +-
 45 files changed, 26370 insertions(+), 26155 deletions(-)
```

The stat above is the historical tracked-file diff against `main` at `1921f37`. Files newly added
in that review are listed in section G; they were absent from the unstaged diff captured then.

## K. Remaining research limitations

No failing local test/build or unresolved inconsistency was found in the reviewed outputs.

**Important:** no glasses recordings; no direct manual WildPPG ECG validation; exploratory feature selection
on both datasets; small cohorts and conditional bootstrap uncertainty; approximate rejection count proxy;
non-causal reference cleaning and retrospective display gates; stress algorithm not validated against stress
labels; confident score bands not equivalent to hysteretic levels; poor absolute forehead performance;
no full raw-data rerun; no independently regenerable Dart fixtures without app source.
These limits prevent publication-grade or clinical reliability claims.

**Nice to improve:** freeze transitive dependencies and environment metadata for a future release; obtain
WildPPG source-file checksums; translate the historical pipeline note if it becomes an entry point; add
fresh glasses data once hardware and raw export are available. None requires adding a complex framework.

## L. Interview-defense questions and concise answers

1. **Why is PPG RMSSD PRV rather than HRV?** ECG marks cardiac electrical timing; PPG marks peripheral
   pulse arrival. Pulse propagation and fiducial detection can vary independently of R–R timing. This
   audit compares PRV RMSSD with ECG HRV RMSSD; it does not establish universal interchangeability.
2. **Why does RMSSD react so strongly to beat timing?** Interval error contains differences of adjacent
   timestamp errors; RMSSD then differences adjacent intervals again. Variable timing error can therefore
   inflate variability even when median HR looks reasonable. Constant delay alone cancels from intervals.
3. **Why did the systolic fiducial help?** With this input polarity the original maxima occur near a broad
   diastolic foot. Negating the filtered detector input selects a more stable systolic feature. The measured
   lag IQR and finger RMSSD error fall; this does not establish systolic optimality at every anatomical site.
4. **Did you measure pulse transit time?** No. ECG-to-detected-pulse lag includes pulse arrival physiology,
   processing delay, detection error and possible mismatches. The audit cannot separate pre-ejection,
   propagation and algorithmic components from those lag summaries.
5. **Why does the same MAX30101 not validate the glasses?** It controls one hardware difference but not
   vascular bed, geometry, pressure, optical coupling, movement or data transport. Neither public dataset
   reproduces the nose bridge, and WildPPG uses another chip.
6. **What exactly is template consistency?** Demean each complete −0.25/+0.45 s segment around detected
   systolic peaks, construct a pointwise median template and average normalized correlations. It uses no
   ECG, but includes each beat in its own template and can reward repeated artefacts.
7. **Were all 24 features independently compared?** No. There are 24 ECG-free inputs for multifeature
   models and eight explicit single-feature comparisons. Calling the chosen feature “best of 24” overstates
   the design; its usefulness remains an exploratory conclusion.
8. **What does LOSO protect against, and what does it not?** A test person's labels cannot fit its model,
   feature direction or calibration. LOSO does not undo candidate selection, hyperparameter choices or
   interpretation developed after looking across these datasets, nor make windows independent.
9. **Is cross-site success external validation?** It tests transfer when only the source data fit a model.
   Because both sites influenced development and the final narrative, it is a robustness check rather than
   fully independent confirmation. Ranking transfer also differs from threshold transfer.
10. **Why can keeping low estimates look deceptively good?** Absolute error includes the estimate, and
    reference RMSSD is often relatively low. Selecting low estimates can lower error without retaining
    physiological tracking. The forehead negative control has Spearman about 0.20 versus 0.50 for template
    consistency at the same retrospective coverage.
11. **Does correlation prove accurate measurement?** No. It can coexist with a large bias, depends on the
    retained range and can change through selection. That is why the audit reports absolute error, retained
    coverage, reference tracking and downstream consequences together.
12. **What did SHAP establish?** It described fitted-model reliance on the estimate and correlated features,
    motivating a negative control. It did not prove causality, circularity or generalization; the explanation
    model was fit to all labelled data and is separate from held-out performance evaluation.
13. **Why bootstrap people instead of minutes?** Minutes within a person share physiology, activity,
    sensors and processing state. Resampling people preserves these clusters. With 22/16 people the CIs
    remain broad; reusing OOF scores omits refitting and feature-selection uncertainty.
14. **Does split conformal guarantee 90% coverage here?** The standard target is marginal coverage under
    exchangeability. Clustered windows and domain shifts make that assumption uncertain. Empirical pooled
    coverage near target is not a per-person or selected-subset guarantee; some people are much lower.
15. **Why does a 50% gate show only 46% of finger minutes?** The other-subject quantile targets finite
    quality values before baseline restrictions. The current minute and session baseline must both pass,
    and unknown outputs cannot be displayed. Final coverage uses evaluable non-baseline minutes.
16. **Why are the confident stress results different from the main kappa table?** Main comparisons use
    hysteretic app levels. Confidence is defined by an interval lying inside a fixed score band. That is a
    different target; its raw agreement can be dominated by the calm majority class.
17. **What explains the forehead failure?** The saved channel/fiducial checks show weak usable IR pulse
    information, missed beats and unstable timing. Timing correction and selection leave large absolute
    errors. Motion, optical coupling and physiology are plausible contributors, but the audit does not
    isolate their individual causal contributions or directly validate the automatic ECG reference there.
18. **What can Terra infer from this, and what would you do next?** Provider summaries alone cannot recover
    the raw-waveform feature. The study motivates testing what upstream quality metadata is available and
    whether it improves downstream reliability. Next, freeze the method before a third-dataset test, then
    separately study stress validity using protocol labels and eventually real glasses recordings.

## M. Reading guide

Start with the two-page PDF and root README. For a deeper technical review, read the
`rejection_proxy` correction and its rerun impact above, then the subject/coverage/conformal
caveats in the technical README and the provenance/AI note. The file list and historical diff
summary document what changed from `1921f37` to the review commit.

## Proposed frozen third-dataset validation (future work, not performed)

- **Primary question:** does the fixed template-consistency rule lower PRV RMSSD error versus ungated v2
  while preserving ECG tracking at useful realized coverage on a new dataset?
- **Freeze before reference inspection:** detector/filter parameters (0.5–3.5 Hz, 0.8σ over 4 s, 400 ms
  refractory), RR acceptance, systolic polarity convention, 60 s non-overlapping windows after 10 s warmup,
  minimum 10 PPG intervals, template segment −0.25/+0.45 s, pointwise median/demeaning/correlation,
  minimum five complete segments, higher-consistency direction, missing-feature abstention, ECG cleaning,
  endpoint definitions and subject-bootstrap seed/resample count. No additional ML model selection.
- **Threshold strategy:** preallocate approximately one third of the new participants to calibration
  using a recorded subject-ID/seed rule, with no ECG-error inspection. Fix the template-feature threshold
  at the median finite calibration score (50% target); apply it unchanged to the remaining test subjects.
  Report realized coverage among all eligible reference windows and among all recorded windows. Never
  force the test set to exactly 50% by reranking it. A separately declared fixed source-threshold arm can
  assess zero-calibration transfer; it must not replace the primary arm after results are seen.
- **Primary endpoint and decision rule:** subject-bootstrap CI for the reduction in pooled median
  absolute RMSSD error relative to ungated v2, together with retained-value tracking and realized coverage.
  A proposed confirmation rule is a positive lower 95% CI for error reduction, no material tracking loss
  (predeclare a −0.05 Spearman non-inferiority margin), and at least 25% realized test coverage. These
  margins are prospective engineering choices, not validated physiological tolerances. Failing any criterion
  is failure of the proposed confirmation; wide CIs may make the result inconclusive rather than positive.
- **Dataset choice:** WESAD offers a stress protocol; PPG-DaLiA emphasizes daily activities. Select one,
  verify licence/access and record that choice before outcomes. Do not run both and report only the winner.
  Processed wrist BVP is not raw DC-bearing optical data: omit the app's DC amplitude SQI as inapplicable,
  explicitly define polarity/scaling from sensor documentation and input-only checks, and do not claim a
  replication of the original raw-optical pipeline. If compatibility needs outcome-guided changes, stop
  the frozen test and label a separate adaptation study.
- **Stress secondary endpoint:** assess ECG-based application agreement under the fixed baseline/session
  rules first. Compare to WESAD protocol labels separately; those address stress validity, not just
  measurement propagation. Prespecify whether score bands or hysteretic levels are the target.
- **Governance:** save code/config/input hashes and the calibration/test split before evaluating ECG errors;
  retain all exclusions and negative results. Bug fixes after unblinding require explicit disclosure and
  cannot be called untouched frozen confirmation. Do not tune per-person uncertainty on held-out test labels.
