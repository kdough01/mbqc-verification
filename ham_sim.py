"""
hamsim_check.py — check the building block behind the Hamiltonian-simulation slide.

Both QSVT and GQSP call a *block encoding* of
    H = sum_i (h_i X_i + g_i Z_i) + sum_i J_i Z_i Z_{i+1}
d (or g) times. This file builds the unary ("one-hot") block encoding as a
Qiskit circuit, then checks three things:

  1. Correctness of the circuit:  (<0^m| ⊗ I) U (|0^m> ⊗ I) == H / alpha
  2. Correctness of the MBQC pattern: the Graphix pattern reproduces U exactly
     (statevector simulation, via qiskit_to_mbqc.verify)
  3. Resource scaling: vertices / CZs / measurements as a function of n,
     fitted to a*n + b, which is the form the slide's per-degree costs take.

Layout: qubits 0..n-1 are data, qubits n..n+m-1 are the m = 3n-1 unary ancillas,
one per Hamiltonian term (term k is "selected" when ancilla k is |1>).
"""

from __future__ import annotations

import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import SparsePauliOp, Statevector

from qiskit_converter import pattern_stats, plot_circuit_and_pattern, qiskit_to_pattern, verify


# ----------------------------------------------------------------------------
# The Hamiltonian
# ----------------------------------------------------------------------------

def ising_terms(h, g, J):
    """List of (coefficient, kind, qubits) for the slide's Hamiltonian."""
    n = len(h)
    terms = [(h[i], "X", (i,)) for i in range(n)]
    terms += [(g[i], "Z", (i,)) for i in range(n)]
    terms += [(J[i], "ZZ", (i, i + 1)) for i in range(n - 1)]
    return terms


def ising_matrix(h, g, J) -> np.ndarray:
    """Dense H in Qiskit's little-endian convention (qubit 0 = rightmost)."""
    n = len(h)
    labels = []
    for c, kind, qs in ising_terms(h, g, J):
        s = ["I"] * n
        for q, p in zip(qs, kind):
            s[n - 1 - q] = p
        labels.append(("".join(s), c))
    return SparsePauliOp.from_list(labels).to_matrix()


def random_coeffs(n, seed=0):
    rng = np.random.default_rng(seed)
    return rng.uniform(0.2, 1.0, n), rng.uniform(0.2, 1.0, n), rng.uniform(0.2, 1.0, n - 1)


# ----------------------------------------------------------------------------
# Unary block encoding:  U = PREP† · SELECT · PREP
# ----------------------------------------------------------------------------

def unary_prepare(amps) -> QuantumCircuit:
    """|0^m>  ->  sum_k amps[k] |e_k>   (one-hot / W-type state), O(m) gates.

    Start with the excitation on ancilla 0, then at each step keep amplitude
    amps[k] on ancilla k and pass the rest one ancilla down the line.
    """
    m = len(amps)
    qc = QuantumCircuit(m, name="PREP")
    qc.x(0)
    remaining = 1.0
    for k in range(m - 1):
        cos_half = np.clip(amps[k] / np.sqrt(remaining), -1, 1)
        theta = 2 * np.arccos(cos_half)
        qc.cry(theta, k, k + 1)   # |10> -> cos|10> + sin|11>
        qc.cx(k + 1, k)           # |11> -> |01>
        remaining -= amps[k] ** 2
    return qc


def unary_select(n, terms) -> QuantumCircuit:
    """SELECT = sum_k |e_k><e_k| ⊗ P_k  (+ identity elsewhere): one controlled Pauli per term."""
    m = len(terms)
    qc = QuantumCircuit(n + m, name="SELECT")
    for k, (_, kind, qs) in enumerate(terms):
        a = n + k
        if kind == "X":
            qc.cx(a, qs[0])
        elif kind == "Z":
            qc.cz(a, qs[0])
        else:  # ZZ: two controlled-Zs from the same ancilla
            qc.cz(a, qs[0])
            qc.cz(a, qs[1])
    return qc


def block_encoding(h, g, J) -> tuple[QuantumCircuit, float]:
    """Return (U, alpha) with (<0^m| ⊗ I) U (|0^m> ⊗ I) = H / alpha."""
    n = len(h)
    terms = ising_terms(h, g, J)
    coeffs = np.array([c for c, _, _ in terms])
    alpha = coeffs.sum()
    amps = np.sqrt(coeffs / alpha)

    m = len(terms)
    prep = unary_prepare(amps)
    anc = list(range(n, n + m))
    qc = QuantumCircuit(n + m)
    qc.compose(prep, anc, inplace=True)
    qc.compose(unary_select(n, terms), inplace=True)
    qc.compose(prep.inverse(), anc, inplace=True)
    return qc, alpha


# ----------------------------------------------------------------------------
# Checks
# ----------------------------------------------------------------------------

def check_block_encoding(h, g, J, atol=1e-9) -> float:
    """Max |entry| error between the top-left block of U and H/alpha."""
    n = len(h)
    qc, alpha = block_encoding(h, g, J)
    # Column j of the block = U applied to |0^m>|j>, keeping the ancillas-all-0
    # amplitudes. Ancillas are the high qubits (little-endian), so those are the
    # first 2^n entries of the statevector. One statevector per column avoids
    # building the full 2^(n+m) unitary.
    block = np.empty((2 ** n, 2 ** n), dtype=complex)
    for j in range(2 ** n):
        block[:, j] = Statevector.from_int(j, 2 ** qc.num_qubits).evolve(qc).data[: 2 ** n]
    err = np.abs(block - ising_matrix(h, g, J) / alpha).max()
    if err > atol:
        raise AssertionError(f"block encoding off by {err:.2e}")
    return err


def check_mbqc(h, g, J, seed=0) -> float:
    """Compile U to MBQC and confirm the pattern reproduces the circuit exactly."""
    qc, _ = block_encoding(h, g, J)
    return verify(qc, qiskit_to_pattern(qc), seed=seed)


def resource_table(ns, optimize=True):
    rows = []
    for n in ns:
        qc, _ = block_encoding(*random_coeffs(n))
        s = pattern_stats(qiskit_to_pattern(qc, optimize=optimize))
        rows.append((n, s["total_nodes"], s["edges (CZ)"], s["measurements"], s["max_space"]))
    return rows


def fit_linear(ns, ys):
    a, b = np.polyfit(ns, ys, 1)
    resid = np.max(np.abs(np.polyval([a, b], ns) - ys))
    return a, b, resid


if __name__ == "__main__":
    print("1) block encoding is correct (circuit level)")
    for n in (2, 3, 4):
        print(f"   n={n}: max error vs H/alpha = {check_block_encoding(*random_coeffs(n, seed=n)):.1e}")

    print("2) MBQC pattern reproduces the circuit")
    for n in (2, 3):
        print(f"   n={n}: |overlap| = {check_mbqc(*random_coeffs(n, seed=n)):.12f}")

    print("3) resources per block-encoding call vs n (optimized pattern)")
    ns = list(range(2, 11))
    rows = resource_table(ns)
    print("    n   vertices   CZs   meas   max_space")
    for r in rows:
        print("   %2d   %6d   %5d   %4d   %6d" % r)
    for name, col in (("vertices", 1), ("CZs", 2), ("measurements", 3)):
        a, b, resid = fit_linear(ns, [r[col] for r in rows])
        print(f"   {name:12s} ≈ {a:6.2f} n + {b:7.2f}   (max residual {resid:.2f})")

    qc, _ = block_encoding(*random_coeffs(2))
    plot_circuit_and_pattern(qc, filename="block_encoding_n2.png")
    print("saved block_encoding_n2.png")