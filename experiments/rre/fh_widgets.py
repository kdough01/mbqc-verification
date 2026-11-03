"""
fh_widgets.py — Fermi–Hubbard runtime against widget granularity, with the calibrated configuration.

    python experiments/rre/fh_widgets.py [--out results/calibrated/fh_widgets.json]

With the configuration that reproduces the QFT rows, Fermi–Hubbard runtimes come out 4–5× below Table II. Runtime
there is dominated by inter-module handover, paid once per widget step, so it depends on how finely the circuit is
cut into widgets — a setting the paper does not state. This runs the actual pipeline at each granularity the public
widgetizer produces (pyLIQTR's circuit structure makes the levels discrete) and records the steps, the graph memory
(bus patches) and the runtime against the paper. Failures are recorded.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
LEVELS = {2: [(10000, 100), (2500, 100)], 4: [(10000, 100), (10000, 40), (1500, 100), (10000, 30)]}


def main(argv=None) -> int:
    import compare
    import fh
    from reproduce_table2 import CONFIG
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(HERE / "results" / "calibrated" / "fh_widgets.json"))
    args = ap.parse_args(argv)
    rows = []
    for n, levels in LEVELS.items():
        for mg, mq in levels:
            t0 = time.time()
            row = {"lattice": f"{n}x{n}", "max_gates": mg, "max_q": mq}
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    r = fh.run(n, "random", 0, CONFIG, [], max_gates=mg, max_q=mq, qubit_manager="greedy-fifo",
                               label=f"widgets {mg}/{mq}")
                c = compare.compare(r)
                x = r["rre"]
                row.update({"distinct_widgets": r["instance"]["widgetizer"]["n_distinct_widgets"],
                            "widget_steps": x["num_widget_steps"], "distance": x["distance"], "t_count": x["t_count"],
                            "graph_memory": x["num_logical_qubits_per_busrail"],
                            "handover_s": x["total_handover_time_sec"], "consumption_s": x["total_consump_ops_sec"],
                            "ratios": {k: v["ratio"] for k, v in c["quantities"].items()},
                            "matched": c["matched"]})
            except Exception as e:
                row["error"] = f"{type(e).__name__}: {e}"[:200]
            row["steps_text"] = (f'{row["widget_steps"]:,} steps' if "widget_steps" in row
                                 else f"≤ {mg:,} gates: widgetizer fails")
            row["wall_seconds"] = round(time.time() - t0, 1)
            rows.append(row)
            print(row.get("error") or (row["lattice"], mg, mq, row["widget_steps"], row["ratios"]["time_s"]), flush=True)
    Path(args.out).write_text(json.dumps({"rows": rows}, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
