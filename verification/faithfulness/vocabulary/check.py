"""
check.py — vocabulary: does the statement only use vetted words?

Every constant in the Lean statement's type must come from core Lean (an
`Init.*` module) or from a definition or assumption node's Lean names. A node
that passes inherits most of its faithfulness from those definitions, which a
person reviews once.
"""

from __future__ import annotations

from verification.base import Check, CheckResult, register
from verification.truth.lean.leanrun import LeanUnavailable, inspect, node_prefixes, owner


@register
class VocabularyCheck(Check):
    kind = "vocabulary"

    def applies_to(self, node):
        return bool(node.lean_decl)

    def run(self, node, params, ctx):
        try:
            info = inspect(ctx).get(node.lean_decl)
        except LeanUnavailable as e:
            return CheckResult("error", summary=str(e))
        if info is None or info.get("missing"):
            return CheckResult("fail", summary=f"{node.lean_decl} not found")
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
            return CheckResult("fail", summary=f"statement uses unvetted constants: {', '.join(sorted(unvetted))}",
                               evidence=ev)
        return CheckResult("pass", summary=f"statement uses only core Lean and {len(used)} vetted node(s): "
                                           f"{', '.join(sorted(used)) or 'none'}", evidence=ev)
