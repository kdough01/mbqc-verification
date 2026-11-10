"""
equivalence/iff_proof — two separately written formalizations of one claim are provably equivalent.

What it checks
    That a second formalization of the node's claim (the theorem `other`, written separately, for example by
    another proposer or in another style) states the same thing as the main one: a third declaration `proof`
    proves stmt(main) ↔ stmt(other), where stmt(X) is the type of X. Two faithful-looking statements that are
    provably equivalent make a mistranscription in either less likely.

How it works
    1. Inspects proof's type and checks it is exactly type(lean_decl) ↔ type(other) (definitional equality is
       not accepted).
    2. Checks proof is a theorem from standard axioms only.
    3. Checks proof does not reach the proofs of lean_decl or other: with both proved, A ↔ B would follow from
       them trivially, and the equivalence must come from the statements.

Parameters
    other       the Lean name of the second formalization
    proof       the Lean name of the theorem proving the equivalence

Passes when
    All three conditions hold.

Fails when
    proof states something other than main ↔ other exactly, is not a theorem, uses non-standard axioms, or
    reaches either proof.

Grants
    tested (faithfulness).

Limits
    It does not show that either statement says what the paper says; review still decides that.

Example
    - test: equivalence/iff_proof
      name: restated
      params: {other: MBQC.Papers.p_abc.theorem_1.restated, proof: MBQC.Papers.p_abc.theorem_1.restated_iff}
"""

from __future__ import annotations

from checks._framework import Result
from checks._shared.lean import STANDARD_AXIOMS, LeanUnavailable, inspect

PARAMS = {"other": {"type": "string"}, "proof": {"type": "string"}}
REQUIRED = ["other", "proof"]


def applies_to(node):
    return bool(node.lean_decl)


def run(node, params, ctx):
    other, proof = params["other"], params["proof"]
    try:
        r = inspect(ctx).get(f"iff:{node.lean_decl}|{other}|{proof}")
    except LeanUnavailable as e:
        return Result("error", summary=str(e))
    if r is None or r.get("missing"):
        return Result("fail", summary=f"{(r or {}).get('missing') or 'a declaration'} not found in the Lean project")
    ev = {"main": node.lean_decl, "other": other, "proof": proof, "type_equal": r.get("type_equal"),
          "definitionally_equal": r.get("defeq"), "axioms": r.get("axioms"), "uses": r.get("uses"), "note": r.get("note")}
    if not r.get("type_equal"):
        why = " (only definitionally)" if r.get("defeq") else ""
        return Result("fail", summary=f"{proof} does not state {node.lean_decl} ↔ {other} exactly{why}"
                      + (f": {r['note']}" if r.get("note") else ""), evidence=ev)
    if r.get("kind") != "theorem":
        return Result("fail", summary=f"{proof} is a {r.get('kind')}, not a theorem", evidence=ev)
    if set(r.get("axioms") or []) - STANDARD_AXIOMS:
        return Result("fail", summary=f"{proof} uses non-standard axioms: {sorted(set(r['axioms']) - STANDARD_AXIOMS)}",
                      evidence=ev)
    if r.get("uses"):
        return Result("fail", summary=f"{proof} reaches the proof of {', '.join(r['uses'])}: the equivalence must "
                                      "follow from the statements, not from both being proved", evidence=ev)
    return Result("pass", summary=f"{node.lean_decl} ↔ {other} proved ({proof}) without either proof", evidence=ev)
