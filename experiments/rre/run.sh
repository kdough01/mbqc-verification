#!/usr/bin/env bash
# Run the Fermi–Hubbard reproduction and write experiments/rre/results/.
#
#   bash experiments/rre/run.sh                 # small instances, calibration, scaling and the side studies
#   bash experiments/rre/run.sh --only fh:8 fh:16 fh:20 qft:500 qft:1000 ising:5   # the bigger machine only
#
# Run inside the environment that environment.sh builds (source .rre/venv/bin/activate). The calibrated runs write
# results/calibrated/<family>_<label>.json (every RRE output plus provenance) and table2_<family>_<label>.json
# (against Table II). Without --only it also reruns the calibration grid, the scaling series, the widget levels,
# and the first pass (fh_NxN.json, table2_NxN.json, rederive_NxN.json with config_paper_v3.yaml), phases.json,
# sensitivity.json and the two cabaliser_inputs files. Afterwards `dagtool run --stale` picks up the change.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${RRE_RESULTS:-$HERE/results}"
PY="${PYTHON:-python}"
SAMPLES="${CABALISER_SAMPLES:-20}"
if [ "${1:-}" = --only ]; then
  shift
  echo "== calibrated: $*"
  "$PY" "$HERE/reproduce_table2.py" --only "$@" --out-dir "$OUT/calibrated"
  echo "done: $OUT"; exit 0
fi
mkdir -p "$OUT/calibrated"

echo "== calibration grid on the QFT rows"; "$PY" "$HERE/calibrate.py" --out "$OUT/calibrated/calibration.json"
echo "== Table II, calibrated";            "$PY" "$HERE/reproduce_table2.py" --out-dir "$OUT/calibrated"
echo "== scaling (actual runs only)";      "$PY" "$HERE/scaling.py" --out "$OUT/calibrated/scaling.json"
echo "== Fermi-Hubbard widget levels";     "$PY" "$HERE/fh_widgets.py" --out "$OUT/calibrated/fh_widgets.json"

for n in 2 4; do   # the first pass: config_paper_v3.yaml and the first column readings
  lat="${n}x${n}"
  echo "== first pass, Fermi-Hubbard $lat"
  "$PY" "$HERE/fh.py" --n "$n" --out "$OUT/fh_$lat.json" > /dev/null
  "$PY" "$HERE/compare.py" --v1 "$OUT/fh_$lat.json" > "$OUT/table2_$lat.json"
  "$PY" "$HERE/rederive.py" "$OUT/fh_$lat.json" > "$OUT/rederive_$lat.json"
done
echo "== random vs optimized QSP phases";   "$PY" "$HERE/phases.py" --n 2 4 --out "$OUT/phases.json"
echo "== sensitivity (first pass)";        "$PY" "$HERE/sensitivity.py" --n 2 4 --out "$OUT/sensitivity.json"
echo "== compiled graphs on general inputs ($SAMPLES random inputs)"
"$PY" "$HERE/cabaliser_inputs.py" --samples "$SAMPLES" --out "$OUT/cabaliser_inputs.json"
"$PY" "$HERE/cabaliser_inputs.py" --samples "$SAMPLES" --table rre_test --out "$OUT/cabaliser_inputs_rre_test_table.json"
echo "done: $OUT"
