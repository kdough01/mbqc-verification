"""
phases.py — does choosing random QSP phases (the paper's choice, §III.3) give a conservative resource estimate?

    python experiments/rre/phases.py --n 2 4 --out experiments/rre/results/phases.json

The paper: "The correct number of phase angles is used in the circuits, but their numerical values are random.
This provides a conservative overestimate of the resource estimations". This builds the same QSVT circuit twice,
with pyLIQTR's random phases and with its optimized (accurate) phases, and compares the number of phases and the
logical gate counts (pyLIQTR estimate_resources, and RRE's own transpilation counts).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def counts(n: int, phases: str) -> dict:
    from pyLIQTR.utils.resource_analysis import estimate_resources
    import fh
    circuit, info = fh.fh_circuit(n, phases, seed=0)
    r = estimate_resources(circuit)
    return {"num_phases": info["num_phases"], "logical_qubits": int(r["LogicalQubits"]), "T": int(r["T"]),
            "Clifford": int(r["Clifford"])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, nargs="+", default=[2, 4])
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    rows = {}
    for n in args.n:
        rnd, opt = counts(n, "random"), counts(n, "optimization")
        rows[f"{n}x{n}"] = {"random": rnd, "optimization": opt,
                            "random_minus_optimized_T": rnd["T"] - opt["T"],
                            "random_is_conservative": rnd["T"] >= opt["T"] and rnd["Clifford"] >= opt["Clifford"]}
    text = json.dumps({"claim": "random phases give a conservative overestimate (§III.3)", "instances": rows}, indent=1)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
