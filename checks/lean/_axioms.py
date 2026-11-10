"""
_axioms.py — read `#print axioms` for a node's main declaration and sort the axioms it rests on.

Standard axioms (propext, Quot.sound, Classical.choice) are fine. Axioms under MBQC.Assumptions.* are fine
when an assumption node names them in its lean_decl: they are that node's stated assumptions. Anything else
(sorryAx, an axiom no node owns) means the proof does not count.
"""

from __future__ import annotations

from checks._shared.lean import ASSUMPTION_NAMESPACE, STANDARD_AXIOMS, inspect, node_prefixes, owner


def read(node, ctx) -> tuple[dict | None, dict]:
    """(Lean's record of the declaration or None, evidence: axioms, assumption axioms and nodes, node deps)."""
    info = inspect(ctx).get(node.lean_decl)
    if info is None or info.get("missing"):
        return None, {}
    axioms = sorted(info["axioms"])
    extra = [a for a in axioms if a not in STANDARD_AXIOMS]
    prefixes = node_prefixes(ctx.dag)
    bad = [a for a in extra if not a.startswith(ASSUMPTION_NAMESPACE) or owner(a, prefixes) is None]
    deps = sorted({owner(p, prefixes) for p in info["node_deps"]} - {None, node.id})
    assumption_nodes = sorted({owner(a, prefixes) for a in extra if owner(a, prefixes)})
    return info, {"decl": node.lean_decl, "module": info["module"], "axioms": axioms, "assumption_axioms": extra,
                  "assumption_nodes": assumption_nodes, "node_deps": deps, "undeclared_axioms": bad}
