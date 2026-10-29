"""
grids.py — MBQC resource counts over (n, k) grids, computed once per run.

The training grid and held-out points are the ones the original harness used
(ham_sim.py GRIDS). k is the method's repetition parameter: Trotter steps r,
QSVT degree D (odd), GQSP Laurent degree d.
"""

from __future__ import annotations

from fractions import Fraction

import numpy as np

from mbqc_verify.hamsim.analysis import count, evaluate

GRIDS = {   # (training grid of (n, k), held-out points)
    "trotter2": ([(n, k) for n in (2, 3, 4, 5) for k in (1, 2, 3, 4)], [(7, 6), (9, 3)]),
    "qsvt":     ([(n, k) for n in (2, 3, 4) for k in (3, 5, 7)], [(5, 9)]),
    "gqsp":     ([(n, k) for n in (2, 3, 4) for k in (1, 2, 3)], [(5, 4)]),
}


def grid(method: str, quick: bool = False) -> tuple[list, list]:
    train, holdout = GRIDS[method]
    if quick:   # keep the two smallest n (all k) so a bilinear fit is still determined
        small_n = sorted({n for n, _ in train})[:2]
        train = [(n, k) for n, k in train if n in small_n]
    return train, holdout


def counts(method: str, optimize: bool, quick: bool, cache: dict) -> dict[tuple[int, int], dict]:
    """{(n, k): {N, E, M, space}} on the training grid plus held-out points (cached per run)."""
    key = ("counts", method, optimize, quick)
    if key not in cache:
        train, holdout = grid(method, quick)
        cache[key] = {(n, k): count(method, n, k, optimize) for n, k in train + holdout}
    return cache[key]


def domain_text(method: str, quick: bool) -> str:
    train, holdout = grid(method, quick)
    ns = sorted({n for n, _ in train})
    ks = sorted({k for _, k in train})
    return f"n in {ns}, k in {ks} (training) + held-out {holdout}"


def mismatches(coef, data: dict, quantity: str) -> list[dict]:
    """Grid points where the bilinear formula `coef` = (a, b, c, e) disagrees with the counts."""
    coef = [Fraction(str(c)) for c in coef]
    out = []
    for (n, k), row in sorted(data.items()):
        predicted = evaluate(coef, n, k)
        if predicted != row[quantity]:
            out.append({"n": n, "k": k, "count": row[quantity], "formula": str(predicted)})
    return out


def interpolate(data: dict, quantity: str, points: list[tuple[int, int]]) -> list[Fraction] | None:
    """The unique bilinear formula through 4 points (exact rational arithmetic), or None if singular."""
    import sympy as sp
    rows = [[n * k, k, n, 1] for n, k in points]
    rhs = [data[p][quantity] for p in points]
    A = sp.Matrix(rows)
    if A.det() == 0:
        return None
    sol = A.LUsolve(sp.Matrix(rhs))
    return [Fraction(int(sp.fraction(x)[0]), int(sp.fraction(x)[1])) for x in sol]


def least_squares(data: dict, quantity: str, train: list[tuple[int, int]]) -> list[str]:
    """The harness's original fit (float least squares rounded to denominators <= 12), for reference."""
    X = np.array([[n * k, k, n, 1] for n, k in train], dtype=float)
    y = np.array([data[p][quantity] for p in train], dtype=float)
    coef = np.linalg.lstsq(X, y, rcond=None)[0]
    return [str(Fraction(c).limit_denominator(12)) for c in coef]


def corners(train: list[tuple[int, int]]) -> list[tuple[int, int]]:
    ns, ks = sorted({n for n, _ in train}), sorted({k for _, k in train})
    return [(ns[0], ks[0]), (ns[0], ks[-1]), (ns[-1], ks[0]), (ns[-1], ks[-1])]
