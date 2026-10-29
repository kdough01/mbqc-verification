"""
check.py — translation validation: does the compiled pattern equal its circuit?

Instead of proving the compiler correct in general, check each output: compile
one instance with the Graphix pipeline and compare pattern and circuit on random
input states (worst |overlap| over the states, measurement branches sampled).
Moved here from ham_sim.py check_mbqc_equivalence(). Grants `bounded`: a proof
for that instance only, up to floating-point simulation.

Node params:
    instances: list of {method: trotter2 | qsvt | gqsp, optimize: bool,
                         n: int, seed: int, t: float, r: int (trotter2) | eps: float (qsvt, gqsp)}
    atol: float (default 1e-8)

The optimized QSVT/GQSP patterns keep ~100 qubits alive at once and can't be
simulated, so only unoptimized ones are listed for those methods.

Planned (design doc, wave 3): also check the gflow certificate of each pattern.
"""

from __future__ import annotations

from mbqc_verify.compile.qiskit_to_mbqc import qiskit_to_pattern, verify
from mbqc_verify.hamsim.analysis import build
from mbqc_verify.hamsim.circuits import IsingChain, trotter_circuit
from verification.base import Check, CheckResult, register


def _circuit(inst: dict):
    H = IsingChain.random(inst["n"], seed=inst.get("seed", inst["n"]))
    if inst["method"] == "trotter2":
        return trotter_circuit(H, inst.get("t", 1.0), inst["r"], order=2)
    return build(inst["method"], H, t=inst["t"], eps=inst["eps"])


def _label(inst: dict, calls: int) -> str:
    rep = f"r={inst['r']}" if inst["method"] == "trotter2" else f"{calls} calls"
    return f"{inst['method']} n={inst['n']} {rep} ({'optimized' if inst['optimize'] else 'unoptimized'})"


@register
class TranslationCheck(Check):
    kind = "translation"

    def run(self, node, params, ctx):
        atol = float(params.get("atol", 1e-8))
        rows, failures = [], []
        for inst in params["instances"]:
            hc = _circuit(inst)
            label = _label(inst, hc.calls)
            try:
                overlap = verify(hc.circuit, qiskit_to_pattern(hc.circuit, optimize=inst["optimize"]), atol=atol)
                rows.append({"instance": label, "overlap": overlap, "ok": True})
            except AssertionError as e:
                rows.append({"instance": label, "overlap": None, "ok": False, "error": str(e)})
                failures.append(label)
        domain = "instances: " + "; ".join(r["instance"] for r in rows)
        if failures:
            return CheckResult("fail", "refuted", domain, summary=f"pattern != circuit for {failures[0]}",
                               evidence={"rows": rows})
        worst = min(r["overlap"] for r in rows)
        return CheckResult("pass", "bounded", domain,
                           summary=f"{len(rows)} instances match; worst |overlap| = {worst:.12f}",
                           evidence={"rows": rows, "atol": atol})
