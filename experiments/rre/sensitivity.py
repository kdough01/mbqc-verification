"""
sensitivity.py — how the Table II quantities move with the settings the paper does not state.

    python experiments/rre/sensitivity.py --n 2 4 --out experiments/rre/results/sensitivity.json

Varies one unstated setting at a time from config_paper_v3.yaml: the failure budget reading of Eq. (27)
(target_p_algo 0.95 or 0.05), the characteristic gate time t (200 ns or 50 ns), ancilla allocation during
decomposition (fresh qubits or reuse), and widget size (max gates per widget).
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

VARIANTS = [
    ("baseline (config_paper_v3.yaml)", [], {}),
    ("failure budget 0.05", ["target_p_algo=0.05"], {}),
    ("gate time 50 ns", ["ftqc.qcycle_char_timescale_ns=50"], {}),
    ("ancilla reuse (greedy qubit manager)", [], {"qubit_manager": "greedy"}),
    ("widgets of at most 2000 gates", [], {"max_gates": 2000}),
]
KEYS = ["num_logical_qubits_per_busrail", "input_logical_qubits", "distance", "dist_widget_name",
        "num_t_factories_per_module", "total_allocated_physical_qubits", "num_alloc_physical_qubits_per_module",
        "total_num_modules", "total_ft_algorithm_time_sec", "total_ft_energy_kWh", "t_count", "N"]


def main(argv=None) -> int:
    import fh
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, nargs="+", default=[2, 4])
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    out = {}
    for n in args.n:
        rows = []
        for label, sets, kw in VARIANTS:
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    r = fh.run(n, "random", 0, HERE / "config_paper_v3.yaml", sets, **kw)
                rows.append({"variant": label, **{k: r["rre"][k] for k in KEYS}})
            except Exception as e:  # noqa: BLE001 - e.g. widgetization failing for small widgets
                rows.append({"variant": label, "error": f"{type(e).__name__}: {e}"[:200]})
        out[f"{n}x{n}"] = rows
    text = json.dumps(out, indent=1, default=str)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
