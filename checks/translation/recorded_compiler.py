"""
translation/recorded_compiler — a compiler outside the main environment produced graphs that implement their circuits.

What it checks
    That the graph states a recorded compiler (Cabaliser) built from the small Trotter circuits map every input
    state to the circuit's output state. Without this, that compiler's counts could be counts of a wrongly
    translated circuit (for example a wrong qubit order or angle in its adapter).

How it works
    The compiler runs in its own environment, so experiments/compilers/run.py does the work and records it in
    experiments/compilers/results/<compiler>.json; this test reads the record.
    1. The circuit, transpiled to Clifford + Rz, is compiled by the compiler; each non-Clifford Rz gets its own
       tag with its own angle (src/mbqc_verify/compilers/cabaliser.py).
    2. The compiled graph is simulated as a statevector with the semantics of Cabaliser's own local simulator
       (checked against it on small widgets): inputs teleported in, X measurements post-selected on +.
    3. It is compared with the circuit's unitary on every computational basis input and on random inputs; the
       record keeps the worst fidelity of each instance, and this test requires each to be 1 within atol.

Parameters
    compiler    the recorded compiler, e.g. cabaliser
    atol        tolerance on 1 − fidelity (default 1e-8)

Passes when
    Every recorded instance has worst fidelity ≥ 1 − atol.

Fails when
    Some instance falls short (refuted), or there is no record or it holds no translation runs (error).

Grants
    bounded: those instances, on the post-selected branch, up to floating point.

Limits
    Only instances whose inputs and graph vertices fit in one statevector are simulated (the Trotter ones);
    the QSVT and GQSP graphs have hundreds of vertices.

Example
    - test: translation/recorded_compiler
      params: {compiler: cabaliser, atol: 1.0e-9}
"""

from __future__ import annotations

import json

from checks._framework import Result
from checks._shared.grids import record_path

PARAMS = {"compiler": {"enum": ["cabaliser"]}, "atol": {"type": "number"}}
REQUIRED = ["compiler"]


def run(node, params, ctx):
    compiler, atol = params["compiler"], float(params.get("atol", 1e-8))
    path = record_path(compiler)
    if not path.exists():
        return Result("error", summary=f"no record for {compiler}: run experiments/compilers/run.py --compiler {compiler}")
    rec = json.loads(path.read_text(encoding="utf-8"))
    rows = rec.get("translation", [])
    if not rows:
        return Result("error", summary=f"{path.name} records no translation runs")
    label = lambda r: f"{r['method']} n={r['n']} r={r['r']} ({r['vertices']} vertices, {r['inputs']} inputs)"
    bad = [r for r in rows if r["worst_fidelity"] < 1 - atol]
    domain = f"{rec['label']}, instances: " + "; ".join(label(r) for r in rows)
    ev = {"record": path.name, "versions": rec.get("versions"), "rows": rows, "atol": atol}
    if bad:
        return Result("fail", "refuted", domain, summary=f"graph state != circuit for {label(bad[0])} "
                                                         f"(fidelity {bad[0]['worst_fidelity']:.6f})", evidence=ev)
    worst = min(r["worst_fidelity"] for r in rows)
    return Result("pass", "bounded", domain, summary=f"{len(rows)} instances match on every input; worst "
                                                     f"fidelity {worst:.12f} (post-selected branch)", evidence=ev)
