"""
run_all.py — the full Hamiltonian-simulation report (formerly ham_sim.py).

Prints every layer of the slide check and writes results/hamsim_results.json,
the input for plot_results.py. The checks themselves live under verification/
and also run through `dagtool run`, which records them as DAG evidence; this
script is the human-readable tour of the same computations.

The slide's result has three layers (see docs/hamsim.md):

  A. ACCURACY      "degree d_eps (or r_eps Trotter steps) gives error <= eps".
                   verification/truth/numerical
  B. COST FORMULAS "N, E, M = (per-repetition cost) x repetitions + setup".
                   verification/truth/scaling
  C. CONSEQUENCES  Big-O and "d >= g  =>  GQSP is cheaper".
                   verification/truth/symbolic, verification/truth/refuter

Run from the repository root:
       python experiments/hamsim/run_all.py           (about six minutes)
       python experiments/hamsim/run_all.py --quick   (smaller grids)
"""

from __future__ import annotations

import argparse
import json
import time
from fractions import Fraction
from pathlib import Path

import numpy as np

from mbqc_verify.hamsim.analysis import REP_SYMBOL, cost_at_equal_accuracy, format_formula
from mbqc_verify.hamsim.slide import SLIDE_N
from verification.truth.numerical.hamsim_accuracy import (check_accuracy,
                                                          check_trotter_circuit_matches_formula)
from verification.truth.symbolic.coeff_positivity import certificate
from verification.truth.scaling.grids import GRIDS, counts, grid

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results" / "hamsim_results.json"

MBQC_INSTANCES = [   # same instances as the original harness
    {"method": "trotter2", "optimize": False, "n": 2, "seed": 2, "t": 1.0, "r": 3},
    {"method": "trotter2", "optimize": True, "n": 2, "seed": 2, "t": 1.0, "r": 3},
    {"method": "qsvt", "optimize": False, "n": 2, "seed": 2, "t": 0.3, "eps": 0.01},
    {"method": "gqsp", "optimize": False, "n": 2, "seed": 2, "t": 0.3, "eps": 0.01},
]


def check_mbqc_equivalence() -> list[tuple[str, float]]:
    from verification.truth.translation.check import _circuit, _label
    from mbqc_verify.compile.qiskit_to_mbqc import qiskit_to_pattern, verify
    out = []
    for inst in MBQC_INSTANCES:
        hc = _circuit(inst)
        out.append((_label(inst, hc.calls), verify(hc.circuit, qiskit_to_pattern(hc.circuit, optimize=inst["optimize"]))))
    return out


def fit_bilinear(points, holdout):
    """Least-squares fit of value = a n k + b k + c n + e, rounded to denominators <= 12 (the original method)."""
    X = np.array([[n * k, k, n, 1] for n, k, _ in points], dtype=float)
    y = np.array([v for _, _, v in points], dtype=float)
    coef = np.linalg.lstsq(X, y, rcond=None)[0]
    fracs = [Fraction(c).limit_denominator(12) for c in coef]
    predict = lambda n, k: fracs[0] * n * k + fracs[1] * k + fracs[2] * n + fracs[3]
    exact = all(predict(n, k) == v for n, k, v in points + holdout)
    worst = max(abs(float(predict(n, k)) - v) for n, k, v in points + holdout)
    return fracs, exact, worst


def check_formulas(optimize: bool, quick: bool, cache: dict) -> dict:
    results = {}
    for method in GRIDS:
        train, holdout = grid(method, quick)
        data = counts(method, optimize, quick, cache)
        results[method] = {"data": {p: data[p] for p in train + holdout}}
        for q in ("N", "E", "M"):
            pts = [(n, k, data[n, k][q]) for n, k in train]
            hold = [(n, k, data[n, k][q]) for n, k in holdout]
            results[method][q] = fit_bilinear(pts, hold)
    return results


def prove_slide_claim() -> dict[str, bool]:
    return {name: all(c["certifies_positive"] for c in certificate(q))
            for name, q in (("vertices N", "N"), ("measurements M", "M"), ("executed CZs E", "E"))}


def our_claim_holds(formulas: dict, n_max: int = 50, k_max: int = 41) -> dict[str, bool]:
    out = {}
    for q in ("N", "E", "M"):
        fq, fg = formulas["qsvt"][q][0], formulas["gqsp"][q][0]
        ev = lambda f, n, k: f[0] * n * k + f[1] * k + f[2] * n + f[3]
        out[q] = all(ev(fq, n, D) > ev(fg, n, d)
                     for n in range(2, n_max + 1) for d in range(1, k_max + 1)
                     for D in range(1, k_max + 1, 2) if D >= d)
    return out


def compare_with_slide(formulas: dict) -> list[tuple]:
    rows = []
    for method in ("qsvt", "gqsp"):
        ours = tuple(formulas[method]["N"][0])
        slide = SLIDE_N[method]
        rows.append((method, slide, ours, ours[:2] == slide[:2], ours[2:] == slide[2:]))
    return rows


def main(quick: bool = False) -> None:
    t_start = time.time()
    cache: dict = {}
    line = "=" * 78

    print(line, "\nLAYER A: accuracy  (repetitions from theory -> simulate -> error <= eps?)\n" + line)
    rows = check_accuracy(ns=(2,) if quick else (2, 3), ts=(0.5, 2.0),
                          epsilons=(1e-2, 1e-4) if quick else (1e-2, 1e-3, 1e-5))
    print(f"{'method':9s} {'n':>2s} {'t':>4s} {'eps':>7s} {'repetitions':>12s} {'actual error':>13s}  ok")
    for r in rows:
        print(f"{r['method']:9s} {r['n']:2d} {r['t']:4.1f} {r['eps']:7.0e} {r['reps']:12d} {r['err']:13.2e}  {'yes' if r['ok'] else 'NO'}")
    print(f"all within eps: {all(r['ok'] for r in rows)}   (repetitions: Trotter steps; QSVT/GQSP block-encoding calls)")
    print(f"Trotter circuit == product formula: max deviation {check_trotter_circuit_matches_formula():.1e}")

    print("\nMBQC equivalence (pattern vs circuit, random input states, worst |overlap|):")
    for name, ov in check_mbqc_equivalence():
        print(f"  {name:38s} {ov:.12f}")

    formulas = {}
    for optimize in (False, True):
        label = "optimized (Pauli measurements removed)" if optimize else "unoptimized (gate-by-gate)"
        print("\n" + line, f"\nLAYER B: resource formulas, {label}\n" + line)
        res = check_formulas(optimize, quick, cache)
        for method, r in res.items():
            sym = REP_SYMBOL[method]
            print(f"{method}  ({sym} = {'Trotter steps' if sym == 'r' else 'QSVT degree, 3D calls' if sym == 'D' else 'GQSP Laurent degree, 2d calls'})")
            for q in ("N", "E", "M"):
                fr, exact, worst = r[q]
                status = "exact on all points incl. held-out" if exact else f"NOT exact (off by up to {worst:.0f})"
                print(f"   {q} = {format_formula(fr, sym):40s} {status}")
            spaces = sorted({v['space'] for v in r['data'].values()})
            print(f"   peak live qubits (max_space) over the grid: {spaces[0]} .. {spaces[-1]}")
        formulas[optimize] = res

    print("\n" + line, "\nLAYER C: consequences\n" + line)
    print("Slide's claim (its own formulas): d >= g  =>  QSVT uses more, for all n >= 2")
    for q, ok in prove_slide_claim().items():
        print(f"   {q:16s} proved: {ok}")
    for optimize in (False, True):
        tag = "optimized" if optimize else "unoptimized"
        print(f"Same claim with OUR {tag} formulas (n <= 50, degrees <= 41):",
              {q: v for q, v in our_claim_holds(formulas[optimize]).items()})

    print("\nOur vertex formulas vs the slide's  [(a n + b) x degree + (c n + e)]:")
    for optimize in (False, True):
        for method, slide, ours, same_per, same_setup in compare_with_slide(formulas[optimize]):
            fmt = lambda f: format_formula([Fraction(x) for x in f], "deg")
            print(f"  {method} {'optimized  ' if optimize else 'unoptimized'}: slide {fmt(slide):28s} ours {fmt(ours):30s}"
                  f" per-degree match: {same_per}, setup match: {same_setup}")

    for optimize in (False, True):
        tag = "optimized" if optimize else "unoptimized"
        print(f"\nVertices needed at EQUAL accuracy ({tag} formulas; Trotter = 2nd order):")
        print(f"{'n':>3s} {'t':>4s} {'eps':>7s} {'alpha':>6s} | {'r':>6s} {'D':>4s} {'d':>4s} | "
              f"{'Trotter2':>10s} {'QSVT':>10s} {'GQSP':>10s} | cheapest")
        for r in cost_at_equal_accuracy({m: formulas[optimize][m]["N"][0] for m in GRIDS}, ns=(4, 16, 64), ts=(1.0, 10.0), epsilons=(1e-2, 1e-4, 1e-8)):
            c, k = r["cost"], r["reps"]
            print(f"{r['n']:3d} {r['t']:4.0f} {r['eps']:7.0e} {r['alpha']:6.1f} | {k['trotter2']:6d} {k['qsvt']:4d} {k['gqsp']:4d} | "
                  f"{c['trotter2']:10.0f} {c['qsvt']:10.0f} {c['gqsp']:10.0f} | {r['best']}")

    save_results(RESULTS, rows, formulas, quick)
    print(f"\nsaved {RESULTS.relative_to(HERE.parents[1])} (input for plot_results.py)")
    print(f"total time {time.time() - t_start:.0f}s")


def save_results(path: Path, accuracy_rows: list[dict], formulas: dict, quick: bool = False) -> None:
    """Write everything the plots need: accuracy rows, fitted formulas, the raw counts, and provenance."""
    from dagtool.evidence import git_commit, now_utc, versions
    out = {"accuracy": [{k: (bool(v) if k == "ok" else v) for k, v in r.items()} for r in accuracy_rows],
           "formulas": {}, "counts": {}}
    for optimize, res in formulas.items():
        tag = "optimized" if optimize else "unoptimized"
        out["formulas"][tag] = {m: {q: {"coef": [str(c) for c in r[q][0]], "exact": r[q][1]} for q in ("N", "E", "M")}
                                for m, r in res.items()}
        out["counts"][tag] = {m: [dict(n=n, k=k, **v) for (n, k), v in r["data"].items()] for m, r in res.items()}
    out["slide_N"] = {m: list(v) for m, v in SLIDE_N.items()}
    out["provenance"] = {**git_commit(HERE.parents[1]), "versions": versions(), "finished": now_utc(), "quick": quick}
    with open(path, "w") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="smaller grids")
    main(ap.parse_args().quick)
