"""
nonvacuity/witness — a witness theorem shows the Lean theorem's hypotheses can all hold at once.

What it checks
    That the theorem is not vacuous: its hypotheses are jointly satisfiable. The classic failure of a
    generated statement is a hypothesis that quietly makes it trivial (for example 2 ≤ n and n < 2).

How it works
    1. Reads the main theorem's hypotheses as Lean prints them.
    2. Reads the witness theorem, which must state ∃ x…, H1 ∧ … ∧ Hk.
    3. Compares the witness's conjuncts with the hypotheses (whitespace-normalized, as printed), and checks
       the witness uses standard axioms only.

Parameters
    witness     the Lean name of the witness theorem (omit when the theorem has no hypotheses)

Passes when
    The theorem has no hypotheses, or the witness proves exactly its hypotheses together from standard axioms.

Fails when
    Hypotheses but no witness, a missing witness, a witness whose conjuncts differ from the hypotheses, or a
    witness that relies on non-standard axioms.

Grants
    tested (faithfulness).

Example
    - test: nonvacuity/witness
      params: {witness: MBQC.Results.HamSim.qsvt_unopt_nonvacuous}
"""

from __future__ import annotations

from checks._framework import Result
from checks._shared.lean import STANDARD_AXIOMS, LeanUnavailable, inspect

PARAMS = {"witness": {"type": "string"}}
REQUIRED = []


def _norm(s: str) -> str:
    return " ".join(s.split())


def applies_to(node):
    return bool(node.lean_decl)


def run(node, params, ctx):
    try:
        info = inspect(ctx)
    except LeanUnavailable as e:
        return Result("error", summary=str(e))
    main = info.get(node.lean_decl)
    if main is None or main.get("missing"):
        return Result("fail", summary=f"{node.lean_decl} not found")
    hyps = sorted(_norm(h) for h in main["hypotheses"])
    if not hyps:
        return Result("pass", summary="the theorem has no hypotheses", evidence={"hypotheses": []})
    w = params.get("witness")
    if not w:
        return Result("fail", summary=f"{len(hyps)} hypotheses but no witness named", evidence={"hypotheses": hyps})
    wi = info.get(w)
    if wi is None or wi.get("missing"):
        return Result("fail", summary=f"witness {w} not found")
    conj = sorted(_norm(c) for c in wi["conjuncts"])
    ev = {"hypotheses": hyps, "witness": w, "witness_conjuncts": conj, "witness_axioms": wi["axioms"]}
    if set(wi["axioms"]) - STANDARD_AXIOMS:
        return Result("fail", summary="the witness relies on non-standard axioms", evidence=ev)
    if conj != hyps:
        return Result("fail", summary="the witness does not state exactly the theorem's hypotheses", evidence=ev)
    return Result("pass", summary=f"all {len(hyps)} hypotheses hold together ({w})", evidence=ev)
