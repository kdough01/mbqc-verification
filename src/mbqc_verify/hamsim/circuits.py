"""
circuits.py — Qiskit circuits for simulating the slide's Ising chain

    H = sum_{i=0}^{n-1} (h_i X_i + g_i Z_i) + sum_{i=0}^{n-2} J_i Z_i Z_{i+1}

with three methods:

    trotter_circuit  product formula, r steps (order 1 or 2). No ancillas.
    qsvt_circuit     QSVT for cos(Ht) and sin(Ht), combined by a linear
                     combination of unitaries (LCU), then one round of
                     oblivious amplitude amplification (OAA).
    gqsp_circuit     GQSP on the qubitization walk operator.

Every builder returns a HamSimCircuit: the circuit, the qubit layout, and the
ancilla bits to post-select on. With the ancillas starting in |0...0>, the
operator applied to the data qubits *given* that post-selection is the
method's approximation of e^{-iHt}; analysis.postselected_block() extracts it,
and the checks under verification/ test it.

Qubit layout (Qiskit indices):
    0 .. n-1          data qubits
    n .. n+m-1        unary ancillas, one per Hamiltonian term (m = 3n - 1)
    n+m, n+m+1, ...   extra qubits by name: "sig" (QSVT, GQSP), "lcu" (QSVT)

Angles (phases) are inputs here; qsp_angles.py computes them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import SparsePauliOp

from .qsp_angles import gqsp_rotation


# ============================================================================
# The Hamiltonian
# ============================================================================

@dataclass
class IsingChain:
    h: np.ndarray   # X coefficients, length n
    g: np.ndarray   # Z coefficients, length n
    J: np.ndarray   # ZZ coefficients, length n-1

    @property
    def n(self) -> int:
        return len(self.h)

    def terms(self) -> list[tuple[float, str, tuple[int, ...]]]:
        """(coefficient, Pauli kind, qubits) for every term, in a fixed order."""
        n = self.n
        return ([(self.h[i], "X", (i,)) for i in range(n)]
                + [(self.g[i], "Z", (i,)) for i in range(n)]
                + [(self.J[i], "ZZ", (i, i + 1)) for i in range(n - 1)])

    @property
    def alpha(self) -> float:
        """Sum of the (positive) coefficients: the block-encoding normalization."""
        return float(self.h.sum() + self.g.sum() + self.J.sum())

    def pauli_op(self, which: str = "all") -> SparsePauliOp:
        """H (or only its 'x' part, or only its 'z' part) as a SparsePauliOp.
        Qiskit labels are little-endian: qubit 0 is the rightmost character."""
        labels = []
        for c, kind, qs in self.terms():
            if (which == "x" and kind != "X") or (which == "z" and kind == "X"):
                continue                     # keep only the requested part
            s = ["I"] * self.n
            for q, p in zip(qs, kind):
                s[self.n - 1 - q] = p
            labels.append(("".join(s), c))
        return SparsePauliOp.from_list(labels)

    def matrix(self) -> np.ndarray:
        return self.pauli_op().to_matrix()

    @staticmethod
    def random(n: int, seed: int = 0, low: float = 0.2, high: float = 1.0) -> "IsingChain":
        rng = np.random.default_rng(seed)
        return IsingChain(rng.uniform(low, high, n), rng.uniform(low, high, n),
                          rng.uniform(low, high, n - 1))


# ============================================================================
# Layout and result container
# ============================================================================

@dataclass
class Layout:
    n: int                        # data qubits
    m: int = 0                    # unary ancillas
    extra: tuple[str, ...] = ()   # named extra qubits

    def anc(self, k: int) -> int:
        return self.n + k

    def q(self, name: str) -> int:
        return self.n + self.m + self.extra.index(name)

    @property
    def num_qubits(self) -> int:
        return self.n + self.m + len(self.extra)


@dataclass
class HamSimCircuit:
    circuit: QuantumCircuit
    layout: Layout
    postselect: dict[int, int] = field(default_factory=dict)  # qubit -> required bit
    calls: int = 0           # number of block-encoding (or walk) calls; Trotter: steps
    method: str = ""


# ============================================================================
# Unary block encoding  U = PREP^dagger . SELECT . PREP
# ============================================================================
#
# One ancilla per term. The ancillas always hold a "one-hot" state: exactly one
# ancilla is |1>. We start them in |e_0> (ancilla 0 is |1>).
#
#   PREP:    |e_0>  ->  sum_k sqrt(c_k / alpha) |e_k>
#            built from 2-qubit Givens rotations, which never leave the one-hot
#            subspace.
#   SELECT:  |e_k>|psi> -> |e_k> P_k |psi>   (one controlled Pauli per term)
#
# Then (<e_0| (x) I) U (|e_0> (x) I) = sum_k (c_k/alpha) P_k = H / alpha.
#
# Why one-hot pays off: the reflection about the "good" ancilla state
# (2 |e_0><e_0| - I) is, on the one-hot subspace, simply -Z on ancilla 0 (that
# ancilla is |1> exactly for |e_0>). So every reflection QSVT and GQSP need is
# a single-qubit Z, not a many-qubit controlled gate. On that subspace U is
# also Hermitian with U^2 = I (each P_k^2 = I), which is what qubitization needs.

def _givens(qc: QuantumCircuit, a: int, b: int, theta: float) -> None:
    """|10> -> cos(theta/2)|10> + sin(theta/2)|01>, |01> -> -sin|10> + cos|01>,
    |00> and |11> unchanged (qubit order a, b). Preserves the number of 1s."""
    qc.cx(b, a)
    qc.cry(theta, a, b)
    qc.cx(b, a)


def prepare_circuit(layout: Layout, H: IsingChain) -> QuantumCircuit:
    """PREP on the full register (acts only on the ancillas)."""
    amps = np.sqrt(np.array([c for c, _, _ in H.terms()]) / H.alpha)
    qc = QuantumCircuit(layout.num_qubits, name="PREP")
    remaining = 1.0                      # weight still sitting on ancilla k
    for k in range(layout.m - 1):
        # keep amplitude amps[k] on ancilla k, pass the rest to ancilla k+1
        theta = 2 * np.arccos(np.clip(amps[k] / np.sqrt(remaining), -1, 1))
        _givens(qc, layout.anc(k), layout.anc(k + 1), theta)
        remaining -= amps[k] ** 2
    return qc


def select_circuit(layout: Layout, H: IsingChain, control: tuple[int, int] | None = None) -> QuantumCircuit:
    """SELECT on the full register. If control = (qubit, bit), every Pauli is
    applied only when that qubit equals bit (used to make U controlled: PREP and
    PREP^dagger cancel when SELECT is skipped, so only SELECT needs the control)."""
    qc = QuantumCircuit(layout.num_qubits, name="SELECT")
    if control is not None and control[1] == 0:
        qc.x(control[0])                 # open control = flip, control on 1, flip back

    for k, (_, kind, qubits) in enumerate(H.terms()):
        a = layout.anc(k)
        for target, pauli in zip(qubits, kind):
            if control is None:
                (qc.cx if pauli == "X" else qc.cz)(a, target)
            else:
                c = control[0]
                if pauli == "X":
                    qc.ccx(c, a, target)
                else:                    # CCZ = H . CCX . H on the target
                    qc.h(target)
                    qc.ccx(c, a, target)
                    qc.h(target)

    if control is not None and control[1] == 0:
        qc.x(control[0])
    return qc


def block_encoding_circuit(layout: Layout, H: IsingChain, control=None) -> QuantumCircuit:
    """U = PREP^dagger . SELECT . PREP  (optionally controlled; see select_circuit)."""
    prep = prepare_circuit(layout, H)
    qc = QuantumCircuit(layout.num_qubits, name="U")
    qc.compose(prep, inplace=True)
    qc.compose(select_circuit(layout, H, control), inplace=True)
    qc.compose(prep.inverse(), inplace=True)
    return qc


# ============================================================================
# Method 1: Trotter (product formula)
# ============================================================================
#
# Split H = A + B with A = all X terms, B = all Z and ZZ terms. Terms within A
# commute, and so do terms within B, so e^{-iA dt} and e^{-iB dt} are exact
# layers of single-qubit and ZZ rotations.
#   order 1:  (e^{-iA dt} e^{-iB dt})^r
#   order 2:  (e^{-iA dt/2} e^{-iB dt} e^{-iA dt/2})^r, with neighbouring half
#             steps of A merged, so r B-layers and r+1 A-layers in total.

def _x_layer(qc, H, dt):
    for i in range(H.n):
        qc.rx(2 * H.h[i] * dt, i)        # e^{-i h X dt} = RX(2 h dt)


def _z_layer(qc, H, dt):
    for i in range(H.n):
        qc.rz(2 * H.g[i] * dt, i)
    for i in range(H.n - 1):
        qc.rzz(2 * H.J[i] * dt, i, i + 1)


def trotter_circuit(H: IsingChain, t: float, r: int, order: int = 2) -> HamSimCircuit:
    dt = t / r
    qc = QuantumCircuit(H.n)
    if order == 1:
        for _ in range(r):
            _x_layer(qc, H, dt)
            _z_layer(qc, H, dt)
    elif order == 2:
        _x_layer(qc, H, dt / 2)
        for step in range(r):
            _z_layer(qc, H, dt)
            _x_layer(qc, H, dt if step < r - 1 else dt / 2)
    else:
        raise ValueError("order must be 1 or 2")
    return HamSimCircuit(qc, Layout(H.n), {}, calls=r, method=f"trotter{order}")


# ============================================================================
# Method 2: QSVT + LCU + oblivious amplitude amplification
# ============================================================================
#
# QSVT turns D calls of U into a degree-D polynomial of H/alpha, of definite
# parity. e^{-iHt} = cos(Ht) - i sin(Ht) has mixed parity, so we build
#     C ~ cos(Ht)  (even, D-1 calls)    and    S ~ sin(Ht)  (odd, D calls)
# on two branches of an "lcu" qubit and combine them:
#
#  * Real-part trick ("sig" qubit): the projector phase e^{i phi (2 Pi - I)} is
#    applied as e^{i phi (2 Pi - I) Z_sig}. With sig in |+>, the two sig
#    branches see phases +phi and -phi; projecting sig back on |+> averages
#    them, giving the REAL polynomial Re P (the angle finder targets Re P).
#    Since 2 Pi - I = -Z_{a0} on the one-hot subspace, that phase is
#    exp(-i phi Z_{a0} Z_sig) = RZZ(2 phi) on (a0, sig).
#
#  * LCU ("lcu" qubit): branch lcu=0 uses the cos phases, lcu=1 the sin phases.
#    Writing phi_l = (phi_c + phi_s)/2 + (phi_c - phi_s)/2 Z_lcu, the phase step
#    becomes RZZ(phi_c + phi_s) on (a0, sig) and a 3-qubit ZZZ rotation by
#    (phi_c - phi_s) on (a0, sig, lcu). The cos branch makes one call fewer:
#    on its last call only SELECT is controlled (on lcu = 1), so for lcu = 0 the
#    call collapses to PREP^dagger PREP = I. A final S^dagger on lcu supplies
#    the -i. Projecting lcu on |+> gives (C - i S)/2 ~ beta e^{-iHt} / 2.
#
#  * OAA: if V block-encodes (beta/2) * (a unitary) with beta ~ 1, then
#    -V R V^dagger R V block-encodes sin(3 arcsin(beta/2)) * (that unitary)
#    ~ 1 * (that unitary), where R = I - 2 |good><good| on the ancillas
#    (a CCZ on a0, sig, lcu, with sig and lcu flipped since good = (1, 0, 0)).

def _zzz_rotation(qc, a, b, c, theta):
    """exp(-i theta/2 Z_a Z_b Z_c): compute the parity into c, rotate, uncompute."""
    qc.cx(a, b)
    qc.cx(b, c)
    qc.rz(theta, c)
    qc.cx(b, c)
    qc.cx(a, b)


def _qsvt_block(layout: Layout, H: IsingChain, phases_cos, phases_sin) -> QuantumCircuit:
    """V: block-encodes (C - i S)/2 with C, S the QSVT real polynomials."""
    D = len(phases_sin) - 1                 # number of calls on the sin branch
    assert len(phases_cos) == D, "cos branch must have one call fewer (D-1 calls, D phases)"
    phi_c = np.append(phases_cos, 0.0)      # cos branch: no phase after its skipped call
    phi_s = np.asarray(phases_sin)

    a0, sig, lcu = layout.anc(0), layout.q("sig"), layout.q("lcu")
    U = block_encoding_circuit(layout, H)
    U_sin_only = block_encoding_circuit(layout, H, control=(lcu, 1))

    qc = QuantumCircuit(layout.num_qubits, name="V")
    qc.h(sig)
    qc.h(lcu)
    for j in range(D + 1):
        qc.rzz(phi_c[j] + phi_s[j], a0, sig)
        _zzz_rotation(qc, a0, sig, lcu, phi_c[j] - phi_s[j])
        if j < D - 1:
            qc.compose(U, inplace=True)
        elif j == D - 1:
            qc.compose(U_sin_only, inplace=True)
    qc.sdg(lcu)
    qc.h(sig)
    qc.h(lcu)
    return qc


def _reflect_good(qc: QuantumCircuit, layout: Layout) -> None:
    """I - 2 |good><good| with good = (a0=1, sig=0, lcu=0), on the one-hot subspace."""
    a0, sig, lcu = layout.anc(0), layout.q("sig"), layout.q("lcu")
    qc.x(sig)
    qc.x(lcu)
    qc.h(lcu)
    qc.ccx(a0, sig, lcu)                    # CCZ via H . CCX . H
    qc.h(lcu)
    qc.x(sig)
    qc.x(lcu)


def qsvt_circuit(H: IsingChain, phases_cos, phases_sin) -> HamSimCircuit:
    layout = Layout(H.n, len(H.terms()), ("sig", "lcu"))
    V = _qsvt_block(layout, H, phases_cos, phases_sin)

    qc = QuantumCircuit(layout.num_qubits)
    qc.x(layout.anc(0))                     # ancillas start in |e_0>
    qc.compose(V, inplace=True)             # oblivious amplitude amplification:
    _reflect_good(qc, layout)               #   -V R V^dagger R V
    qc.compose(V.inverse(), inplace=True)
    _reflect_good(qc, layout)
    qc.compose(V, inplace=True)
    qc.global_phase += np.pi                # the leading minus sign

    post = {layout.anc(k): int(k == 0) for k in range(layout.m)}
    post.update({layout.q("sig"): 0, layout.q("lcu"): 0})
    D = len(phases_sin) - 1
    return HamSimCircuit(qc, layout, post, calls=3 * D, method="qsvt")


# ============================================================================
# Method 3: GQSP on the walk operator
# ============================================================================
#
# Walk operator W = Z_{a0} . U. On each 2D invariant subspace it has
# eigenvalues e^{+-iw} with cos w = -x (x = eigenvalue of H / alpha), so a
# Laurent polynomial f(W) = sum_{k=-d}^{d} c_k W^k with f(e^{iw}) =
# e^{i tau cos w} gives e^{-i tau x} = e^{-iHt} (tau = alpha t).
#
# GQSP only makes ordinary polynomials P(W) (powers 0..2d) using the
# signal-controlled operator c0-W = |0><0| (x) W + |1><1| (x) I. We alternate
# c0-W with c1-W^dagger = |0><0| (x) I + |1><1| (x) W^dagger. Because
# c1-W^dagger = W^dagger . c0-W and W^dagger commutes with signal-qubit
# rotations, d of each give W^{-d} P(W) with P computed as if all 2d calls
# were c0-W. Choosing P(z) = z^d f(z) then yields f(W).

def _controlled_walk(layout: Layout, H: IsingChain, on_bit: int, dagger: bool) -> QuantumCircuit:
    """|on_bit><on_bit|_sig (x) W(^dagger) + (other sig value) (x) I."""
    sig, a0 = layout.q("sig"), layout.anc(0)
    cU = block_encoding_circuit(layout, H, control=(sig, on_bit))
    cZ = QuantumCircuit(layout.num_qubits)
    if on_bit == 0:
        cZ.x(sig)
    cZ.cz(sig, a0)
    if on_bit == 0:
        cZ.x(sig)
    # W = Z_a0 . U  (U first), W^dagger = U . Z_a0  (Z first)
    first, second = (cZ, cU) if dagger else (cU, cZ)
    qc = QuantumCircuit(layout.num_qubits, name="cW")
    qc.compose(first, inplace=True)
    qc.compose(second, inplace=True)
    return qc


def gqsp_circuit(H: IsingChain, thetas, phis, lam) -> HamSimCircuit:
    D = len(thetas) - 1                     # = 2d calls
    assert D % 2 == 0, "GQSP Hamiltonian simulation uses an even number (2d) of calls"
    layout = Layout(H.n, len(H.terms()), ("sig",))
    sig = layout.q("sig")
    cW = _controlled_walk(layout, H, on_bit=0, dagger=False)
    cWdag = _controlled_walk(layout, H, on_bit=1, dagger=True)

    qc = QuantumCircuit(layout.num_qubits)
    qc.x(layout.anc(0))                     # ancillas start in |e_0>
    qc.unitary(gqsp_rotation(thetas[0], phis[0], lam), [sig], label="R0")
    for j in range(1, D + 1):
        qc.compose(cW if j % 2 == 1 else cWdag, inplace=True)
        qc.unitary(gqsp_rotation(thetas[j], phis[j]), [sig], label=f"R{j}")

    post = {layout.anc(k): int(k == 0) for k in range(layout.m)}
    post[sig] = 0
    return HamSimCircuit(qc, layout, post, calls=D, method="gqsp")