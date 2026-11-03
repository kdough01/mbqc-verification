"""
reproduce_table2.py — Table II rows with the calibrated configuration, one run per instance.

    python experiments/rre/reproduce_table2.py [--only qft:4 fh:2 ...] [--out-dir results/calibrated]

The calibrated configuration is config_calibrated.yaml plus the per-family settings below, all settled by
calibrate.py on the QFT rows (README.md, "Calibration"). Each instance writes <family>_<label>.json (every RRE output
and provenance) and table2_<family>_<label>.json (Table II, column by column, compare.MAPPING).

Per-family settings (not stated in the paper):
  qft    one widget for the whole circuit: the QFT rows' bus patches and runtimes reproduce only without widgets
  fh     RRE's example widgetizer (≤ 10,000 gates, ≤ 100 qubits); ancillas reused in allocation order (greedy-fifo),
         which reproduces ñ_logical = 74 at 4×4. fh:4:finer uses ≤ 40-qubit widgets (14 distinct, 2,948 steps)
  ising  RRE's example widgetizer; greedy ancilla reuse
Instances above the small set (FH 8×8+, QFT N-500/1000, Ising 5×5+) are for the larger machine (README.md).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
CONFIG = HERE / "config_calibrated.yaml"
ONE_WIDGET = (10**9, 10**4)
# id -> (model, n, max_gates, max_q, qubit_manager)
INSTANCES = {
    "qft:4": ("qft", 4, *ONE_WIDGET, "simple"),
    "qft:10": ("qft", 10, *ONE_WIDGET, "simple"),
    "qft:25": ("qft", 25, *ONE_WIDGET, "simple"),
    "qft:100": ("qft", 100, *ONE_WIDGET, "simple"),
    "fh:2": ("fh", 2, 10000, 100, "greedy-fifo"),
    "fh:4": ("fh", 4, 10000, 100, "greedy-fifo"),
    "fh:4:finer": ("fh", 4, 10000, 40, "greedy-fifo"),
    "ising:2": ("ising", 2, 10000, 100, "greedy"),
}
# For the larger machine only (README.md, "Larger instances"); pass them with --only.
LARGE = {
    "fh:8": ("fh", 8, 10000, 100, "greedy-fifo"),
    "fh:16": ("fh", 16, 10000, 100, "greedy-fifo"),
    "fh:20": ("fh", 20, 10000, 100, "greedy-fifo"),
    "qft:500": ("qft", 500, *ONE_WIDGET, "simple"),
    "qft:1000": ("qft", 1000, *ONE_WIDGET, "simple"),
    "ising:5": ("ising", 5, 10000, 100, "greedy"),
}


def file_stem(inst: str, result: dict) -> str:
    fam = inst.split(":")[0]
    stem = f"{fam}_{result['instance']['lattice']}"
    return stem + ("_finer" if inst.endswith(":finer") else "")


def main(argv=None) -> int:
    import compare
    import fh
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="+", default=list(INSTANCES))
    ap.add_argument("--out-dir", default=str(HERE / "results" / "calibrated"))
    args = ap.parse_args(argv)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for inst in args.only:
        model, n, mg, mq, qm = {**INSTANCES, **LARGE}[inst]
        with contextlib.redirect_stdout(io.StringIO()):
            r = fh.run(n, "random", 0, CONFIG, [], max_gates=mg, max_q=mq, qubit_manager=qm, model=model,
                       label=f"calibrated:{inst}")
        stem = file_stem(inst, r)
        (out / f"{stem}.json").write_text(json.dumps(r, indent=1, default=str) + "\n", encoding="utf-8")
        c = compare.compare(r)
        c["instance_id"] = inst
        c["settings"] = {"config": CONFIG.name, "max_gates": mg, "max_q": mq, "qubit_manager": qm}
        (out / f"table2_{stem}.json").write_text(json.dumps(c, indent=1) + "\n", encoding="utf-8")
        print(f"{inst}: matched {', '.join(c['matched']) or 'none'}; not matched {', '.join(c['not_matched'])}",
              flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
