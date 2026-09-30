#!/usr/bin/env bash
# Rebuilds every number and the figure used in brief/brief_draft.md.
set -euo pipefail
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install -q -r requirements.txt
.venv/bin/python -m pip check
./download_ptt_ppg.sh                                   # ~410 MB, SHA-256 verified
# Dart reference outputs (dart_ref/out/) are committed. Regenerating them needs the Dart SDK
# and the original app sources next to this folder (team project, not published).
if command -v dart >/dev/null && [ -d ../smart_wearables_app_stress/lib/processing ]; then
  .venv/bin/python dart_ref/gen_reference.py
  .venv/bin/python dart_ref/gen_stress_reference.py
else
  echo "skipping Dart reference regeneration (app sources or Dart SDK not found); using committed dart_ref/out/"
fi
.venv/bin/python -m pytest -q tests/ | tee results/pytest_output.txt
.venv/bin/python run_analysis.py                        # results/windows.csv, sweep.csv, summary.json
.venv/bin/python fiducial_check.py > /dev/null          # results/fiducial_check.{csv,json}
.venv/bin/python validate_rpeaks.py > /dev/null         # results/rpeak_validation.json (R detector vs manual peaks)
./download_wildppg.sh all                               # 16 files, ~19.6 GB transfer one at a time; raw deleted after extraction
.venv/bin/python run_wildppg.py an0 e61                 # results/wildppg_*.{csv,json}
.venv/bin/python wildppg_channel_check.py > /dev/null   # results/wildppg_channel_check.json
.venv/bin/python oracle_check.py > /dev/null            # results/oracle_check.json, fig_oracle.{png,pdf}
.venv/bin/python calibrate_sqi.py                       # results/sqi_calibration.json
.venv/bin/python build_features.py all                  # results/features_{finger,forehead}.csv (~15 min)
.venv/bin/python quality_models.py                      # results/quality_models.json, fig_quality_models
.venv/bin/python conformal.py                           # results/conformal.json, fig_conformal (~5 min)
.venv/bin/python explain.py                             # results/explain.json, fig_shap
.venv/bin/python robustness_quality.py > /dev/null      # results/robustness_quality.json
.venv/bin/python fig_tracking.py                        # results/fig_tracking.{png,pdf}
.venv/bin/python build_stress.py all                    # results/stress_{finger,forehead}.csv (~12 min)
.venv/bin/python stress_eval.py                         # results/stress_eval.json (~4 min)
.venv/bin/python fig_brief.py                           # results/fig_brief.{png,pdf} (brief figure)
.venv/bin/python make_figure.py                         # results/fig_sqi_tradeoff.{png,pdf}
cp results/fig_brief.png ../brief/fig_brief.png
.venv/bin/python check_doc_numbers.py --write
.venv/bin/python ../brief/build_pdf.py                  # requires Chrome/Chromium
./check_terra_schema.sh                                 # results/terra_schema_check.txt (network)
shasum -a 256 results/summary.json results/sweep.csv results/fiducial_check.json \
  results/rpeak_validation.json results/wildppg_summary.json results/wildppg_sweep.csv \
  results/oracle_check.json results/sqi_calibration.json
