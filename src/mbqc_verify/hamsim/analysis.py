"""
analysis.py — the library half of the old ham_sim.py harness.

Everything here computes something about the Hamiltonian-simulation circuits:
how many repetitions each method needs for accuracy eps, the operator a
circuit applies after post-selection, the exact product formula, and the MBQC
resource counts of a compiled pattern. Nothing here decides whether a claim is
true; the checks under verification/ do that, and import these functions.
"""

from __future__ import annotations

import math
from fractions import Fraction

import numpy as np
from qiskit.quantum_info import SparsePauliOp, Statevector
from scipy.linalg import expm

from ..compile.qiskit_to_mbqc import pattern_stats, qiskit_to_pattern
from .circuits import HamSimCircuit, IsingChain, gqsp_circuit, qsvt_circuit, trotter_circuit
from .qsp_angles import (chebyshev_coeffs_cos_sin, gqsp_angles, gqsp_hamsim_polynomial,
                         qsvt_phases, smallest_degree)

# Error budget. Each method approximates e^{-iHt} with a truncated series
# (truncation error <= TRUNC * eps) and scales its polynomial by BETA = 1 - TRUNC * eps
# so it stays strictly below 1 in magnitude, as angle finding requires.
# Both effects are far below eps; Layer A confirms the total numerically.
TRUNC = 0.1

METHODS = ("trotter2", "qsvt", "gqsp")
REP_SYMBOL = {"trotter2": "r", "qsvt": "D", "gqsp": "d"}


# ============================================================================
# Operators
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


# ============================================================================
# MBQC resource counts
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
    """N (vertices), E (CZ edges), M (measurements) and peak live qubits of the compiled pattern."""
    hc = generic_circuit(method, n, k, np.random.default_rng(1000 * n + k))
    s = pattern_stats(qiskit_to_pattern(hc.circuit, optimize=optimize))
    return {"N": s["total_nodes"], "E": s["edges (CZ)"], "M": s["measurements"], "space": s["max_space"]}


# ============================================================================
# Bilinear formulas  value = (a n + b) k + c n + e
# ============================================================================

def evaluate(coef, n, k):
    """Value of the bilinear formula with coefficients (a, b, c, e) at (n, k)."""
    a, b, c, e = coef
    return a * n * k + b * k + c * n + e


def format_formula(fracs, k: str) -> str:
    """(a n + b) k + c n + e, leaving out zero terms, e.g. '(294n - 144)D + 362n - 30'."""
    a, b, c, e = (Fraction(x) for x in fracs)
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


def cost_at_equal_accuracy(formulas: dict, ns, ts, epsilons) -> list[dict]:
    """Vertices each method needs to reach the same eps (this comparison doesn't
    depend on how each method counts 'degree'). `formulas[method]` is the (a, b, c, e)
    vertex formula. Trotter steps use the triangle-inequality norm bound, which is
    valid at any n."""
    rows = []
    for n in ns:
        H = IsingChain.random(n, seed=n)
        for t in ts:
            for eps in epsilons:
                reps = {"trotter2": trotter_steps(H, t, eps, 2, exact=False),
                        "qsvt": qsvt_degree(H, t, eps), "gqsp": gqsp_degree(H, t, eps)}
                cost = {m: float(evaluate(formulas[m], n, reps[m])) for m in reps}
                rows.append(dict(n=n, t=t, eps=eps, alpha=H.alpha, reps=reps, cost=cost,
                                 best=min(cost, key=cost.get)))
    return rows
