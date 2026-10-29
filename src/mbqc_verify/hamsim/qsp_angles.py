"""
qsp_angles.py — the classical pre-processing for QSVT and GQSP Hamiltonian simulation.

Both algorithms implement a polynomial approximation of e^{-iHt} by calling a
block encoding of H/alpha many times with single-qubit rotations in between.
This file answers two questions, for a given rescaled time tau = alpha * t and
target error eps:

  1. How large must the polynomial degree be?        (degree selection)
  2. Which rotation angles produce that polynomial?  (angle finding)

Nothing in this file touches a quantum circuit. Every angle-finding routine is
checked against a 2x2 "model" of one invariant subspace, which is exactly what
the circuit does on each eigenvector of H (see circuits.py).

Background
----------
Jacobi-Anger expansion (x in [-1, 1], J_k = Bessel functions of the first kind):

    cos(tau x) = J_0(tau) + 2 sum_{k>=1} (-1)^k J_{2k}(tau)   T_{2k}(x)
    sin(tau x) =            2 sum_{k>=0} (-1)^k J_{2k+1}(tau) T_{2k+1}(x)
    e^{i tau cos w} = sum_{k=-inf}^{inf} i^k J_k(tau) e^{i k w}

Truncating at degree D leaves an error of at most  bessel_tail(tau, D+1),
where bessel_tail(tau, K) = 2 * sum_{k >= K} |J_k(tau)|.
"""

from __future__ import annotations

import numpy as np
from numpy.polynomial import chebyshev as cheb
from scipy.optimize import least_squares
from scipy.special import jv


# ----------------------------------------------------------------------------
# 1. Degree selection
# ----------------------------------------------------------------------------

def bessel_tail(tau: float, K: int) -> float:
    """2 * sum_{k >= K} |J_k(tau)|: bounds the error of truncating any of the
    three series above at degree K - 1. (|J_k| decays super-exponentially once
    k > tau, so summing 60 terms past max(K, tau) is plenty.)"""
    ks = np.arange(K, max(K, int(tau)) + 60)
    return 2.0 * np.abs(jv(ks, tau)).sum()


def smallest_degree(tau: float, budget: float, parity: str | None = None) -> int:
    """Smallest degree D (optionally odd/even) with bessel_tail(tau, D+1) <= budget."""
    D = 0
    while bessel_tail(tau, D + 1) > budget or (parity == "odd" and D % 2 == 0) or (
        parity == "even" and D % 2 == 1
    ):
        D += 1
    return D


# ----------------------------------------------------------------------------
# 2a. QSVT angles (symmetric QSP for a real polynomial of definite parity)
# ----------------------------------------------------------------------------
#
# The circuit (circuits.qsvt_circuit) acts on each 2D invariant subspace
# {|good>, |perp>} as the product, in time order,
#
#     e^{i phi_0 Z},  R(x),  e^{i phi_1 Z},  R(x), ...,  R(x),  e^{i phi_D Z}
#
# with R(x) = [[x, s], [s, -x]], s = sqrt(1-x^2), x = (eigenvalue of H)/alpha,
# and it returns Re <good| ... |good>  (the "real part" trick, see circuits).
# This is the "reflection convention" of QSVT.
#
# Angle finding is best understood in the other standard convention ("Wx"),
# where R(x) is replaced by W(x) = [[x, i s], [i s, x]]. There, starting from
# phases (pi/4, 0, ..., 0, pi/4) and solving with symmetric phases converges
# reliably (Dong, Lin & Wang, "Efficient phase-factor evaluation in QSP", 2021).
# We solve in Wx and convert with wx_to_reflection_phases(), then check the
# result in the reflection convention the circuit actually uses.

def chebyshev_coeffs_cos_sin(tau: float, degree: int, kind: str) -> np.ndarray:
    """Chebyshev coefficients of the degree-truncated cos(tau x) or sin(tau x)."""
    c = np.zeros(degree + 1)
    for k in range(degree + 1):
        if kind == "cos" and k % 2 == 0:
            c[k] = (1 if k == 0 else 2) * (-1) ** (k // 2) * jv(k, tau)
        elif kind == "sin" and k % 2 == 1:
            c[k] = 2 * (-1) ** ((k - 1) // 2) * jv(k, tau)
    return c


def qsp_response_reflection(phases, x) -> np.ndarray:
    """<good| e^{i phi_0 Z} R(x) e^{i phi_1 Z} ... R(x) e^{i phi_D Z} |good>,
    applied in time order; this is what the QSVT circuit implements."""
    x = np.asarray(x, dtype=float)
    s = np.sqrt(1 - x ** 2)
    v0 = np.exp(1j * phases[0]) * np.ones_like(x, dtype=complex)
    v1 = np.zeros_like(v0)
    for phi in phases[1:]:
        v0, v1 = x * v0 + s * v1, s * v0 - x * v1              # R(x)
        v0, v1 = v0 * np.exp(1j * phi), v1 * np.exp(-1j * phi)  # e^{i phi Z}
    return v0


def _qsp_response_wx(phases, x) -> np.ndarray:
    """Same as above but with W(x) = [[x, i s], [i s, x]] (the Wx convention)."""
    x = np.asarray(x, dtype=float)
    s = np.sqrt(1 - x ** 2)
    v0 = np.exp(1j * phases[0]) * np.ones_like(x, dtype=complex)
    v1 = np.zeros_like(v0)
    for phi in phases[1:]:
        v0, v1 = x * v0 + 1j * s * v1, 1j * s * v0 + x * v1
        v0, v1 = v0 * np.exp(1j * phi), v1 * np.exp(-1j * phi)
    return v0


def wx_to_reflection_phases(wx_phases) -> np.ndarray:
    """Convert Wx phases to reflection phases giving the *same* <good|..|good>.

    Uses R(x) = -i e^{i pi/4 Z} W(x) e^{i pi/4 Z}. Substituting this for every
    R shifts interior phases by -pi/2 and end phases by -pi/4, and leaves a
    global factor (-i)^D, which we cancel by moving both end phases by D*pi/4
    (each end contributes e^{i D pi/4} on |good>).
    """
    ph = np.asarray(wx_phases, dtype=float)
    D = len(ph) - 1
    if D == 0:
        return ph.copy()
    out = ph - np.pi / 2
    out[0] = ph[0] - np.pi / 4 + D * np.pi / 4
    out[-1] = ph[-1] - np.pi / 4 + D * np.pi / 4
    return out


def _symmetric(free: np.ndarray, D: int) -> np.ndarray:
    """Expand the first ceil((D+1)/2) phases to the full symmetric list of D+1."""
    n_free = len(free)
    return np.concatenate([free, free[: (D + 1) - n_free][::-1]])


def qsvt_phases(cheb_coeffs: np.ndarray, scale: float = 1.0, tol: float = 1e-12) -> np.ndarray:
    """Reflection-convention phases with Re(response) = scale * f(x), f given in
    the Chebyshev basis. f must have definite parity and |scale * f| < 1 on [-1, 1].

    Method: symmetric phases, one equation per positive Chebyshev node (a square
    system), solved by Levenberg-Marquardt from the standard starting point.
    """
    D = len(cheb_coeffs) - 1
    n_free = D // 2 + 1
    j = np.arange(1, n_free + 1)
    nodes = np.cos((2 * j - 1) * np.pi / (4 * n_free))
    target = scale * cheb.chebval(nodes, cheb_coeffs)

    start = np.zeros(n_free)
    start[0] = np.pi / 4
    sol = least_squares(
        lambda free: _qsp_response_wx(_symmetric(free, D), nodes).real - target,
        start, method="lm", xtol=1e-15, ftol=1e-15, gtol=1e-15,
    )
    phases = wx_to_reflection_phases(_symmetric(sol.x, D))

    # Check on a dense grid, in the convention the circuit uses.
    grid = np.cos(np.linspace(0, np.pi, 2001))
    err = np.abs(qsp_response_reflection(phases, grid).real - scale * cheb.chebval(grid, cheb_coeffs)).max()
    if err > tol:
        raise RuntimeError(f"QSVT phase finding did not converge (max error {err:.2e})")
    return phases


# ----------------------------------------------------------------------------
# 2b. GQSP angles (Motlagh & Wiebe, "Generalized Quantum Signal Processing",
#     PRX Quantum 5, 020368, 2024)
# ----------------------------------------------------------------------------
#
# GQSP acts on one signal qubit. With A = |0><0| (x) U + |1><1| (x) I, the sequence
#
#     R(th_0, ph_0, lam),  A,  R(th_1, ph_1, 0),  A,  ...,  A,  R(th_D, ph_D, 0)
#
# (time order) has first column (P(U), Q(U)) for polynomials P, Q of degree D,
# where R(th, ph, lam) = [[e^{i(lam+ph)} cos th, e^{i ph} sin th],
#                         [e^{i lam} sin th,     -cos th        ]].
# Any P with |P(z)| <= 1 on |z| = 1 is reachable. To find the angles:
#   (a) find a "complementary" Q with |P|^2 + |Q|^2 = 1 on the unit circle;
#   (b) peel off one R and one A at a time ("layer stripping").

def gqsp_rotation(theta: float, phi: float, lam: float = 0.0) -> np.ndarray:
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[np.exp(1j * (lam + phi)) * c, np.exp(1j * phi) * s],
                     [np.exp(1j * lam) * s, -c]])


def complementary_polynomial(p: np.ndarray, n_fft: int = 2 ** 15) -> np.ndarray:
    """Q (same degree as P, coefficients low-to-high) with |P|^2 + |Q|^2 = 1 on |z|=1.

    Uses the FFT "outer function" construction: on the circle, set
    |Q| = sqrt(1 - |P|^2) and choose the phase that makes Q analytic inside the
    unit disk (keep only non-negative Fourier modes of log|Q|, doubled). The
    result is a polynomial of degree deg(P) up to aliasing error, which shrinks
    as n_fft grows. Requires max |P| < 1 on the circle.
    (See Berntson & Suenderhauf, "Complementary polynomials in QSP", 2024.)
    """
    D = len(p) - 1
    z = np.exp(2j * np.pi * np.arange(n_fft) / n_fft)
    one_minus = 1 - np.abs(np.polyval(p[::-1], z)) ** 2
    if one_minus.min() <= 0:
        raise ValueError("need |P| < 1 on the unit circle (scale P down slightly)")
    log_mod = np.fft.fft(0.5 * np.log(one_minus)) / n_fft        # Fourier modes of log|Q|
    analytic = np.zeros(n_fft, dtype=complex)
    analytic[0] = log_mod[0]
    analytic[1 : n_fft // 2] = 2 * log_mod[1 : n_fft // 2]          # drop negative modes
    q_on_circle = np.exp(np.fft.ifft(analytic) * n_fft)
    q = np.fft.fft(q_on_circle) / n_fft
    return q[: D + 1]


def gqsp_angles(p: np.ndarray, tol: float = 1e-10):
    """Angles (thetas, phis, lam) whose GQSP sequence has <0|...|0> = P(U).

    p: coefficients of P(z), lowest power first. Returns arrays of length D+1.
    """
    p = np.array(p, dtype=complex)
    q = complementary_polynomial(p)
    P, Q = p.copy(), q.copy()
    D = len(p) - 1
    thetas, phis = np.zeros(D + 1), np.zeros(D + 1)

    for j in range(D, 0, -1):
        # The last layer is R_j A. Undo R_j: the result must equal (z P', Q') with
        # deg P', Q' <= j-1. That fixes (theta_j, phi_j) through either
        #   top coefficient of row 1 vanishing:  e^{-i phi} sin(th) P[j] = cos(th) Q[j]
        #   constant term of row 0 vanishing:   e^{-i phi} cos(th) P[0] = -sin(th) Q[0]
        # (theory says both hold; we use the better-conditioned one).
        if abs(P[j]) ** 2 + abs(Q[j]) ** 2 >= abs(P[0]) ** 2 + abs(Q[0]) ** 2:
            theta = np.arctan2(abs(Q[j]), abs(P[j]))
            phi = np.angle(P[j]) - np.angle(Q[j])
        else:
            theta = np.arctan2(abs(P[0]), abs(Q[0]))
            phi = np.angle(P[0]) - np.angle(-Q[0])
        thetas[j], phis[j] = theta, phi

        Rinv = gqsp_rotation(theta, phi).conj().T
        row0 = Rinv[0, 0] * P + Rinv[0, 1] * Q
        row1 = Rinv[1, 0] * P + Rinv[1, 1] * Q
        P, Q = row0[1:], row1[:-1]       # divide row 0 by z; drop row 1's (zero) top term

    # What is left is R_0 |0> = (e^{i(lam+phi_0)} cos th_0, e^{i lam} sin th_0).
    lam = np.angle(Q[0])
    phis[0] = np.angle(P[0]) - lam
    thetas[0] = np.arctan2(abs(Q[0]), abs(P[0]))

    # Check in the 2x2 model on the unit circle.
    zs = np.exp(1j * np.linspace(0, 2 * np.pi, 257))
    err = max(abs(gqsp_response(thetas, phis, lam, z) - np.polyval(p[::-1], z)) for z in zs)
    if err > tol:
        raise RuntimeError(f"GQSP angle finding failed (max error {err:.2e})")
    return thetas, phis, lam


def gqsp_response(thetas, phis, lam, z) -> complex:
    """<0| GQSP sequence |0> when the controlled operator has eigenvalue z."""
    v = gqsp_rotation(thetas[0], phis[0], lam) @ np.array([1, 0])
    for th, ph in zip(thetas[1:], phis[1:]):
        v = gqsp_rotation(th, ph) @ (np.array([z, 1]) * v)
    return v[0]


def gqsp_hamsim_polynomial(tau: float, d: int, scale: float) -> np.ndarray:
    """Coefficients of P(z) = scale * z^d * sum_{k=-d}^{d} i^k J_k(tau) z^k.

    On the walk operator, whose eigenvalues are z = e^{i w} with cos w = -x,
    the Laurent part equals e^{i tau cos w} = e^{-i tau x}, i.e. e^{-iHt}.
    The extra z^d is removed in the circuit by d calls of W^dagger.
    """
    k = np.arange(-d, d + 1)
    return scale * (1j ** k) * jv(k, tau)