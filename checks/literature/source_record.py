"""
literature/source_record — an imported result names its source, the exact form used, and its conventions.

What it checks
    That a result taken from the literature, not proved here, is recorded well enough to audit: the node's
    source: gives a citation, the exact form of the result as used, and how the source's conventions map to
    ours. Its trust boundary is then visible: every node that rests on it lists it in its frontier.

How it works
    Reads the node's source: record and checks which of citation, exact_form and convention_map are present.

Parameters
    (none)

Passes when
    citation and exact_form are present (a missing convention_map is noted in the summary; the node's
    faithfulness requires it separately).

Fails when
    citation or exact_form is missing.

Grants
    assumed, never proved.

Example
    - test: literature/source_record
"""

from __future__ import annotations

from checks._framework import Result

PARAMS = {}
REQUIRED = []


def run(node, params, ctx):
    src = node.source or {}
    missing = [f for f in ("citation", "exact_form", "convention_map") if not src.get(f)]
    ev = {"citation": src.get("citation"), "url": src.get("url"),
          "exact_form": bool(src.get("exact_form")), "convention_map": bool(src.get("convention_map"))}
    if "citation" in missing or "exact_form" in missing:
        return Result("fail", None, None, summary=f"source record incomplete: missing {missing}", evidence=ev)
    note = "" if not missing else f" (missing {missing})"
    return Result("pass", "assumed", "as stated in the source", summary=f"imported from {src['citation']}{note}", evidence=ev)
