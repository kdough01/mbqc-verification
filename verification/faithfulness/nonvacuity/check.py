"""
check.py — nonvacuity: can the theorem's hypotheses all hold at once?

The classic failure of a generated statement is a hypothesis that quietly makes
it trivial. The node names a witness theorem `∃ x…, H1 ∧ … ∧ Hk`; this check
requires that the witness is proved with standard axioms only and that its
conjuncts are exactly the main theorem's hypotheses (compared as printed by Lean).

Node params: witness: <Lean name>   (omit for a theorem with no hypotheses)
"""

from __future__ import annotations

from verification.base import Check, CheckResult, register
from verification.truth.lean.leanrun import STANDARD_AXIOMS, LeanUnavailable, inspect


def _norm(s: str) -> str:
    return " ".join(s.split())


@register
class NonvacuityCheck(Check):
    kind = "nonvacuity"

    def applies_to(self, node):
        return bool(node.lean_decl)

    def run(self, node, params, ctx):
        try:
            info = inspect(ctx)
        except LeanUnavailable as e:
            return CheckResult("error", summary=str(e))
        main = info.get(node.lean_decl)
        if main is None or main.get("missing"):
            return CheckResult("fail", summary=f"{node.lean_decl} not found")
        hyps = sorted(_norm(h) for h in main["hypotheses"])
        if not hyps:
            return CheckResult("pass", summary="the theorem has no hypotheses", evidence={"hypotheses": []})
        w = params.get("witness")
        if not w:
            return CheckResult("fail", summary=f"{len(hyps)} hypotheses but no witness named",
                               evidence={"hypotheses": hyps})
        wi = info.get(w)
        if wi is None or wi.get("missing"):
            return CheckResult("fail", summary=f"witness {w} not found")
        conj = sorted(_norm(c) for c in wi["conjuncts"])
        ev = {"hypotheses": hyps, "witness": w, "witness_conjuncts": conj, "witness_axioms": wi["axioms"]}
        if set(wi["axioms"]) - STANDARD_AXIOMS:
            return CheckResult("fail", summary="the witness relies on non-standard axioms", evidence=ev)
        if conj != hyps:
            return CheckResult("fail", summary="the witness does not state exactly the theorem's hypotheses",
                               evidence=ev)
        return CheckResult("pass", summary=f"all {len(hyps)} hypotheses hold together ({w})", evidence=ev)
