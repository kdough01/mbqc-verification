"""
scaling/gate_counts — the transpiled circuit has an exact bilinear number of gates of one kind.

What it checks
    That the circuit Qiskit's transpiler produces (level 1, Graphix's gate set) has (a n + b) k + c n + e
    gates of the given kind at every point of the method's grid. These are the facts the Lean proofs of the
    unoptimized formulas take on trust (lean/MBQC/Assumptions/HamSimGates.lean), so this test is their
    evidence.

How it works
    1. Builds and transpiles the circuit for each (n, k) of the grid, held-out points included.
    2. Counts its Graphix instructions of the kind (a gate outside Lean's model, MBQC.Defs.Gate, is an error).
    3. Compares the count with the formula exactly.

Parameters
    method      trotter2 | qsvt | gqsp
    gate        cnot | cz | rzz | ccx | h | x | rx | ry | rz | u
    coef        [a, b, c, e]

Passes when
    The formula is exact on every grid point.

Fails when
    Any count differs; the first mismatch is the counterexample.

Grants
    empirical on the grid.

Example
    - test: scaling/gate_counts
      params: {method: qsvt, gate: cnot, coef: [75, -36, -3, 12]}
"""

from __future__ import annotations

from checks._shared.grids import gate_counts

from ._compare import evidence, formula_result

PARAMS = {
    "method": {"enum": ["trotter2", "qsvt", "gqsp"]},
    "gate": {"enum": ["cnot", "cz", "rzz", "ccx", "h", "x", "rx", "ry", "rz", "u"]},
    "coef": {"type": "array", "minItems": 4, "maxItems": 4, "items": {"type": ["integer", "number", "string"]}},
}
REQUIRED = ["method", "gate", "coef"]


def run(node, params, ctx):
    method, q = params["method"], f"gate:{params['gate']}"
    data = gate_counts(method, ctx.quick, ctx.cache)
    return formula_result(method, q, params["coef"], data, ctx.quick, evidence(method, q, data, ctx.quick))
