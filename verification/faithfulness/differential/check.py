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
    gates: true                             instead compare the J/CZ streams themselves: Lean's
                                            `gatesToJcz` (lean/MBQC/Defs/GraphixGates.lean) against
                                            Graphix's `instructions_to_jcz`, token for token, for every
                                            gate kind on several qubit orders and for the whole
                                            transpiled circuit of each instance
"""

from __future__ import annotations

import numpy as np
from graphix import instruction as gi
from graphix.transpiler import Circuit, instructions_to_jcz

from mbqc_verify.compile.qiskit_to_mbqc import pattern_stats, to_graphix_circuit
from mbqc_verify.hamsim.analysis import generic_circuit
from verification.base import Check, CheckResult, register
from verification.truth.lean.leanrun import LeanUnavailable, run_counts, run_lines
from verification.truth.scaling.grids import grid


def jcz_tokens(instructions) -> list[str]:
    """Graphix's J/CZ stream as `J:q` / `C:a:b` tokens (global phases dropped)."""
    toks = []
    for ins in instructions_to_jcz(instructions):
        kind = ins.kind.name
        if kind == "J":
            toks.append(f"J:{ins.target}")
        elif kind == "CZ":
            a, b = ins.targets
            toks.append(f"C:{a}:{b}")
        elif kind != "GPHASE":
            raise ValueError(f"unexpected instruction {kind} in the J/CZ stream")
    return toks


def gate_token(ins) -> str:
    """A Graphix instruction as the Lean `G` token (argument order of the Lean constructor)."""
    k = ins.kind.name
    if k in ("CNOT", "RZZ"):
        return f"{k.lower()}:{ins.control}:{ins.target}"
    if k == "CZ":
        return f"cz:{ins.targets[0]}:{ins.targets[1]}"
    if k == "CCX":
        return f"ccx:{ins.controls[0]}:{ins.controls[1]}:{ins.target}"
    if k in ("H", "X", "RX", "RY", "RZ", "U"):
        return f"{k.lower()}:{ins.target}"
    raise ValueError(f"gate {k} is not in the Lean model (MBQC.Defs.Gate)")


def single_gates() -> list[tuple[str, list]]:
    """Every gate kind of the Lean model, on several qubit orders, with generic angles."""
    a, b, c = 0.37, -1.21, 2.05
    out = []
    for p, q in ((0, 1), (1, 0), (2, 0), (1, 3)):
        out += [(f"cnot {p},{q}", [gi.CNOT(target=q, control=p)]), (f"cz {p},{q}", [gi.CZ(targets=(p, q))]),
                (f"rzz {p},{q}", [gi.RZZ(target=q, control=p, angle=a)])]
    for p, q, r in ((0, 1, 2), (2, 0, 1), (1, 2, 0), (3, 0, 2)):
        out.append((f"ccx {p},{q},{r}", [gi.CCX(target=r, controls=(p, q))]))
    for q in (0, 2):
        out += [(f"h {q}", [gi.H(target=q)]), (f"x {q}", [gi.X(target=q)]), (f"rx {q}", [gi.RX(target=q, angle=a)]),
                (f"ry {q}", [gi.RY(target=q, angle=b)]), (f"rz {q}", [gi.RZ(target=q, angle=c)]),
                (f"u {q}", [gi.U(target=q, theta=a, phi=b, lambda_=c)])]
    return out


def gate_streams(params, ctx) -> CheckResult:
    cases = single_gates()
    pts = [(i["method"], i["n"], i["k"]) for i in params.get("instances", [])]
    for m, n, k in pts:
        hc = generic_circuit(m, n, k, np.random.default_rng(1000 * n + k))
        cases.append((f"{m} n={n} k={k}", list(to_graphix_circuit(hc.circuit).instruction)))
    graphix = [jcz_tokens(ins) for _, ins in cases]
    try:
        lean = run_lines(ctx, ["G " + " ".join(gate_token(i) for i in ins) for _, ins in cases])
    except LeanUnavailable as e:
        return CheckResult("error", summary=str(e))
    rows, bad = [], []
    for (name, ins), gx, lx in zip(cases, graphix, lean):
        lx = lx.split()
        rows.append({"case": name, "gates": len(ins), "tokens": len(gx), "agree": gx == lx})
        if gx != lx:
            first = next((i for i, (u, v) in enumerate(zip(gx, lx)) if u != v), min(len(gx), len(lx)))
            rows[-1] |= {"first_difference": first, "graphix": gx[first:first + 6], "lean": lx[first:first + 6]}
            bad.append(rows[-1])
    ev = {"rows": rows}
    if bad:
        b = bad[0]
        return CheckResult("fail", summary=f"{len(bad)} of {len(rows)} J/CZ streams differ (first: {b['case']} at "
                                           f"token {b['first_difference']})", evidence=ev)
    return CheckResult("pass", summary=f"Lean's gate decompositions reproduce Graphix's J/CZ stream token for token on "
                                       f"{len(rows) - len(pts)} single gates and {len(pts)} whole circuits",
                       evidence=ev)


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
        if params.get("gates"):
            return gate_streams(params, ctx)
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
