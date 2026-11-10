"""
lean/proof — the node's Lean theorem is proved from standard axioms and the assumptions it declares.

What it checks
    That the declaration the node names (lean_decl) is a theorem Lean accepts, and which axioms it rests on.
    Proved from standard axioms only, it is proved; proved also from axioms of assumption nodes, it is proved
    modulo those assumptions, and they become the node's frontier.

How it works
    1. Builds the Lean project once per run (lake build MBQC) and inspects every node's declaration
       (lean/scripts/Inspect.lean).
    2. Reads `#print axioms` for this declaration. Standard axioms: propext, Quot.sound, Classical.choice.
       Assumption axioms: names under MBQC.Assumptions.* that an assumption node lists in its lean_decl.
    3. Records which other nodes' declarations the proof reaches. Once the proof passes, those decide the
       node's parents in the DAG (dagtool flags declared edges the proof does not use, and the reverse).

Parameters
    (none)

Passes when
    The declaration is a theorem whose axioms are standard or declared assumptions.

Fails when
    The declaration is missing or not a theorem, the proof uses sorry, or it rests on an axiom no assumption
    node declares.

Grants
    proved, or proved_modulo the assumption nodes it uses.

See also
    lean/disproof for a theorem that proves the node's claim false.

Example
    - test: lean/proof
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
    if extra:
        return Result("pass", "proved_modulo", "all values in the statement", frontier=nodes,
                      summary=f"proved in Lean from {len(extra)} assumption axiom(s) of {', '.join(nodes)}", evidence=ev)
    return Result("pass", "proved", "all values in the statement",
                  summary="proved in Lean; axioms: " + ", ".join(ev["axioms"] or ["none"]), evidence=ev)
