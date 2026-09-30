#!/usr/bin/env bash
# Inspect quality/confidence fields in Terra's public OpenAPI schema.
# This describes a public schema snapshot, not Terra's internal quality handling.
# Usage: ./check_terra_schema.sh [commit]; default reproduces the saved snapshot.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
REV="${1:-5944de59e7f2ccb941254c6907d52ebee08d58d8}"
OUT="$HERE/results/terra_schema_check.txt"
mkdir -p "$HERE/results"
git init -q "$TMP/openapi"
cd "$TMP/openapi"
git fetch -q --depth 1 https://github.com/tryterra/openapi "$REV"
git checkout -q --detach FETCH_HEAD
{
  echo "# Terra OpenAPI schema check"
  echo "repo: https://github.com/tryterra/openapi"
  echo "commit: $(git log -1 --format='%H %cd')"
  echo "checked_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  for f in HeartRateDataSample HeartRateVariabilityDataSampleRMSSD \
           HeartRateVariabilityDataSampleSDNN RRIntervalSample HeartRateContext; do
    echo "## schemas/core/$f.yaml -- top-level properties / consts"
    [ -f "schemas/core/$f.yaml" ] || { echo "Missing schema: $f" >&2; exit 1; }
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
} > "$TMP/schema_check.txt"
cp "$TMP/schema_check.txt" "$OUT"
echo "wrote $OUT"
