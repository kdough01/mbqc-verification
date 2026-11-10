"""
symbolic/slide_positivity — QSVT − GQSP is a polynomial with nonnegative coefficients, so it is positive.

What it checks
    The slide's claim with the slide's own formulas: for n ≥ 2 and odd d ≥ g ≥ 3, QSVT's count (N, E or M)
    exceeds GQSP's.

How it works
    1. Substitutes n = 2 + p and d = g + 2k (p, k ≥ 0) into QSVT − GQSP (checks/symbolic/_certificate.py).
    2. Splits g by residue mod 4, because the slide's E_G has χ = [g ≡ 1 mod 4] and η = [g = 3]: g = 3,
       g = 7 + 4q, g = 5 + 4q (q ≥ 0).
    3. Expands each case with sympy into a polynomial in p, q, k ≥ 0. If every coefficient is ≥ 0 and the
       constant term is > 0, it is positive for all allowed values.
    The certificate (the list of polynomials) is in the evidence, checkable by anyone, so sympy need not be
    trusted.

Parameters
    quantity    N | E | M

Passes when
    Every case's polynomial has nonnegative coefficients and a positive constant term.

Fails when
    Some case has a negative coefficient. That only means this certificate was not found; the claim may
    still hold.

Grants
    empirical: it stays below proved until a Lean proof checks the same certificate.

Example
    - test: symbolic/slide_positivity
      params: {quantity: N}
"""

from __future__ import annotations

from checks._framework import Result

from ._certificate import certificate

PARAMS = {"quantity": {"enum": ["N", "E", "M"]}}
REQUIRED = ["quantity"]


def run(node, params, ctx):
    cert = certificate(params["quantity"])
    ok = all(c["certifies_positive"] for c in cert)
    domain = "all n >= 2 and odd d >= g >= 3"
    if ok:
        return Result("pass", "empirical", domain,
                      summary=f"QSVT - GQSP is a positive-coefficient polynomial in all {len(cert)} cases",
                      evidence={"certificate": cert})
    return Result("fail", None, domain, summary="positivity certificate not found (the claim may still hold)",
                  evidence={"certificate": cert})
