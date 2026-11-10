"""
numerical/trotter_circuit — the Trotter circuit implements the product formula it stands for.

What it checks
    That the Qiskit circuit built for a Trotter product (first and second order) equals the product formula
    computed directly from matrices. numerical/hamsim_accuracy uses the matrix product for speed; this test is
    why that is safe.

How it works
    1. For n in {2, 3}, builds a random Ising chain (seed n).
    2. For r in {1, 2, 5} and order 1 and 2, at t = 0.7, builds the Trotter circuit and takes its
       post-selected block.
    3. Takes the largest spectral-norm difference from the product formula over all cases.

Parameters
    tol         the largest allowed difference (default 1e-10)

Passes when
    The largest difference is at most tol.

Fails when
    Some case differs by more than tol.

Grants
    empirical on the cases listed.

Example
    - test: numerical/trotter_circuit
      params: {tol: 1.0e-10}
"""

from __future__ import annotations

from checks._framework import Result

from ._accuracy import check_trotter_circuit_matches_formula

PARAMS = {"tol": {"type": "number"}}
REQUIRED = []


def run(node, params, ctx):
    worst = check_trotter_circuit_matches_formula()
    tol = float(params.get("tol", 1e-10))
    ok = worst <= tol
    return Result("pass" if ok else "fail", "empirical" if ok else "refuted",
                  "n in [2, 3], r in [1, 2, 5], order 1 and 2, t = 0.7",
                  summary=f"max |circuit - product formula| = {worst:.1e} (tol {tol:.0e})",
                  evidence={"max_deviation": worst, "tol": tol})
