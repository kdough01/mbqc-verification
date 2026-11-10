"""
conventions.py — every edge's two ends must agree on conventions, or the edge
must name converters (mbqc_verify.conventions.CONVERTERS) that bridge each
disagreement. `variant_of` edges are reported as information: comparing a claim
with its variant under different conventions is exactly where "degree" bugs hide.
"""

from __future__ import annotations

from mbqc_verify.conventions import CONVERTERS


def edge_conflicts(dag) -> list[tuple]:
    """(edge, {axis: (parent value, child value)}) for edges whose disagreements aren't bridged."""
    out = []
    for e in dag.edges:
        conflicts = dag.nodes[e.src].conventions.conflicts(dag.nodes[e.dst].conventions)
        bridged: dict[str, set[str]] = {}
        for c in e.convert:
            axis, a, b = CONVERTERS[c]
            bridged.setdefault(axis, set()).update({a, b})
        left = {ax: v for ax, v in conflicts.items() if not (ax in bridged and set(v) <= bridged[ax])}
        if left:
            out.append((e, left))
    return out
