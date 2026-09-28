#!/usr/bin/env bash
# Downloads the WFDB part (.hea/.atr/.dat, ~480 MB) of the PhysioNet
# "Pulse Transit Time PPG Dataset" v1.1.0 (open access, ODbL 1.0, no login)
# and verifies every file against the official SHA256SUMS.txt.
# The duplicated CSV folder (~2.4 GB) is NOT downloaded.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HERE/data/ptt_ppg"
BASE="https://physionet-open.s3.amazonaws.com/pulse-transit-time-ppg/1.1.0"   # official S3 mirror
mkdir -p "$DEST" && cd "$DEST"
for f in RECORDS LICENSE.txt SHA256SUMS.txt README.txt device_schematic.png; do
  [ -s "$f" ] || curl -s --fail --retry 3 -O "$BASE/$f"
done
want() { for r in $(cat RECORDS); do printf '%s\n' "$r.hea" "$r.atr" "$r.dat"; done; }
bad() {  # files missing or failing the checksum
  want | while read -r f; do
    exp=$(awk -v f="$f" '$2==f {print $1}' SHA256SUMS.txt)
    if [ ! -s "$f" ] || [ "$(shasum -a 256 "$f" | cut -d' ' -f1)" != "$exp" ]; then echo "$f"; fi
  done
}
for attempt in 1 2 3; do
  todo=$(bad)
  [ -z "$todo" ] && break
  echo "attempt $attempt: $(echo "$todo" | wc -l | tr -d ' ') files to fetch"
  echo "$todo" | xargs -P 6 -I{} curl -s --fail --retry 3 -o {} "$BASE/{}" || true
done
left=$(bad)
if [ -n "$left" ]; then echo "STILL MISSING/CORRUPT:"; echo "$left"; exit 1; fi
echo "all $(want | wc -l | tr -d ' ') files present, SHA-256 verified"
