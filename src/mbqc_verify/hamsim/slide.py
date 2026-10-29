"""
slide.py — the claims of the slide "Hamiltonian simulation: explicit costs and
trade-offs" (docs/img/hamsim_slide.png), written down as data.

These are the statements under test, not results: nothing here is computed.
Symbols follow the slide: n data qubits (n >= 2), QSVT degree d and GQSP degree
g, both odd and >= 3. The slide does not define its degrees relative to ours
(see mbqc_verify.conventions.Degree.SLIDE_POLYNOMIAL_DEGREE).
"""

from __future__ import annotations

import sympy as sp

# Vertex formulas as (a, b, c, e):  N = (a n + b) * degree + c n + e
SLIDE_N = {
    "qsvt": (36, -18, 14, 23),
    "gqsp": (12, -6, 32, -11),
}

n, d, g = sp.symbols("n d g", integer=True, positive=True)
chi, eta = sp.symbols("chi eta", integer=True, nonnegative=True)   # chi = [g = 1 mod 4], eta = [g = 3]

N_Q = (36 * n - 18) * d + 14 * n + 23
N_G = (12 * n - 6) * g + 32 * n - 11
E_Q = (168 * n - 102) * d + 45 * n + 185
E_G = (124 * n - 116) * g + (122 - chi) * n - 40 + 3 * chi - eta
M_Q = N_Q - n
M_G = N_G - n

# The three quantities the slide's d >= g claim compares, as (QSVT, GQSP).
SLIDE_PAIRS = {
    "N": (N_Q, N_G),
    "E": (E_Q, E_G),
    "M": (M_Q, M_G),
}
