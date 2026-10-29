"""
check.py — lean: is the node's Lean declaration proved, and from which axioms?

Builds the Lean project, then reads `#print axioms` for the node's `lean_decl`.
    only propext / Quot.sound / Classical.choice         -> proved
    plus axioms under MBQC.Assumptions.* (named in an
    assumption node's lean_decl)                          -> proved_modulo
    sorryAx or any other axiom                            -> fail
The evidence also records which other nodes' declarations the proof reaches
(graph/edges uses this instead of the declared edges once a proof exists).
"""

from __future__ import annotations

from verification.base import Check, CheckResult, register

from .leanrun import ASSUMPTION_NAMESPACE, STANDARD_AXIOMS, LeanUnavailable, inspect, node_prefixes, owner


@register
class LeanCheck(Check):
    kind = "lean"

    def applies_to(self, node):
        return bool(node.lean_decl)

    def run(self, node, params, ctx):
        try:
            info = inspect(ctx).get(node.lean_decl)
        except LeanUnavailable as e:
            return CheckResult("error", summary=str(e))
        if info is None or info.get("missing"):
            return CheckResult("fail", summary=f"{node.lean_decl} not found in the Lean project")
        if info["kind"] != "theorem":
            return CheckResult("fail", summary=f"{node.lean_decl} is a {info['kind']}, not a theorem")
        prefixes = node_prefixes(ctx.dag)
        axioms = sorted(info["axioms"])
        extra = [a for a in axioms if a not in STANDARD_AXIOMS]
        bad = [a for a in extra if not a.startswith(ASSUMPTION_NAMESPACE) or owner(a, prefixes) is None]
        deps = sorted({owner(p, prefixes) for p in info["node_deps"]} - {None, node.id})
        assumption_nodes = sorted({owner(a, prefixes) for a in extra if owner(a, prefixes)})
        ev = {"decl": node.lean_decl, "module": info["module"], "axioms": axioms,
              "assumption_axioms": extra, "assumption_nodes": assumption_nodes, "node_deps": deps}
        if "sorryAx" in axioms:
            return CheckResult("fail", summary="the proof uses sorry", evidence=ev)
        if bad:
            return CheckResult("fail", summary=f"undeclared axioms: {', '.join(bad)}", evidence=ev)
        if extra:
            return CheckResult("pass", "proved_modulo", "all values in the statement",
                               frontier=assumption_nodes,
                               summary=f"proved in Lean from {len(extra)} assumption axiom(s) of "
                                       f"{', '.join(assumption_nodes)}", evidence=ev)
        return CheckResult("pass", "proved", "all values in the statement",
                           summary="proved in Lean; axioms: " + ", ".join(axioms or ["none"]), evidence=ev)
