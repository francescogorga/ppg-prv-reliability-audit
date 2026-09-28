#!/usr/bin/env bash
# Verifica riproducibile: esistono campi di qualita'/confidenza per HR/HRV/RR
# nello schema OpenAPI pubblico di Terra (github.com/tryterra/openapi)?
# Output salvato in analysis/results/terra_schema_check.txt
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TMP="$(mktemp -d)"
OUT="$HERE/results/terra_schema_check.txt"
mkdir -p "$HERE/results"
git clone -q --depth 1 https://github.com/tryterra/openapi "$TMP/openapi"
cd "$TMP/openapi"
{
  echo "# Terra OpenAPI schema check"
  echo "repo: https://github.com/tryterra/openapi"
  echo "commit: $(git log -1 --format='%H %cd')"
  echo "checked_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  for f in HeartRateDataSample HeartRateVariabilityDataSampleRMSSD \
           HeartRateVariabilityDataSampleSDNN RRIntervalSample HeartRateContext; do
    echo "## schemas/core/$f.yaml -- top-level properties / consts"
    grep -E '^  [a-z_]+:|const:|title:' "schemas/core/$f.yaml" || true
    echo
  done
  echo "## files in schemas/ matching quality|confidence|accuracy|reliab|artifact|artefact|sqi (case-insensitive)"
  grep -rliE 'quality|confidence|accuracy|reliab|artifact|artefact|\bsqi\b' schemas || true
  echo
  echo "## same grep restricted to heart/hrv/rr/ecg schema files"
  ls schemas/core | grep -iE 'heart|hrv|rrinterval|ecg' | while read -r f; do
    grep -liE 'quality|confidence|accuracy|reliab|artifact|artefact' "schemas/core/$f" || true
  done
  echo "(empty above = no match)"
} > "$OUT"
rm -rf "$TMP"
echo "wrote $OUT"
