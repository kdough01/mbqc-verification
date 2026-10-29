"""
coeff_positivity.py — a positivity certificate for "QSVT costs more than GQSP".

Moved here from ham_sim.py prove_slide_claim(). For the slide's formulas, with
n >= 2 and odd d >= g >= 3: substitute n = 2 + p, d = g + 2k (p, k >= 0) and split
g by residue mod 4 (the slide's E_G has chi = [g = 1 mod 4], eta = [g = 3]):
g = 3, g = 7 + 4q, g = 5 + 4q (q >= 0). In each case QSVT - GQSP becomes a
polynomial in p, q, k >= 0. If every coefficient is >= 0 and the constant term
is > 0, it is positive for all allowed values.

The certificate is the list of those polynomials. It is checkable by anyone
(and, in wave 3, by Lean's `positivity`), so sympy does not have to be trusted.
"""

from __future__ import annotations

import sympy as sp

from mbqc_verify.hamsim.slide import SLIDE_PAIRS, chi, d, eta, g, n

p, q, k = sp.symbols("p q k", integer=True, nonnegative=True)

CASES = [  # (g substitution, chi, eta, description)
    (sp.Integer(3), 0, 1, "g = 3"),
    (7 + 4 * q, 0, 0, "g = 7 + 4q  (g = 3 mod 4, g >= 7)"),
    (5 + 4 * q, 1, 0, "g = 5 + 4q  (g = 1 mod 4)"),
]


def certificate(quantity: str) -> list[dict]:
    """One entry per case: the difference polynomial, its coefficients, and whether it certifies > 0."""
    QSVT, GQSP = SLIDE_PAIRS[quantity]
    out = []
    for gs, c, e, label in CASES:
        diff = (QSVT - GQSP).subs({chi: c, eta: e}).subs({d: g + 2 * k}).subs({g: gs, n: 2 + p})
        poly = sp.Poly(sp.expand(diff), p, q, k)
        coeffs = {str(m): int(cf) for m, cf in zip(poly.monoms(), poly.coeffs())}
        const = coeffs.get("(0, 0, 0)", 0)
        ok = const > 0 and all(cf >= 0 for cf in coeffs.values())
        out.append({"case": label, "difference": str(poly.as_expr()), "coefficients": coeffs,
                    "certifies_positive": ok})
    return out
