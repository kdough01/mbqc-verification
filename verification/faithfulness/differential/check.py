"""
check.py — differential: do Lean's computable definitions reproduce Graphix's numbers?

Two independent implementations agreeing is strong evidence that a definition
means what we intend. For each instance, Graphix decomposes the circuit into its
J/CZ stream (`instructions_to_jcz`) and builds the unoptimized pattern; Lean's
`compileJcz` (lean/MBQC/Defs/JCZ.lean, run by the `mbqc_counts` executable)
builds its own graph from the same stream. Their N, E, M must be equal.

Node params:
    method: trotter2 | qsvt | gqsp          compare on the method's whole scaling grid
  or
    instances: [{method, n, k}, ...]        compare on the listed instances
"""

from __future__ import annotations

import numpy as np
from graphix.transpiler import instructions_to_jcz

from mbqc_verify.compile.qiskit_to_mbqc import pattern_stats, to_graphix_circuit
from mbqc_verify.hamsim.analysis import generic_circuit
from verification.base import Check, CheckResult, register
from verification.truth.lean.leanrun import LeanUnavailable, run_counts
from verification.truth.scaling.grids import grid


def stream_and_counts(method: str, n: int, k: int, cache: dict) -> tuple[str, tuple[int, int, int]]:
    """One J/CZ stream line for Lean, and Graphix's (N, E, M) of the unoptimized pattern."""
    key = ("jcz", method, n, k)
    if key not in cache:
        hc = generic_circuit(method, n, k, np.random.default_rng(1000 * n + k))
        gc = to_graphix_circuit(hc.circuit)
        toks = [str(gc.width)]
        for ins in instructions_to_jcz(gc.instruction):
            kind = ins.kind.name
            if kind == "J":
                toks.append(f"J:{ins.target}")
            elif kind == "CZ":
                a, b = ins.targets
                toks.append(f"C:{a}:{b}")
            elif kind in ("GPHASE",):
                continue
            else:
                raise ValueError(f"unexpected instruction {kind} in the J/CZ stream")
        s = pattern_stats(gc.transpile().pattern)
        cache[key] = (" ".join(toks), (s["total_nodes"], s["edges (CZ)"], s["measurements"]))
    return cache[key]


@register
class DifferentialCheck(Check):
    kind = "differential"

    def run(self, node, params, ctx):
        if "instances" in params:
            pts = [(i["method"], i["n"], i["k"]) for i in params["instances"]]
        else:
            train, holdout = grid(params["method"], ctx.quick)
            pts = [(params["method"], n, k) for n, k in train + holdout]
        data = [stream_and_counts(m, n, k, ctx.cache) for m, n, k in pts]
        try:
            lean = run_counts(ctx, [line for line, _ in data])
        except LeanUnavailable as e:
            return CheckResult("error", summary=str(e))
        rows, bad = [], []
        for (m, n, k), (_, gx), lx in zip(pts, data, lean):
            rows.append({"method": m, "n": n, "k": k, "graphix": list(gx), "lean": list(lx), "agree": gx == lx})
            if gx != lx:
                bad.append(rows[-1])
        ev = {"rows": rows}
        if bad:
            b = bad[0]
            return CheckResult("fail", summary=f"{len(bad)} of {len(rows)} instances disagree (first: {b['method']} "
                                               f"n={b['n']} k={b['k']}: Graphix {b['graphix']}, Lean {b['lean']})",
                               evidence=ev)
        return CheckResult("pass", summary=f"Lean and Graphix agree on N, E, M for all {len(rows)} instances",
                           evidence=ev)
