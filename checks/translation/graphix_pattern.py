"""
translation/graphix_pattern — the Graphix pattern compiled from a circuit equals the circuit, per instance.

What it checks
    That for each listed instance, the MBQC pattern the Graphix pipeline compiles from the circuit implements
    the same operation as the circuit. Instead of proving the compiler correct in general, this checks each
    output (translation validation).

How it works
    1. Builds the circuit of each instance: a random Ising chain (seed) and the method's circuit for time t
       (r Trotter steps, or accuracy eps for QSVT and GQSP).
    2. Compiles it with Graphix (src/mbqc_verify/compilers/graphix.py), unoptimized or optimized.
    3. Simulates pattern and circuit on random input states with sampled measurement branches and takes the
       worst |overlap| (verify in the same file); it must be 1 within atol.

Parameters
    instances   list of {method: trotter2 | qsvt | gqsp, optimize: bool, n, seed, t,
                r (trotter2) or eps (qsvt, gqsp)}
    atol        tolerance on |overlap| (default 1e-8)

Passes when
    Every instance matches on every sampled input.

Fails when
    Some instance's pattern differs from its circuit; it is recorded.

Grants
    bounded: a check of those instances only, up to floating-point simulation.

Limits
    The optimized QSVT and GQSP patterns keep about 100 qubits alive at once and cannot be simulated, so only
    unoptimized ones are listed for those methods.

Example
    - test: translation/graphix_pattern
      params: {instances: [{method: trotter2, optimize: true, n: 2, seed: 2, t: 1.0, r: 2}]}
"""

from __future__ import annotations

from checks._framework import Result
from mbqc_verify.compilers.graphix import qiskit_to_pattern, verify
from mbqc_verify.hamsim.analysis import build
from mbqc_verify.hamsim.circuits import IsingChain, trotter_circuit

PARAMS = {
    "instances": {"type": "array", "minItems": 1, "items": {
        "type": "object", "required": ["method", "optimize", "n"], "additionalProperties": False,
        "properties": {"method": {"enum": ["trotter2", "qsvt", "gqsp"]}, "optimize": {"type": "boolean"},
                       "n": {"type": "integer"}, "seed": {"type": "integer"}, "t": {"type": "number"},
                       "r": {"type": "integer"}, "eps": {"type": "number"}}}},
    "atol": {"type": "number"},
}
REQUIRED = ["instances"]


def _circuit(inst: dict):
    H = IsingChain.random(inst["n"], seed=inst.get("seed", inst["n"]))
    if inst["method"] == "trotter2":
        return trotter_circuit(H, inst.get("t", 1.0), inst["r"], order=2)
    return build(inst["method"], H, t=inst["t"], eps=inst["eps"])


def _label(inst: dict, calls: int) -> str:
    rep = f"r={inst['r']}" if inst["method"] == "trotter2" else f"{calls} calls"
    return f"{inst['method']} n={inst['n']} {rep} ({'optimized' if inst['optimize'] else 'unoptimized'})"


def run(node, params, ctx):
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
        return Result("fail", "refuted", domain, summary=f"pattern != circuit for {failures[0]}", evidence={"rows": rows})
    worst = min(r["overlap"] for r in rows)
    return Result("pass", "bounded", domain, summary=f"{len(rows)} instances match; worst |overlap| = {worst:.12f}",
                  evidence={"rows": rows, "atol": atol})
