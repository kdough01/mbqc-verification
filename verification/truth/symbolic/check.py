"""
check.py — symbolic: a computer-algebra certificate for a polynomial inequality.

Node params:
    certificate: slide_d_ge_g
    quantity:    N | E | M

Passes with `empirical` when every case's difference polynomial has nonnegative
coefficients and a positive constant term. It stays `empirical` (not `proved`)
until a Lean check confirms the same certificate.
"""

from __future__ import annotations

from verification.base import Check, CheckResult, register

from .coeff_positivity import certificate


@register
class SymbolicCheck(Check):
    kind = "symbolic"

    def run(self, node, params, ctx):
        if params.get("certificate") != "slide_d_ge_g":
            raise ValueError(f"unknown certificate {params.get('certificate')!r}")
        cert = certificate(params["quantity"])
        ok = all(c["certifies_positive"] for c in cert)
        domain = "all n >= 2 and odd d >= g >= 3"
        if ok:
            return CheckResult("pass", "empirical", domain,
                               summary=f"QSVT - GQSP is a positive-coefficient polynomial in all {len(cert)} cases",
                               evidence={"certificate": cert})
        return CheckResult("fail", None, domain,
                           summary="positivity certificate not found (the claim may still hold)",
                           evidence={"certificate": cert})
