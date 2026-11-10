"""
vocabulary/vetted_constants — every constant in the Lean statement comes from core Lean or a vetted node.

What it checks
    That the statement of the node's Lean theorem (its type, not its proof) uses only constants from core Lean
    (an Init.* module) or from the Lean names of definition and assumption nodes. A statement that passes
    inherits most of its faithfulness from those definitions, which a person reviews once.

How it works
    1. Inspects the node's declaration (checks/_shared/lean.py) and lists the constants in its type.
    2. Skips those from Init.* modules.
    3. Looks up the node that owns each remaining constant (longest matching Lean name or namespace), keeping
       only definition and assumption nodes.

Parameters
    (none)

Passes when
    Every constant is from core Lean or a definition or assumption node; the evidence lists which nodes.

Fails when
    The declaration is missing, or some constant belongs to no definition or assumption node (an unvetted
    word in the statement).

Grants
    tested (faithfulness): the statement is written in reviewed vocabulary.

Example
    - test: vocabulary/vetted_constants
"""

from __future__ import annotations

from checks._framework import Result
from checks._shared.lean import LeanUnavailable, inspect, node_prefixes, owner

PARAMS = {}
REQUIRED = []


def applies_to(node):
    return bool(node.lean_decl)


def run(node, params, ctx):
    try:
        info = inspect(ctx).get(node.lean_decl)
    except LeanUnavailable as e:
        return Result("error", summary=str(e))
    if info is None or info.get("missing"):
        return Result("fail", summary=f"{node.lean_decl} not found")
    prefixes = {p: nid for p, nid in node_prefixes(ctx.dag).items()
                if ctx.dag.nodes[nid].kind in ("definition", "assumption")}
    used, unvetted = {}, []
    for c in info["type_consts"]:
        if c["module"].startswith("Init"):
            continue
        nid = owner(c["name"], prefixes)
        if nid is None:
            unvetted.append(c["name"])
        else:
            used.setdefault(nid, []).append(c["name"])
    ev = {"vetted_nodes": {k: sorted(v) for k, v in used.items()}, "unvetted": sorted(unvetted)}
    if unvetted:
        return Result("fail", summary=f"statement uses unvetted constants: {', '.join(sorted(unvetted))}", evidence=ev)
    return Result("pass", summary=f"statement uses only core Lean and {len(used)} vetted node(s): "
                                  f"{', '.join(sorted(used)) or 'none'}", evidence=ev)
