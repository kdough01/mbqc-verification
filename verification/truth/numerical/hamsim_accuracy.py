"""
hamsim_accuracy.py — Layer A: does the theory's repetition count reach accuracy eps?

For every (method, n, t, eps): take the repetitions the imported bound gives,
build the circuit (or the Trotter product), and compare with the exact e^{-iHt}
in spectral norm. Moved here from ham_sim.py check_accuracy().
"""

from __future__ import annotations

from scipy.linalg import expm

from mbqc_verify.hamsim.analysis import (build, op_norm, postselected_block, product_formula,
                                         trotter_steps)
from mbqc_verify.hamsim.circuits import IsingChain, trotter_circuit

METHODS = ("trotter1", "trotter2", "qsvt", "gqsp")


def accuracy_domain(quick: bool) -> dict:
    return dict(ns=(2,) if quick else (2, 3), ts=(0.5, 2.0),
                epsilons=(1e-2, 1e-4) if quick else (1e-2, 1e-3, 1e-5))


def check_accuracy(ns, ts, epsilons, methods=METHODS) -> list[dict]:
    rows = []
    for n in ns:
        H = IsingChain.random(n, seed=n)
        for t in ts:
            exact = expm(-1j * H.matrix() * t)
            for eps in epsilons:
                for method in methods:
                    if method.startswith("trotter"):
                        order = int(method[-1])
                        r = trotter_steps(H, t, eps, order)
                        err = op_norm(product_formula(H, t, r, order) - exact)
                        reps = r
                    else:
                        hc = build(method, H, t, eps)
                        err = op_norm(postselected_block(hc) - exact)
                        reps = hc.calls
                    rows.append(dict(method=method, n=n, t=t, eps=eps, reps=reps, err=err, ok=bool(err <= eps)))
    return rows


def accuracy_rows(quick: bool, cache: dict) -> list[dict]:
    key = ("accuracy", quick)
    if key not in cache:
        cache[key] = check_accuracy(**accuracy_domain(quick))
    return cache[key]


def check_trotter_circuit_matches_formula(ns=(2, 3), rs=(1, 2, 5), t=0.7) -> float:
    """Layer A uses product_formula() for speed; confirm the circuit implements it."""
    worst = 0.0
    for n in ns:
        H = IsingChain.random(n, seed=n)
        for r in rs:
            for order in (1, 2):
                hc = trotter_circuit(H, t, r, order)
                worst = max(worst, op_norm(postselected_block(hc) - product_formula(H, t, r, order)))
    return worst
