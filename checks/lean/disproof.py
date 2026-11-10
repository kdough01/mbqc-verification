"""
lean/disproof — Lean proves the node's claim false.

What it checks
    That the declaration the node names (lean_decl) is a theorem stating the negation of the node's claim,
    `¬ claim`, and that Lean accepts it from standard axioms and declared assumptions only.

How it works
    1. Builds and inspects the Lean project, as lean/proof does.
    2. Reads `#print axioms` for the disproof and sorts the axioms the same way.
    3. A disproof that rests on assumption axioms refutes the claim modulo those assumptions (for example the
       Layer B formulas it evaluates); the summary names them.
    Writing the negation is the author's job: a reviewer checks that the Lean statement is the negation of
    the node's statement, as for any Lean statement.

Parameters
    (none)

Passes when
    Never: a disproof that Lean accepts makes this test fail with the claim refuted.

Fails when
    Lean accepts the disproof (refuted), or the disproof does not count: missing, not a theorem, uses sorry,
    or rests on an undeclared axiom (a plain failure, no verdict on the claim).

Grants
    refuted, labelled "Disproved in Lean".

Example
    - test: lean/disproof
"""

from __future__ import annotations

from checks._framework import Result
from checks._shared.lean import LeanUnavailable

from ._axioms import read

PARAMS = {}
REQUIRED = []


def applies_to(node):
    return bool(node.lean_decl)


def run(node, params, ctx):
    try:
        info, ev = read(node, ctx)
    except LeanUnavailable as e:
        return Result("error", summary=str(e))
    if info is None:
        return Result("fail", summary=f"{node.lean_decl} not found in the Lean project")
    if info["kind"] != "theorem":
        return Result("fail", summary=f"{node.lean_decl} is a {info['kind']}, not a theorem")
    bad = ev.pop("undeclared_axioms")
    if "sorryAx" in ev["axioms"]:
        return Result("fail", summary="the proof uses sorry", evidence=ev)
    if bad:
        return Result("fail", summary=f"undeclared axioms: {', '.join(bad)}", evidence=ev)
    extra, nodes = ev["assumption_axioms"], ev["assumption_nodes"]
    modulo = f" modulo {len(extra)} assumption axiom(s) of {', '.join(nodes)}" if extra else ""
    return Result("fail", "refuted", "the claim as stated",
                  summary=f"Lean proves the claim false{modulo} ({node.lean_decl})", evidence=ev)
