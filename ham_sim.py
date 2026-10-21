"""
hamsim_check.py — verify the Hamiltonian-simulation slide, one layer at a time.

The slide's result has three layers (see README_hamsim.md):

  A. ACCURACY      "degree d_eps (or r_eps Trotter steps) gives error <= eps".
                   Imported from circuit-model theory. Checked by building the
                   circuit, simulating it, and comparing with exact e^{-iHt}.
  B. COST FORMULAS "N, E, M = (per-repetition cost) x repetitions + setup",
                   exact integer formulas. This is the MBQC-specific part.
                   Checked by compiling over a grid of (n, repetitions),
                   counting, fitting, and testing the fit on held-out points.
  C. CONSEQUENCES  Big-O and "d >= g  =>  GQSP is cheaper". Pure algebra on B.
                   Checked symbolically (sympy), for the slide's formulas and
                   for our own.

Plus an MBQC equivalence check (the compiled pattern equals the circuit) and a
cost comparison at equal accuracy, which does not depend on how each method
defines "degree".

Run:   python hamsim_check.py           (a few minutes)
       python hamsim_check.py --quick   (smaller grids)

Files: hamsim_circuits.py (circuits), qsp_angles.py (degrees and angles),
       qiskit_to_mbqc.py (circuit -> MBQC pattern).
"""

from __future__ import annotations

import argparse
import math
import time
from fractions import Fraction

import numpy as np
import sympy as sp
from qiskit.quantum_info import SparsePauliOp, Statevector
from scipy.linalg import expm

from circuits import (HamSimCircuit, IsingChain, gqsp_circuit, qsvt_circuit,
                             trotter_circuit)
from qiskit_to_mbqc import pattern_stats, qiskit_to_pattern, verify
from qsp_angles import (bessel_tail, chebyshev_coeffs_cos_sin, gqsp_angles,
                        gqsp_hamsim_polynomial, qsvt_phases, smallest_degree)

# Error budget. Each method approximates e^{-iHt} with a truncated series
# (truncation error <= TRUNC * eps) and scales its polynomial by BETA = 1 - TRUNC * eps
# so it stays strictly below 1 in magnitude, as angle finding requires.
# Both effects are far below eps; Layer A confirms the total numerically.
TRUNC = 0.1


# ============================================================================
# Helpers
# ============================================================================

def postselected_block(hc: HamSimCircuit) -> np.ndarray:
    """The operator applied to the data qubits, given the ancilla post-selection.

    Column j = run the circuit on |j>_data |0...0>_ancillas and keep the
    amplitudes whose ancilla bits match hc.postselect. Qiskit is little-endian
    and data qubits are 0..n-1, so those amplitudes are a contiguous slice.
    """
    n, N = hc.layout.n, hc.layout.num_qubits
    offset = sum(bit << q for q, bit in hc.postselect.items())
    block = np.empty((2 ** n, 2 ** n), dtype=complex)
    for j in range(2 ** n):
        out = Statevector.from_int(j, 2 ** N).evolve(hc.circuit).data
        block[:, j] = out[offset: offset + 2 ** n]
    return block


def op_norm(A: np.ndarray) -> float:
    """Spectral norm (largest singular value)."""
    return float(np.linalg.norm(A, 2))


def commutator(A: SparsePauliOp, B: SparsePauliOp) -> SparsePauliOp:
    return (A @ B - B @ A).simplify()


def norm_bound(op: SparsePauliOp) -> float:
    """Upper bound on ||op|| by the triangle inequality (sum of |Pauli coefficients|).
    Works for any n, unlike the exact norm."""
    return float(np.abs(op.coeffs).sum())


# ============================================================================
# "How many repetitions for accuracy eps" — the imported circuit-model results
# ============================================================================

def qsvt_degree(H: IsingChain, t: float, eps: float) -> int:
    """Odd D with Jacobi-Anger truncation error <= TRUNC*eps for cos (degree D-1) and sin (degree D)."""
    return smallest_degree(H.alpha * t, TRUNC * eps, parity="odd")


def gqsp_degree(H: IsingChain, t: float, eps: float) -> int:
    """Laurent degree d with sum_{|k|>d} |J_k(alpha t)| <= TRUNC*eps. Uses 2d walk calls."""
    return smallest_degree(H.alpha * t, TRUNC * eps)


def trotter_steps(H: IsingChain, t: float, eps: float, order: int, exact: bool = True) -> int:
    """Steps that the commutator error bounds guarantee to be enough.

    With A = X part, B = Z/ZZ part (Childs, Su, Tran, Wiebe & Zhu, PRX 11, 011020 (2021)):
      order 1:  ||S1(t/r)^r - e^{-iHt}|| <= t^2/(2r) ||[A,B]||
      order 2:  ||S2(t/r)^r - e^{-iHt}|| <= t^3/r^2 (||[B,[B,A]]||/12 + ||[A,[A,B]]||/24)
    exact=True uses spectral norms of the matrices (small n only); exact=False
    uses the triangle-inequality bound, which is larger and so still sufficient.
    """
    A, B = H.pauli_op("x"), H.pauli_op("z")
    norm = (lambda op: op_norm(op.to_matrix())) if exact else norm_bound
    if order == 1:
        c1 = norm(commutator(A, B))
        return max(1, math.ceil(t ** 2 * c1 / (2 * eps)))
    c2 = norm(commutator(B, commutator(B, A))) / 12 + norm(commutator(A, commutator(A, B))) / 24
    return max(1, math.ceil(math.sqrt(t ** 3 * c2 / eps)))


def build(method: str, H: IsingChain, t: float, eps: float) -> HamSimCircuit:
    """Circuit that should reach accuracy eps, with angles from qsp_angles."""
    tau, beta = H.alpha * t, 1 - TRUNC * eps
    if method == "qsvt":
        D = qsvt_degree(H, t, eps)
        cos_phases = qsvt_phases(chebyshev_coeffs_cos_sin(tau, D - 1, "cos"), beta)
        sin_phases = qsvt_phases(chebyshev_coeffs_cos_sin(tau, D, "sin"), beta)
        return qsvt_circuit(H, cos_phases, sin_phases)
    if method == "gqsp":
        d = gqsp_degree(H, t, eps)
        return gqsp_circuit(H, *gqsp_angles(gqsp_hamsim_polynomial(tau, d, beta)))
    raise ValueError(method)


def product_formula(H: IsingChain, t: float, r: int, order: int) -> np.ndarray:
    """The Trotter product as a matrix (fast for large r, unlike simulating the circuit)."""
    A, B = H.pauli_op("x").to_matrix(), H.pauli_op("z").to_matrix()
    dt = t / r
    if order == 1:
        step = expm(-1j * B * dt) @ expm(-1j * A * dt)    # A (X layer) acts first, as in the circuit
        return np.linalg.matrix_power(step, r)
    half = expm(-1j * A * dt / 2)
    return np.linalg.matrix_power(half @ expm(-1j * B * dt) @ half, r)


# ============================================================================
# Layer A: accuracy
# ============================================================================

def check_accuracy(ns, ts, epsilons) -> list[dict]:
    """For every (method, n, t, eps): repetitions from the theory, then the actual error."""
    rows = []
    for n in ns:
        H = IsingChain.random(n, seed=n)
        for t in ts:
            exact = expm(-1j * H.matrix() * t)
            for eps in epsilons:
                for method in ("trotter1", "trotter2", "qsvt", "gqsp"):
                    if method.startswith("trotter"):
                        order = int(method[-1])
                        r = trotter_steps(H, t, eps, order)
                        err = op_norm(product_formula(H, t, r, order) - exact)
                        reps = r
                    else:
                        hc = build(method, H, t, eps)
                        err = op_norm(postselected_block(hc) - exact)
                        reps = hc.calls
                    rows.append(dict(method=method, n=n, t=t, eps=eps, reps=reps, err=err, ok=err <= eps))
    return rows


def check_trotter_circuit_matches_formula(ns=(2, 3), rs=(1, 2, 5)) -> float:
    """Layer A uses product_formula() for speed; confirm the circuit implements it."""
    worst = 0.0
    for n in ns:
        H = IsingChain.random(n, seed=n)
        for r in rs:
            for order in (1, 2):
                hc = trotter_circuit(H, 0.7, r, order)
                worst = max(worst, op_norm(postselected_block(hc) - product_formula(H, 0.7, r, order)))
    return worst


def check_mbqc_equivalence() -> list[tuple[str, float]]:
    """Compile small instances to MBQC and confirm pattern == circuit on random inputs.

    Uses the unoptimized pattern for QSVT/GQSP: the optimized one keeps ~100
    qubits alive at once (see the 'max_space' column in Layer B) and can't be
    simulated. Trotter is checked both ways.
    """
    H = IsingChain.random(2, seed=2)
    out = []
    for opt in (False, True):
        hc = trotter_circuit(H, 1.0, 3, order=2)
        out.append((f"trotter2 r=3 ({'optimized' if opt else 'unoptimized'})",
                    verify(hc.circuit, qiskit_to_pattern(hc.circuit, optimize=opt))))
    for method in ("qsvt", "gqsp"):
        hc = build(method, H, t=0.3, eps=1e-2)
        out.append((f"{method} {hc.calls} calls (unoptimized)",
                    verify(hc.circuit, qiskit_to_pattern(hc.circuit, optimize=False))))
    return out


# ============================================================================
# Layer B: exact resource formulas
# ============================================================================
#
# Counts don't depend on the angle values (only on how many rotations there
# are), so we compile with random angles, which also avoids accidental
# simplifications at special angles like pi/2. "k" is the method's repetition
# parameter: Trotter steps r, QSVT degree D (3D calls), GQSP Laurent degree d (2d calls).

def generic_circuit(method: str, n: int, k: int, rng) -> HamSimCircuit:
    H = IsingChain.random(n, seed=n)
    if method == "trotter2":
        return trotter_circuit(H, 1.0, k, order=2)
    if method == "qsvt":
        return qsvt_circuit(H, rng.uniform(0, 2 * np.pi, k), rng.uniform(0, 2 * np.pi, k + 1))
    if method == "gqsp":
        th, ph = rng.uniform(0, 2 * np.pi, (2, 2 * k + 1))
        return gqsp_circuit(H, th, ph, rng.uniform(0, 2 * np.pi))
    raise ValueError(method)


def count(method: str, n: int, k: int, optimize: bool) -> dict:
    hc = generic_circuit(method, n, k, np.random.default_rng(1000 * n + k))
    s = pattern_stats(qiskit_to_pattern(hc.circuit, optimize=optimize))
    return {"N": s["total_nodes"], "E": s["edges (CZ)"], "M": s["measurements"], "space": s["max_space"]}


def fit_bilinear(points: list[tuple[int, int, int]], holdout: list[tuple[int, int, int]]):
    """Fit value = a*n*k + b*k + c*n + e (the slide's form) on `points`.

    Returns (coefficients as Fractions, exact?). 'exact' means the rounded
    rational formula reproduces every training AND held-out value exactly.
    """
    X = np.array([[n * k, k, n, 1] for n, k, _ in points], dtype=float)
    y = np.array([v for _, _, v in points], dtype=float)
    if np.linalg.matrix_rank(X) < 4:
        raise ValueError("training grid can't determine 4 coefficients: need >= 2 values of n and of k")
    coef = np.linalg.lstsq(X, y, rcond=None)[0]
    fracs = [Fraction(c).limit_denominator(12) for c in coef]
    predict = lambda n, k: fracs[0] * n * k + fracs[1] * k + fracs[2] * n + fracs[3]
    exact = all(predict(n, k) == v for n, k, v in points + holdout)
    worst = max(abs(float(predict(n, k)) - v) for n, k, v in points + holdout)
    return fracs, exact, worst


def format_formula(fracs, k: str) -> str:
    """(a n + b) k + c n + e, leaving out zero terms, e.g. '(294n - 144)D + 362n - 30'."""
    a, b, c, e = fracs
    s = lambda x: str(x) if x.denominator == 1 else f"({x})"

    def terms(pairs):              # [(coefficient, suffix)] -> "a n + b" style string
        out = ""
        for coef, suffix in pairs:
            if coef == 0:
                continue
            sign = "-" if coef < 0 else "+"
            out += (f"{'-' if coef < 0 else ''}" if not out else f" {sign} ") + s(abs(coef)) + suffix
        return out or "0"

    head = f"({terms([(a, 'n'), (b, '')])}){k}"
    if (c, e) == (0, 0):
        return head
    tail = terms([(c, "n"), (e, "")])
    return head + (f" - {tail[1:]}" if tail.startswith("-") else f" + {tail}")


GRIDS = {   # (training grid of (n, k), held-out points)
    "trotter2": ([(n, k) for n in (2, 3, 4, 5) for k in (1, 2, 3, 4)], [(7, 6), (9, 3)]),
    "qsvt":     ([(n, k) for n in (2, 3, 4) for k in (3, 5, 7)], [(5, 9)]),
    "gqsp":     ([(n, k) for n in (2, 3, 4) for k in (1, 2, 3)], [(5, 4)]),
}
REP_SYMBOL = {"trotter2": "r", "qsvt": "D", "gqsp": "d"}


def check_formulas(optimize: bool, quick: bool = False) -> dict:
    results = {}
    for method, (train, holdout) in GRIDS.items():
        if quick:   # keep the two smallest n (all k) so the fit is still determined
            small_n = sorted({n for n, _ in train})[:2]
            train = [(n, k) for n, k in train if n in small_n]
        data = {(n, k): count(method, n, k, optimize) for n, k in train + holdout}
        results[method] = {"data": data}
        for q in ("N", "E", "M"):
            pts = [(n, k, data[n, k][q]) for n, k in train]
            hold = [(n, k, data[n, k][q]) for n, k in holdout]
            results[method][q] = fit_bilinear(pts, hold)
    return results


# ============================================================================
# Layer C: consequences
# ============================================================================

def prove_slide_claim() -> dict[str, bool]:
    """Symbolic proof of the slide's claim: for all n >= 2 and odd d >= g >= 3,
    QSVT uses strictly more vertices, CZs and measurements than GQSP.

    Substitute n = 2 + p, d = g + 2k (p, k >= 0) and split g by residue mod 4
    (the slide's E_G has indicators chi = [g = 1 mod 4] and eta = [g = 3]):
    g = 3, g = 7 + 4q, g = 5 + 4q (q >= 0). In each case the difference
    QSVT - GQSP becomes a polynomial in p, q, k >= 0. If every coefficient is
    >= 0 and the constant term is > 0, it is positive for all allowed values.
    """
    n, d, g, p, q, k = sp.symbols("n d g p q k", integer=True, nonnegative=True)
    NQ = (36 * n - 18) * d + 14 * n + 23
    NG = (12 * n - 6) * g + 32 * n - 11
    EQ = (168 * n - 102) * d + 45 * n + 185

    def EG(chi, eta):
        return (124 * n - 116) * g + (122 - chi) * n - 40 + 3 * chi - eta

    cases = [  # (g substitution, chi, eta)
        (sp.Integer(3), 0, 1),
        (7 + 4 * q, 0, 0),
        (5 + 4 * q, 1, 0),
    ]

    def positive_for_all(expr) -> bool:
        poly = sp.Poly(sp.expand(expr), p, q, k)
        coeffs = dict(zip(poly.monoms(), poly.coeffs()))
        const = coeffs.get((0, 0, 0), 0)
        return const > 0 and all(c >= 0 for c in coeffs.values())

    result = {}
    for name, Q, G in (("vertices N", NQ, NG), ("measurements M", NQ - n, NG - n)):
        result[name] = all(positive_for_all((Q - G).subs({d: g + 2 * k}).subs({g: gs, n: 2 + p}))
                           for gs, _, _ in cases)
    result["executed CZs E"] = all(
        positive_for_all((EQ - EG(chi, eta)).subs({d: g + 2 * k}).subs({g: gs, n: 2 + p}))
        for gs, chi, eta in cases)
    return result


def our_claim_holds(formulas: dict, n_max: int = 50, k_max: int = 41) -> dict[str, bool]:
    """Same statement with OUR formulas: for all n in [2, n_max] and D >= d,
    does QSVT (degree D) use more than GQSP (Laurent degree d)?"""
    out = {}
    for q in ("N", "E", "M"):
        fq, fg = formulas["qsvt"][q][0], formulas["gqsp"][q][0]
        ev = lambda f, n, k: f[0] * n * k + f[1] * k + f[2] * n + f[3]
        out[q] = all(ev(fq, n, D) > ev(fg, n, d)
                     for n in range(2, n_max + 1) for d in range(1, k_max + 1)
                     for D in range(1, k_max + 1, 2) if D >= d)          # QSVT degree D is odd
    return out


SLIDE_N = {   # the slide's vertex formulas as (per-degree a, b, setup c, e): (a n + b) deg + c n + e
    "qsvt": (36, -18, 14, 23),
    "gqsp": (12, -6, 32, -11),
}


def compare_with_slide(formulas: dict) -> list[tuple]:
    """Our vertex formulas next to the slide's: same per-degree cost? same setup cost?"""
    rows = []
    for method in ("qsvt", "gqsp"):
        ours = tuple(formulas[method]["N"][0])
        slide = SLIDE_N[method]
        rows.append((method, slide, ours, ours[:2] == slide[:2], ours[2:] == slide[2:]))
    return rows


def cost_at_equal_accuracy(formulas: dict, ns, ts, epsilons) -> list[dict]:
    """Vertices each method needs to reach the same eps (this comparison doesn't
    depend on how each method counts 'degree'). Uses the fitted formulas, so it
    can go to n far beyond what we can simulate; Trotter steps use the
    triangle-inequality norm bound, which is valid at any n."""
    ev = lambda f, n, k: float(f[0] * n * k + f[1] * k + f[2] * n + f[3])
    rows = []
    for n in ns:
        H = IsingChain.random(n, seed=n)
        for t in ts:
            for eps in epsilons:
                reps = {"trotter2": trotter_steps(H, t, eps, 2, exact=False),
                        "qsvt": qsvt_degree(H, t, eps), "gqsp": gqsp_degree(H, t, eps)}
                cost = {m: ev(formulas[m]["N"][0], n, reps[m]) for m in reps}
                rows.append(dict(n=n, t=t, eps=eps, alpha=H.alpha, reps=reps, cost=cost,
                                 best=min(cost, key=cost.get)))
    return rows


# ============================================================================
# Report
# ============================================================================

def main(quick: bool = False) -> None:
    t_start = time.time()
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
        res = check_formulas(optimize, quick)
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
        for r in cost_at_equal_accuracy(formulas[optimize], ns=(4, 16, 64), ts=(1.0, 10.0), epsilons=(1e-2, 1e-4, 1e-8)):
            c, k = r["cost"], r["reps"]
            print(f"{r['n']:3d} {r['t']:4.0f} {r['eps']:7.0e} {r['alpha']:6.1f} | {k['trotter2']:6d} {k['qsvt']:4d} {k['gqsp']:4d} | "
                  f"{c['trotter2']:10.0f} {c['qsvt']:10.0f} {c['gqsp']:10.0f} | {r['best']}")

    save_results("hamsim_results.json", rows, formulas)
    print(f"\nsaved hamsim_results.json (input for plot_results.py)")
    print(f"total time {time.time() - t_start:.0f}s")


def save_results(path: str, accuracy_rows: list[dict], formulas: dict) -> None:
    """Write everything the plots need: accuracy rows, fitted formulas, and the raw counts."""
    import json
    out = {"accuracy": [{k: (bool(v) if k == "ok" else v) for k, v in r.items()} for r in accuracy_rows],
           "formulas": {}, "counts": {}}
    for optimize, res in formulas.items():
        tag = "optimized" if optimize else "unoptimized"
        out["formulas"][tag] = {m: {q: {"coef": [str(c) for c in r[q][0]], "exact": r[q][1]} for q in ("N", "E", "M")}
                                for m, r in res.items()}
        out["counts"][tag] = {m: [dict(n=n, k=k, **v) for (n, k), v in r["data"].items()] for m, r in res.items()}
    out["slide_N"] = {m: list(v) for m, v in SLIDE_N.items()}
    with open(path, "w") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="smaller grids")
    main(ap.parse_args().quick)