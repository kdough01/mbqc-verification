"""
check.py — equivalence: two independent formalizations of one claim are provably equivalent.

A second formalization (written separately, e.g. by another proposer or in another style) states the same claim
as a theorem `other`; a third declaration `proof` proves  stmt(main) ↔ stmt(other)  where stmt(X) is the type of
X. The check passes when
    proof's type is exactly  type(lean_decl) ↔ type(other)  (definitional equality is not accepted),
    proof is a theorem from standard axioms only, and
    proof does not reach the proofs of lean_decl or other (with both proved, A ↔ B would follow from them
    trivially; the equivalence must come from the statements).
Two faithful-looking statements that are provably equivalent make a mistranscription in either less likely.
What it does not show: that either statement says what the paper says (review still decides that).

Node params: other: <Lean name>   proof: <Lean name>
"""

from __future__ import annotations

from verification.base import Check, CheckResult, register
from verification.truth.lean.leanrun import STANDARD_AXIOMS, LeanUnavailable, inspect


@register
class EquivalenceCheck(Check):
    kind = "equivalence"

    def applies_to(self, node):
        return bool(node.lean_decl)

    def run(self, node, params, ctx):
        other, proof = params.get("other"), params.get("proof")
        if not other or not proof:
            return CheckResult("error", summary="equivalence needs params `other` and `proof`")
        try:
            r = inspect(ctx).get(f"iff:{node.lean_decl}|{other}|{proof}")
        except LeanUnavailable as e:
            return CheckResult("error", summary=str(e))
        if r is None or r.get("missing"):
            return CheckResult("fail", summary=f"{(r or {}).get('missing') or 'a declaration'} not found in the Lean project")
        ev = {"main": node.lean_decl, "other": other, "proof": proof, "type_equal": r.get("type_equal"),
              "definitionally_equal": r.get("defeq"), "axioms": r.get("axioms"), "uses": r.get("uses"),
              "note": r.get("note")}
        if not r.get("type_equal"):
            why = " (only definitionally)" if r.get("defeq") else ""
            return CheckResult("fail", summary=f"{proof} does not state {node.lean_decl} ↔ {other} exactly{why}"
                               + (f": {r['note']}" if r.get("note") else ""), evidence=ev)
        if r.get("kind") != "theorem":
            return CheckResult("fail", summary=f"{proof} is a {r.get('kind')}, not a theorem", evidence=ev)
        if set(r.get("axioms") or []) - STANDARD_AXIOMS:
            return CheckResult("fail", summary=f"{proof} uses non-standard axioms: {sorted(set(r['axioms']) - STANDARD_AXIOMS)}",
                               evidence=ev)
        if r.get("uses"):
            return CheckResult("fail", summary=f"{proof} reaches the proof of {', '.join(r['uses'])}: the equivalence "
                               "must follow from the statements, not from both being proved", evidence=ev)
        return CheckResult("pass", summary=f"{node.lean_decl} ↔ {other} proved ({proof}) without either proof",
                           evidence=ev)
