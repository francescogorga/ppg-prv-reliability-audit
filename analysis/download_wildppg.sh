#!/usr/bin/env bash
# Downloads raw WildPPG participant files (ETH Zurich polybox public share, no login;
# data license CC BY-NC-SA 4.0), extracts the channels used here into
# data/wildppg/<id>.npz and deletes the raw .mat (1.1-1.4 GB each) to save disk.
#
# usage: ./download_wildppg.sh an0 e61          # the two participants analysed here
#        ./download_wildppg.sh all              # all 16 (19.6 GB of transfer, one at a time)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SHARE="NWTuyNojU7aya1y"
BASE="https://polybox.ethz.ch/public.php/webdav/data"
ALL="an0 e61 fex k2s kjd l38 n31 ngh p5d p9p qm9 ssx trh tz8 u7y w4p"
IDS="$*"; [ "$IDS" = "all" ] && IDS="$ALL"
mkdir -p "$HERE/data/wildppg_raw" "$HERE/data/wildppg"
for id in $IDS; do
  out="$HERE/data/wildppg/$id.npz"
  if [ -s "$out" ]; then echo "$id: already extracted"; continue; fi
  raw="$HERE/data/wildppg_raw/WildPPG_Part_$id.mat"
  [ -s "$raw" ] || curl -s --fail --retry 3 -u "$SHARE:" -o "$raw" "$BASE/WildPPG_Part_$id.mat"
  "$HERE/.venv/bin/python" "$HERE/load_wildppg.py" extract "$raw" "$out"
  rm -f "$raw"
  echo "$id: extracted to $out"
done
