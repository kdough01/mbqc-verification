"""
lean_edges.py — edges extracted from Lean proofs.

Once a node's Lean proof passes, the declarations it actually reaches decide
its parents, not the hand-declared edges: `uses` for other nodes' declarations,
`assumes` for assumption nodes whose axioms appear in `#print axioms`. Declared
edges that the proof does not use, and used declarations with no declared edge,
are flagged (dagtool status).
"""

from __future__ import annotations


def extracted(lean_record: dict, node_id: str) -> list[tuple[str, str]]:
    """[(parent node id, edge kind)] from a passing `lean` evidence record."""
    ev = lean_record.get("result", {}).get("evidence", {})
    out = [(d, "uses") for d in ev.get("node_deps", []) if d != node_id and d not in ev.get("assumption_nodes", [])]
    out += [(a, "assumes") for a in ev.get("assumption_nodes", [])]
    return out
