"""
cabaliser_inputs.py — the paper's Appendix C verification, run on inputs other than |0…0⟩.

    python experiments/rre/cabaliser_inputs.py [--samples 20] [--out experiments/rre/results/cabaliser_inputs.json]

Appendix C (and RRE's tests/verify_n_validate/test_unitary_verif_cabaliser.py) compiles a small two-widget
circuit with RRE + Cabaliser, simulates the compiled graph states exactly from the all-zero input, applies the
inverse circuit, and checks for |0…0⟩. One input cannot show that the compiled widget implements the circuit on
every input. This compiles the same circuits and compares the simulated output with the circuit's own unitary
for every computational basis state and for random states (Haar-random, entangled), by fidelity.

Cabaliser's local simulator post-selects the measurement outcomes, so this checks the post-selected branch, as
the paper's protocol does; the Pauli-frame corrections of other branches are not exercised.

Two details of the published test matter on non-zero inputs: RRE's compiled output records only that a node is an
arbitrary-angle rotation (tag 77), not its angle, and the test's table maps that tag to T; and Cabaliser's
local_simulator defines Tdag = S @ T, which is T^3, not T†. Neither is visible from |0…0⟩. --table rre_test runs
the published table; --table actual (default) uses the circuit's own Rz angle and the correct T†.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np


def paper_test_circuits():
    """The two widgets of RRE's test_unitariness_verif_cabaliser_qft3toffoli3 (the paper's Appendix C example)."""
    import cirq
    qq = cirq.LineQubit.range(3)
    w0 = cirq.inverse(cirq.Circuit(
        cirq.Z(qq[0]), cirq.H(qq[1]), cirq.S(qq[2]), cirq.SWAP(qq[2], qq[1]), cirq.rz(-0.303)(qq[0]), cirq.Y(qq[1]),
        cirq.X(qq[2]), cirq.CX(qq[0], qq[1]), cirq.T(qq[1]), cirq.S(qq[2]) ** -1, cirq.Z(qq[0]), cirq.CZ(qq[0], qq[2])))
    w1 = cirq.inverse(cirq.Circuit(cirq.T(qq[2]) ** -1, cirq.CX(qq[0], qq[1]), cirq.I(qq[2])))
    return qq, [w0, w1]


def compile_widgets(qq, widgets, name: str) -> list[dict]:
    from rigetti_resource_estimation.estimation_pipeline import estimation_pipeline
    wdict = {"stitches": {(f"W{i}", f"W{i + 1}"): 1 for i in range(len(widgets) - 1)},
             "widgets": {f"W{i}": (w, 1) for i, w in enumerate(widgets)}, "first_widget": "W0",
             "compiler_tag_table": {}, "circuit_name": name, "input_qubits": len(qq),
             "init_t_count": None, "init_rz_count": None, "init_clifford_count": None}
    estimation_pipeline(widgetized_circ_dict=wdict, est_method="cabaliser", graph_state_opt="save")
    out = []
    for i in range(len(widgets)):
        path = Path("output") / name / f"{name}_W{i}_all0init_cabalizeframes.json"
        obj = json.loads(path.read_text())[0]
        obj["adjacencies"] = {int(k): v for k, v in obj["adjacencies"].items()}
        obj["consumptionschedule"] = [[{int(k): v for k, v in d.items()} for d in layer]
                                      for layer in obj["consumptionschedule"]]
        out.append(obj)
    return out


def rz_angles(widgets) -> list[float]:
    import cirq
    return sorted({round(float(op.gate.exponent) * np.pi, 12) for w in widgets for op in w.all_operations()
                   if isinstance(op.gate, cirq.Rz)})


def run(samples: int, seed: int, table_mode: str = "rre_test") -> dict:
    """table_mode: "rre_test" uses the tag table of RRE's test (it maps the arbitrary-rotation tag 77 to T);
    "actual" maps tag 77 to the circuit's own Rz angle. RRE's compiler output records only that a node is an
    arbitrary rotation (tag 77), not which angle, so a single circuit-wide table is all a check can use."""
    import cirq
    from cabaliser import local_simulator as ls
    qq, widgets = paper_test_circuits()
    angles = rz_angles(widgets)
    if table_mode == "rre_test":
        table = {0: ls.I, 31: ls.T, 77: ls.T, 333: ls.Tdag}
    elif len(angles) == 1:
        # Cabaliser's local_simulator defines Tdag = S @ T, which is T^3 = diag(1, e^{3iπ/4}), not T† = diag(1,
        # e^{-iπ/4}); "actual" uses the correct T†.
        t_dag = np.diag([1, np.exp(-1j * np.pi / 4)]).astype(np.complex128)
        table = {0: ls.I, 31: ls.T, 77: ls._Rz(angles[0]), 333: t_dag}
    else:
        raise ValueError(f"{len(angles)} distinct Rz angles share tag 77; the compiled output cannot tell them apart")
    n = len(qq)
    with tempfile.TemporaryDirectory() as tmp:
        cwd = os.getcwd()
        os.chdir(tmp)
        try:
            import contextlib, io
            with contextlib.redirect_stdout(io.StringIO()):
                compiled = compile_widgets(qq, widgets, "inputs_check")
        finally:
            os.chdir(cwd)
    U = cirq.Circuit(widgets).unitary(qubit_order=qq)
    rng = np.random.default_rng(seed)
    states = [("basis", f"|{b:0{n}b}⟩", np.eye(2 ** n)[b]) for b in range(2 ** n)]
    for k in range(samples):
        v = rng.normal(size=2 ** n) + 1j * rng.normal(size=2 ** n)
        states.append(("haar", f"random #{k}", v / np.linalg.norm(v)))
    rows = []
    for kind, label, psi in states:
        state = psi.reshape(-1, 1)
        for obj in compiled:
            state = ls.simulate_dict_as_widget(obj=obj, input_state=state, table=table)
        got = np.asarray(state).reshape(-1)
        want = U @ psi
        fid = float(abs(np.vdot(want, got)) ** 2 / (np.vdot(got, got).real or 1.0))
        rows.append({"kind": kind, "input": label, "fidelity": round(fid, 12)})
    worst = min(r["fidelity"] for r in rows)
    return {"circuits": "RRE test_unitariness_verif_cabaliser_qft3toffoli3 (paper Appendix C)",
            "table_mode": table_mode, "rz_angles": angles,
            "inputs": len(rows), "worst_fidelity": worst, "all_pass": worst > 1 - 1e-9,
            "failures": [r for r in rows if r["fidelity"] <= 1 - 1e-9][:10], "rows": rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--table", default="actual", choices=["actual", "rre_test"])
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    res = run(args.samples, args.seed, args.table)
    text = json.dumps(res, indent=1)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
