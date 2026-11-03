"""
scaling.py — how the resources grow with problem size, from actual runs only.

    python experiments/rre/scaling.py [--fh 2 3 4 5 6] [--qft 4 6 8 10 ...] [--out results/calibrated/scaling.json]

Every point is a run of the pinned pipeline with the calibrated settings of reproduce_table2.py (one widget for QFT;
RRE's example widgetizer and FIFO ancilla reuse for Fermi–Hubbard). Nothing is fitted or extrapolated: sizes that
were not run are absent, and the paper's values appear only where Table II prints them. Larger sizes (FH 8×8 and
up, QFT N ≥ 500) are for the larger machine; pass them explicitly there.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import platform
import sys
import time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
KEYS = ["input_logical_qubits", "num_logical_qubits_per_busrail", "distance", "t_count", "N", "num_widget_steps",
        "num_t_factories_per_module", "total_num_modules", "num_alloc_physical_qubits_per_module",
        "total_ft_algorithm_time_sec", "total_consump_ops_sec", "total_handover_time_sec",
        "total_graph_prep_delay_sec", "total_t_distill_delay_sec", "total_ft_energy_kWh"]
SECTION = {"fh": "fermi_hubbard", "qft": "qft"}


def main(argv=None) -> int:
    import compare
    import fh
    from reproduce_table2 import CONFIG, ONE_WIDGET
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fh", nargs="*", type=int, default=[2, 3, 4, 5, 6])
    ap.add_argument("--qft", nargs="*", type=int, default=[4, 6, 8, 10, 12, 16, 20, 25, 32, 40, 50, 64, 80, 100])
    ap.add_argument("--out", default=str(HERE / "results" / "calibrated" / "scaling.json"))
    args = ap.parse_args(argv)
    table = yaml.safe_load((HERE / "paper_v3_table2.yaml").read_text())
    out = {"note": "actual runs only; paper values where Table II prints them", "machine": platform.machine(),
           "config": CONFIG.name, "series": {}}
    for model, sizes, mg, mq, qm in (("qft", args.qft, *ONE_WIDGET, "simple"), ("fh", args.fh, 10000, 100, "greedy-fifo")):
        pts = []
        for n in sizes:
            t0 = time.time()
            with contextlib.redirect_stdout(io.StringIO()):
                r = fh.run(n, "random", 0, CONFIG, [], max_gates=mg, max_q=mq, qubit_manager=qm, model=model,
                           label="calibrated scaling")
            row = {"n": n, "label": r["instance"]["lattice"], "wall_seconds": round(time.time() - t0, 1),
                   "rre": {k: r["rre"].get(k) for k in KEYS},
                   "table2": {k: get(r["rre"]) for k, (get, _) in compare.MAPPING.items()}}
            paper = (table.get(SECTION[model]) or {}).get(r["instance"]["lattice"])
            if paper:
                row["paper"] = {k: float(v) for k, v in paper.items() if k != "printed"}
            pts.append(row)
            print(model, n, row["table2"]["time_s"], row["table2"]["phys_qubits"], row["wall_seconds"], flush=True)
        out["series"][model] = {"settings": {"max_gates": mg, "max_q": mq, "qubit_manager": qm}, "points": pts}
    out["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
