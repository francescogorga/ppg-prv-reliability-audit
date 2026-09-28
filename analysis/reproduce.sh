#!/usr/bin/env bash
# Rebuilds every number and the figure used in brief/brief_draft.md.
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
./download_ptt_ppg.sh                                   # ~410 MB, SHA-256 verified
# Dart reference outputs (dart_ref/out/) are committed. Regenerating them needs the Dart SDK
# and the original app sources next to this folder (team project, not published).
if command -v dart >/dev/null && [ -d ../smart_wearables_app_stress/lib/processing ]; then
  .venv/bin/python dart_ref/gen_reference.py
else
  echo "skipping Dart reference regeneration (app sources or Dart SDK not found); using committed dart_ref/out/"
fi
.venv/bin/python -m pytest -q tests/ | tee results/pytest_output.txt
.venv/bin/python run_analysis.py                        # results/windows.csv, sweep.csv, summary.json
.venv/bin/python fiducial_check.py > /dev/null          # results/fiducial_check.{csv,json}
.venv/bin/python validate_rpeaks.py > /dev/null         # results/rpeak_validation.json (R detector vs manual peaks)
./download_wildppg.sh an0 e61                           # ~2.2 GB transfer, raw deleted after extraction
.venv/bin/python run_wildppg.py                         # results/wildppg_*.{csv,json}
.venv/bin/python wildppg_channel_check.py > /dev/null   # results/wildppg_channel_check.json
.venv/bin/python make_figure.py                         # results/fig_sqi_tradeoff.{png,pdf}
./check_terra_schema.sh                                 # results/terra_schema_check.txt (network)
shasum -a 256 results/summary.json results/sweep.csv results/fiducial_check.json \
  results/rpeak_validation.json results/wildppg_summary.json results/wildppg_sweep.csv
