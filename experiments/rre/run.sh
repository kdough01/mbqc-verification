#!/usr/bin/env bash
# Run the Fermi–Hubbard reproduction and write experiments/rre/results/.
#
#   bash experiments/rre/run.sh                 # small instances (2x2, 4x4) and the side studies
#   bash experiments/rre/run.sh --only 8 16 20  # larger lattices only (the bigger machine, see README.md)
#
# Run inside the environment that environment.sh builds (source .rre/venv/bin/activate). Each lattice writes
# fh_NxN.json (every RRE output plus provenance), table2_NxN.json (against the paper's Table II) and
# rederive_NxN.json (Appendix A formulas against RRE's outputs). Without --only, phases.json, sensitivity.json
# and the two cabaliser_inputs files are rewritten too. Afterwards `dagtool run --stale` picks up the change.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${RRE_RESULTS:-$HERE/results}"
PY="${PYTHON:-python}"
SAMPLES="${CABALISER_SAMPLES:-20}"
extras=1
if [ "${1:-}" = --only ]; then extras=0; shift; fi
sizes=("$@"); [ ${#sizes[@]} -gt 0 ] || sizes=(2 4)
export RRE_COMMIT="${RRE_COMMIT:-9383b4d}"
mkdir -p "$OUT"

for n in "${sizes[@]}"; do
  lat="${n}x${n}"
  echo "== Fermi–Hubbard $lat"
  "$PY" "$HERE/fh.py" --n "$n" --out "$OUT/fh_$lat.json"
  "$PY" "$HERE/compare.py" "$OUT/fh_$lat.json" > "$OUT/table2_$lat.json"
  "$PY" "$HERE/rederive.py" "$OUT/fh_$lat.json" > "$OUT/rederive_$lat.json"
done

if [ "$extras" = 1 ]; then
  echo "== random vs optimized QSP phases";   "$PY" "$HERE/phases.py" --n 2 4 --out "$OUT/phases.json"
  echo "== sensitivity to unstated settings"; "$PY" "$HERE/sensitivity.py" --n 2 4 --out "$OUT/sensitivity.json"
  echo "== compiled graphs on general inputs ($SAMPLES random inputs)"
  "$PY" "$HERE/cabaliser_inputs.py" --samples "$SAMPLES" --out "$OUT/cabaliser_inputs.json"
  "$PY" "$HERE/cabaliser_inputs.py" --samples "$SAMPLES" --table rre_test --out "$OUT/cabaliser_inputs_rre_test_table.json"
fi
echo "done: $OUT"
