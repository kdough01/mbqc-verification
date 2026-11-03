"""
calibrate.py — which unstated settings reproduce Table II? A grid of real pipeline runs, scored column by column.

    python experiments/rre/calibrate.py [--instances qft:4 qft:10 qft:25] [--out results/calibrated/calibration.json]

Every point is an actual run of the pinned pipeline (pyLIQTR → RRE widgetizer → Cabaliser → Substrate Scheduler →
RRE estimate); nothing is interpolated. The grid varies only settings the paper does not state or states
ambiguously, one value per axis per run:

  qubit_manager   ancilla allocation during decomposition: simple (fresh) | greedy (reuse, LIFO) | greedy-fifo
  target_p_algo   RRE's failure budget: 0.95 (Eq. 27 read literally) | 0.5 (RRE default) | 0.05 (p_algo = 0.95 success)
  coeffs          logical-error fit (κ, p_th): paper (0.009, 0.016, Appendix D) | rre (0.3, 0.0143, params.yaml)
  factories       T-factory table: paper (Table I) | rre (RRE's shipped table)
  gate_ns         characteristic gate time t: 200 (RRE default) | 50 (RRE demo)
  widgets         one widget for the whole circuit | RRE's example widgetizer (≤ 10,000 gates, ≤ 100 qubits)

QFT instances (cirq.qft: no random phases, no ancillas) pin the configuration down without circuit ambiguity; the
point that reproduces them is then used unchanged for Fermi–Hubbard and Ising (reproduce_table2.py). Writes every
run's Table II comparison (compare.MAPPING) and key RRE outputs; a run that fails is recorded with its error.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import io
import itertools
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

AXES = {
    "qubit_manager": ["simple", "greedy", "greedy-fifo"],
    "target_p_algo": [0.95, 0.5, 0.05],
    "coeffs": ["paper", "rre"],
    "factories": ["paper", "rre"],
    "gate_ns": [200, 50],
    "widgets": ["one", "rre-example"],
}
WIDGETS = {"one": (10**9, 10**4), "rre-example": (10000, 100)}
KEYS = ["distance", "input_logical_qubits", "num_logical_qubits_per_busrail", "num_t_factories_per_module",
        "dist_widget_name", "t_count", "total_allocated_physical_qubits", "num_alloc_physical_qubits_per_module",
        "total_num_modules", "total_ft_algorithm_time_sec", "total_consump_ops_sec", "total_handover_time_sec",
        "total_graph_prep_delay_sec", "total_t_distill_delay_sec", "num_widget_steps"]


def params_for(point: dict) -> dict:
    import fh
    from rigetti_resource_estimation import load_yaml_file
    params = fh.load_params(HERE / "config_paper_v3.yaml", [])
    rre = load_yaml_file()
    params["target_p_algo"] = point["target_p_algo"]
    params["ftqc"]["qcycle_char_timescale_ns"] = point["gate_ns"]
    if point["coeffs"] == "rre":
        params["error_scaling_coeffs"] = copy.deepcopy(rre["error_scaling_coeffs"])
    if point["factories"] == "rre":
        params["distill_widget_table"] = copy.deepcopy(rre["distill_widget_table"])
    return params


def label_of(point: dict) -> str:
    return ",".join(f"{k}={point[k]}" for k in AXES)


def run_point(model: str, n: int, point: dict) -> dict:
    import compare
    import fh
    t0 = time.time()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            mg, mq = WIDGETS[point["widgets"]]
            r = fh.run(n, "random", 0, HERE / "config_paper_v3.yaml", [], max_gates=mg, max_q=mq,
                       qubit_manager=point["qubit_manager"], model=model, params=params_for(point),
                       label=label_of(point))
        c = compare.compare(r)
        return {"point": point, "instance": f"{model}:{n}", "lattice": r["instance"]["lattice"],
                "matched": c["matched"], "quantities": {k: {"ours": v["ours"], "paper": v["paper"],
                                                             "ratio": v["ratio"]} for k, v in c["quantities"].items()},
                "rre": {k: r["rre"].get(k) for k in KEYS}, "seconds": round(time.time() - t0, 1)}
    except Exception as e:   # recorded, not hidden: some settings break the pipeline for some instances
        return {"point": point, "instance": f"{model}:{n}", "error": f"{type(e).__name__}: {e}"[:300],
                "seconds": round(time.time() - t0, 1)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instances", nargs="+", default=["qft:4", "qft:10", "qft:25"])
    ap.add_argument("--out", default=str(HERE / "results" / "calibrated" / "calibration.json"))
    ap.add_argument("--fix", action="append", default=[], help="pin an axis, e.g. coeffs=paper")
    args = ap.parse_args(argv)
    axes = dict(AXES)
    for f in args.fix:
        k, _, v = f.partition("=")
        axes[k] = [type(AXES[k][0])(v)]
    if any(i.startswith("qft") for i in args.instances):
        axes["qubit_manager"] = ["simple"]      # QFT allocates no ancillas: the axis changes nothing there
    points = [dict(zip(axes, vals)) for vals in itertools.product(*axes.values())]
    out_path = Path(args.out)
    done = json.loads(out_path.read_text()) if out_path.exists() else {"runs": []}
    seen = {(r["instance"], label_of(r["point"])) for r in done["runs"]}
    for inst in args.instances:
        model, n = inst.split(":")
        for point in points:
            if (inst, label_of(point)) in seen:
                continue
            row = run_point(model, int(n), point)
            done["runs"].append(row)
            done["axes"] = AXES
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(done, indent=1, default=str) + "\n")
            print(inst, label_of(point), row.get("matched", row.get("error")), row["seconds"], flush=True)
    done["summary"] = summarize(done["runs"])
    out_path.write_text(json.dumps(done, indent=1, default=str) + "\n")
    return 0


def summarize(runs: list[dict]) -> dict:
    """Rank the grid points by how many Table II columns they reproduce (within 1%) over all instances."""
    by: dict[str, dict] = {}
    for r in runs:
        lab = label_of(r["point"])
        e = by.setdefault(lab, {"point": r["point"], "matched": 0, "columns": 0, "errors": 0, "per_instance": {}})
        if "error" in r:
            e["errors"] += 1
            continue
        e["matched"] += len(r["matched"])
        e["columns"] += len(r["quantities"])
        e["per_instance"][r["instance"]] = {k: v["ratio"] for k, v in r["quantities"].items()}
    ranked = sorted(by.values(), key=lambda e: (-e["matched"], e["errors"]))
    # For each axis value, the best score any point with that value reaches (lists follow AXES order).
    best_by_axis = {axis: [{"value": v, "best": max((e["matched"] for e in ranked if e["point"][axis] == v), default=None)}
                           for v in values] for axis, values in AXES.items()}
    return {"points": len(ranked), "columns_per_point": ranked[0]["columns"] if ranked else 0,
            "ranked": ranked, "best_by_axis": best_by_axis}


if __name__ == "__main__":
    sys.exit(main())
