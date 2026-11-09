"""
run.py — record what compilers that need their own environment produce, for the verifier's checks.

    CABALISER_PYTHON=.rre/venv/bin/python python experiments/compilers/run.py [--compiler cabaliser]

Runs in the verifier's environment; each compiler's own half runs in its environment as a subprocess
(src/mbqc_verify/compile/compilers.py). Writes experiments/compilers/results/<compiler>.json with

  counts:      N, E, M (and the compiler's extras) of every Hamiltonian-simulation circuit on the scaling grids
               (verification/truth/scaling/grids.py), the same circuits the Graphix checks compile
  translation: fidelity of the compiled graph state with the circuit on every basis input and random inputs,
               for the instances small enough to simulate

The scaling and translation checks with `compiler: <name>` read this record; re-run this after changing the
compiler, its adapter, the circuits or the grids (the checks' evidence goes stale when the record changes).
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from mbqc_verify.compile.compilers import get                       # noqa: E402
from mbqc_verify.hamsim.analysis import generic_circuit             # noqa: E402
from verification.truth.scaling.grids import GRIDS                  # noqa: E402

# Small enough for the statevector check (inputs + every graph vertex held at once)
TRANSLATION = {"cabaliser": [{"method": "trotter2", "n": 2, "r": 1}, {"method": "trotter2", "n": 2, "r": 2},
                             {"method": "trotter2", "n": 3, "r": 1}]}


def versions(name: str) -> dict:
    import qiskit
    out = {"qiskit": qiskit.__version__, "python": platform.python_version()}
    if name == "cabaliser":
        rre = ROOT / ".rre" / "rre"
        for key, path in (("rre_commit", rre), ("cabaliser_commit", rre / "external" / "cabaliser")):
            try:
                out[key] = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True,
                                          text=True, check=True).stdout.strip()
            except Exception:
                out[key] = "unknown (environment not at .rre)"
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compiler", default="cabaliser")
    ap.add_argument("--samples", type=int, default=4, help="random inputs per translation instance")
    args = ap.parse_args(argv)
    comp = get(args.compiler)
    counts = {}
    for method, (train, hold) in GRIDS.items():
        rows = {}
        for n, k in train + hold:
            t0 = time.time()
            qc = generic_circuit(method, n, k, np.random.default_rng(1000 * n + k)).circuit
            rows[f"{n},{k}"] = comp.counts(qc).as_dict()
            print(f"{method} n={n} k={k}: {rows[f'{n},{k}']} ({time.time() - t0:.1f}s)", flush=True)
        counts[method] = rows
    translation = []
    if args.compiler == "cabaliser":
        from mbqc_verify.compile.cabaliser_adapter import translate
        from mbqc_verify.hamsim.circuits import IsingChain, trotter_circuit
        for inst in TRANSLATION["cabaliser"]:
            H = IsingChain.random(inst["n"], seed=inst["n"])
            res = translate(trotter_circuit(H, 1.0, inst["r"], order=2).circuit, samples=args.samples)
            worst = min(r["fidelity"] for r in res["rows"])
            translation.append(inst | {"t": 1.0, "seed": inst["n"], "vertices": res["vertices"],
                                       "inputs": len(res["rows"]), "worst_fidelity": worst})
            print(f"translation {inst}: worst fidelity {worst:.15f} over {len(res['rows'])} inputs", flush=True)
    out = {"compiler": comp.name, "label": comp.label, "description": comp.description,
           "versions": versions(comp.name), "grids": {m: [list(p) for p in t + h] for m, (t, h) in GRIDS.items()},
           "counts": counts, "translation": translation}
    path = ROOT / "experiments" / "compilers" / "results" / f"{comp.name}.json"
    path.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
