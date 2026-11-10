"""
scaling/circuit_width — the transpiled circuit acts on a stated number of qubits.

What it checks
    That the circuit Qiskit's transpiler produces has (a n + b) k + c n + e qubits at every grid point
    (for example 4n + 1 for QSVT: n data qubits, ancillas for the block encoding, one signal qubit). The Lean
    proofs compile on that width, so this test checks the Lean statement models the real circuit.

How it works
    1. Builds and transpiles the circuit for each (n, k) of the grid, held-out points included.
    2. Reads its width and compares it with the formula exactly.

Parameters
    method      trotter2 | qsvt | gqsp
    coef        [a, b, c, e]

Passes when
    The width formula is exact on every grid point.

Fails when
    Any width differs; the first mismatch is the counterexample.

Grants
    empirical on the grid.

Example
    - test: scaling/circuit_width
      params: {method: qsvt, coef: [0, 0, 4, 1]}
"""

from __future__ import annotations

from checks._shared.grids import gate_counts

from ._compare import evidence, formula_result

PARAMS = {
    "method": {"enum": ["trotter2", "qsvt", "gqsp"]},
    "coef": {"type": "array", "minItems": 4, "maxItems": 4, "items": {"type": ["integer", "number", "string"]}},
}
REQUIRED = ["method", "coef"]


def run(node, params, ctx):
    method = params["method"]
    data = gate_counts(method, ctx.quick, ctx.cache)
    return formula_result(method, "width", params["coef"], data, ctx.quick, evidence(method, "width", data, ctx.quick))
