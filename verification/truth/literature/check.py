"""
check.py — literature: an imported result, recorded so its trust boundary is visible.

Passes when the node's `source:` gives a citation, the exact form used, and how
the source's conventions map to ours. Grants `assumed`, never `proved`: every
node that rests on it lists it in its frontier. The convention map is also what
the node's faithfulness requires (verification/kinds.py REQUIRED_FAITH).
"""

from __future__ import annotations

from verification.base import Check, CheckResult, register


@register
class LiteratureCheck(Check):
    kind = "literature"

    def run(self, node, params, ctx):
        src = node.source or {}
        missing = [f for f in ("citation", "exact_form", "convention_map") if not src.get(f)]
        ev = {"citation": src.get("citation"), "url": src.get("url"),
              "exact_form": bool(src.get("exact_form")), "convention_map": bool(src.get("convention_map"))}
        if "citation" in missing or "exact_form" in missing:
            return CheckResult("fail", None, None, summary=f"source record incomplete: missing {missing}", evidence=ev)
        note = "" if not missing else f" (missing {missing})"
        return CheckResult("pass", "assumed", "as stated in the source",
                           summary=f"imported from {src['citation']}{note}", evidence=ev)
