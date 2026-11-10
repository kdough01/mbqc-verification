"""
_compare.py — the comparison every scaling test makes: a formula against counts on a method's grid.

value = (a n + b) k + c n + e with exact rational coefficients; "training" points are the grid the formula
may have been read from, "held-out" points are never used to find it. Shared by the scaling tests and
mutation/scaling_coefficients (which re-runs it with perturbed coefficients).
"""

from __future__ import annotations

from checks._framework import Result
from checks._shared.grids import domain_text, grid, least_squares, mismatches

FORMULA_TESTS = ("scaling/bilinear_formula", "scaling/gate_counts", "scaling/circuit_width")


def evidence(method: str, quantity: str, data: dict, quick: bool, **extra) -> dict:
    train, holdout = grid(method, quick)
    return {"method": method, **extra, "quantity": quantity,
            "training": [list(p) for p in train], "holdout": [list(p) for p in holdout],
            "counts": [{"n": n, "k": k, quantity: v[quantity], "space": v.get("space")} for (n, k), v in sorted(data.items())],
            "least_squares_fit": least_squares(data, quantity, train)}


def formula_result(method: str, quantity: str, coef: list, data: dict, quick: bool, ev: dict) -> Result:
    """Pass if the formula is exact on every point, else the first mismatch refutes it."""
    train, holdout = grid(method, quick)
    miss = mismatches(coef, data, quantity)
    ev["mismatches"] = miss
    if miss:
        m = miss[0]
        return Result("fail", "refuted", f"counterexample at n={m['n']}, k={m['k']}",
                      summary=f"formula misses {len(miss)} of {len(data)} counts "
                              f"(n={m['n']}, k={m['k']}: count {m['count']}, formula {m['formula']})", evidence=ev)
    return Result("pass", "empirical", domain_text(method, quick),
                  summary=f"exact on all {len(train)} training and {len(holdout)} held-out points", evidence=ev)
