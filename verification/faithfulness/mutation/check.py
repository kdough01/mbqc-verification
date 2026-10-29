"""
check.py — mutation: a faithful statement should break when perturbed.

If a formula still "passes" after a coefficient changes, the check behind it is
too weak to tell the difference, and the statement's evidence means less than
it seems. This catches vacuous checks and over-loose statements early.

Node params:
    target: scaling   Perturb each coefficient of the node's scaling formula by
                      +1 and -1 (8 mutants) and re-run the scaling comparison on
                      the same counts. Every mutant must be rejected.

(Lean statement mutation, design doc wave 3, will add target: lean.)
"""

from __future__ import annotations

from verification.base import Check, CheckResult, register
from verification.truth.scaling.grids import counts, mismatches


@register
class MutationCheck(Check):
    kind = "mutation"

    def applies_to(self, node):
        return any(c.kind == "scaling" and c.params.get("claim", "formula") == "formula" for c in node.checks)

    def run(self, node, params, ctx):
        if params.get("target", "scaling") != "scaling":
            raise ValueError(f"unknown mutation target {params.get('target')!r}")
        spec = next(c for c in node.checks if c.kind == "scaling")
        sp = spec.params
        data = counts(sp["method"], bool(sp["optimize"]), ctx.quick, ctx.cache)
        base = [str(c) for c in sp["coef"]]
        if mismatches(base, data, sp["quantity"]):
            return CheckResult("skip", summary="the unmutated formula already fails; nothing to compare")
        rows, survivors = [], []
        names = ("a (n*k)", "b (k)", "c (n)", "e (const)")
        for i in range(4):
            for delta in (1, -1):
                mutant = list(sp["coef"])
                mutant[i] = _shift(mutant[i], delta)
                miss = mismatches(mutant, data, sp["quantity"])
                rows.append({"mutant": f"{names[i]} {'+' if delta > 0 else '-'}1", "coef": [str(c) for c in mutant],
                             "rejected": bool(miss), "first_mismatch": miss[0] if miss else None})
                if not miss:
                    survivors.append(rows[-1]["mutant"])
        if survivors:
            return CheckResult("fail", summary=f"{len(survivors)} mutant(s) survived: {', '.join(survivors)}",
                               evidence={"mutants": rows})
        return CheckResult("pass", summary=f"all {len(rows)} coefficient mutants rejected", evidence={"mutants": rows})


def _shift(c, delta):
    from fractions import Fraction
    v = Fraction(str(c)) + delta
    return int(v) if v.denominator == 1 else str(v)
