"""
fh.py — Fermi–Hubbard resource estimates with the paper's own pipeline (Saadatmand et al., arXiv:2406.06015v3).

    python experiments/rre/fh.py --n 2 [--phases random|optimization] [--seed 0]
                                 [--config experiments/rre/config_paper_v3.yaml] [--set key=value ...]
                                 [--out experiments/rre/results/fh_2x2.json]

Steps, following §III.2.2–III.3 and §II.4 of the paper:
  1. pyLIQTR 1.3.3: FermiHubbard instance on an N×N square lattice (J = 1, U = 2, t = 1), FermiHubbardSquare
     block encoding, QSVT dynamics with ε_qsp = 0.025 and random phase angles (the paper's choice).
  2. RRE widgetization (CirqWidgetizer with small_enough_pyliqtr_re(10000, 100), as in RRE's examples; the paper does
     not state them), transpilation to Clifford+T+Rz, Cabaliser graph-state compilation, Substrate Scheduler,
     and RRE's fault-tolerant estimate (estimation_pipeline, est_method="cabaliser").
Writes every RRE output for the instance plus provenance to JSON. Needs the RRE environment (environment.sh).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as md
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent

# The paper's instance (Eq. 25 and §III.2.2): J = 1, J' = h_z = μ = 0, U = 2, t = 1; ε_qsp from Eq. 27.
J, U, T_EVOLVE, EPS_QSP = 1.0, 2.0, 1.0, 0.025
WIDGET_MAX_GATES, WIDGET_MAX_Q = 10000, 100   # RRE examples/widgetization_example.py (not stated in the paper)


def fh_circuit(n: int, phases: str, seed: int):
    import numpy as np
    from pyLIQTR.BlockEncodings.getEncoding import VALID_ENCODINGS, getEncoding
    from pyLIQTR.ProblemInstances.getInstance import getInstance
    from pyLIQTR.clam.lattice_definitions import SquareLattice
    from pyLIQTR.qubitization.qsvt_dynamics import qsvt_dynamics, simulation_phases

    np.random.seed(seed)
    # pyLIQTR's FermiHubbard writes the hopping term as +J Σ c†c (RRE's example passes J = -1.0), so J = -1 here
    # gives the paper's H = -J Σ c†c with J = 1.
    model = getInstance("FermiHubbard", shape=(n, n), J=-J, U=U, cell=SquareLattice)
    ph = simulation_phases(times=T_EVOLVE * model.alpha, eps=EPS_QSP, precompute=False, phase_algorithm=phases)
    gate = qsvt_dynamics(encoding=getEncoding(VALID_ENCODINGS.FermiHubbardSquare), instance=model, phase_sets=ph)
    info = {"alpha": float(model.alpha), "num_phases": [int(p.num_phases) for p in ph],
            "tau": T_EVOLVE * float(model.alpha)}
    return gate.circuit, info


def decomposition_context(qubit_manager: str):
    """How decompositions allocate ancillas. The paper does not say; RRE's default is a fresh qubit per ancilla."""
    import cirq
    if qubit_manager == "simple":
        return None
    if qubit_manager == "greedy":
        return cirq.DecompositionContext(cirq.GreedyQubitManager(prefix="_anc", maximize_reuse=True))
    raise ValueError(qubit_manager)


def widgetize(circuit, name: str, max_gates: int = WIDGET_MAX_GATES, max_q: int = WIDGET_MAX_Q,
              context=None) -> dict:
    import rigetti_resource_estimation.gs_equivalence as gseq
    from rigetti_resource_estimation import widgetization

    mapper = gseq.GraphStateEquivalenceMapper()   # its default labellers (SUPPORTED_GATES)
    w = widgetization.CirqWidgetizer(small_enough_fn=widgetization.small_enough_pyliqtr_re(
        max_gates=max_gates, max_q=max_q), gs_equiv_mapper=mapper, decomp_context=context)
    res = w.widgetize(circuit)
    ws = res.widgets_and_stitches
    keys = res._leaf_ids_to_widget_keys
    first = keys[res.ordered_leaf_node_ids[0][0]]
    return {
        "widgets": {k: (res.widgets[k], ws["widgets"][k]) for k in res.widgets},
        "stitches": ws["stitches"], "first_widget": first, "circuit_name": name, "compiler_tag_table": {},
        "input_qubits": len(circuit.all_qubits()), "init_t_count": None, "init_rz_count": None,
        "init_clifford_count": None,
    }


def _merge(base: dict, over: dict) -> dict:
    for k, v in over.items():
        base[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return base


def load_params(path: Path, overrides: list[str]) -> dict:
    """RRE's default params.yaml, the paper's overlay (path), then key=value overrides."""
    from rigetti_resource_estimation import load_yaml_file
    params = _merge(load_yaml_file(), yaml.safe_load(path.read_text()) or {})
    for item in overrides:
        key, _, value = item.partition("=")
        node = params
        parts = key.split(".")
        for p in parts[:-1]:
            node = node[p]
        node[parts[-1]] = yaml.safe_load(value)
    return params


def _git(path: Path) -> str:
    p = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True)
    return p.stdout.strip()


def run(n: int, phases: str, seed: int, params_path: Path, overrides: list[str],
        max_gates: int = WIDGET_MAX_GATES, max_q: int = WIDGET_MAX_Q, qubit_manager: str = "simple") -> dict:
    from rigetti_resource_estimation import Configuration
    from rigetti_resource_estimation.estimation_pipeline import estimation_pipeline
    import pandas as pd

    t0 = time.time()
    circuit, info = fh_circuit(n, phases, seed)
    t_circ = time.time() - t0
    name = f"fh{n}x{n}_{phases}_s{seed}"
    context = decomposition_context(qubit_manager)
    wdict = widgetize(circuit, name, max_gates, max_q, context)
    t_widget = time.time() - t0 - t_circ
    params = load_params(params_path, overrides)
    with tempfile.TemporaryDirectory() as tmp:
        csv = Path(tmp) / "out.csv"
        cwd = os.getcwd()
        os.chdir(tmp)                      # RRE writes output/<name>/ relative to the working directory
        try:
            estimation_pipeline(widgetized_circ_dict=wdict, output_csv=str(csv), est_method="cabaliser",
                                graph_state_opt="save", config=Configuration(params),
                                decomp_context=decomposition_context(qubit_manager))
        finally:
            os.chdir(cwd)
        row = pd.read_csv(csv).iloc[-1].to_dict()
    clean = {k: (v.item() if hasattr(v, "item") else v) for k, v in row.items()}
    rre = Path(md.distribution("rigetti-resource-estimation").locate_file("")).resolve()
    return {
        "instance": {"model": "FermiHubbard", "lattice": f"{n}x{n}", "n": n, "J": J, "U": U, "t": T_EVOLVE,
                     "eps_qsp": EPS_QSP, "encoding": "FermiHubbardSquare", "phases": phases, "seed": seed, **info,
                     "widgetizer": {"max_gates": max_gates, "max_q": max_q, "qubit_manager": qubit_manager,
                                    "n_distinct_widgets": len(wdict["widgets"]),
                                    "n_widgets": int(sum(c for _, c in wdict["widgets"].values()))}},
        "rre": clean,
        "config": {"file": params_path.name, "overrides": overrides,
                   "sha256": hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()},
        "provenance": {"python": platform.python_version(), "machine": platform.machine(),
                       "rre": md.version("rigetti-resource-estimation"), "pyLIQTR": md.version("pyLIQTR"),
                       "cirq": md.version("cirq-core"), "rre_commit": os.environ.get("RRE_COMMIT") or _git(rre),
                       "seconds": {"circuit": round(t_circ, 1), "widgetize": round(t_widget, 1),
                                   "total": round(time.time() - t0, 1)},
                       "finished": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--phases", default="random", choices=["random", "optimization"])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--config", default=str(HERE / "config_paper_v3.yaml"))
    ap.add_argument("--set", action="append", default=[], help="override a parameter, e.g. target_p_algo=0.05")
    ap.add_argument("--widget-max-gates", type=int, default=WIDGET_MAX_GATES)
    ap.add_argument("--widget-max-q", type=int, default=WIDGET_MAX_Q)
    ap.add_argument("--qubit-manager", default="simple", choices=["simple", "greedy"])
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    result = run(args.n, args.phases, args.seed, Path(args.config), args.set, args.widget_max_gates, args.widget_max_q,
                 args.qubit_manager)
    text = json.dumps(result, indent=1, default=str)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
