"""
verdict.py — the one-word answer the review site shows for a claim: open, verified or rejected.

It is derived from the computed status (status.py), never written by hand:

    rejected   a counterexample exists (refuted), or the claim rests on one (broken)
    verified   effective truth is at least `empirical`; `methods` lists the check kinds whose
               fresh evidence passed (lean, scaling, numerical, ...), so "verified" always says how
    open       anything else: no evidence yet, or its own evidence passed but a parent it uses is unverified

`core_support` counts the definition, core and transfer nodes a claim rests on (its ancestors over
trust-carrying edges): the more of a new theorem that goes through the reviewed core, the less of it
needs new trust.
"""

from __future__ import annotations

from verification.kinds import TRUTH_RANK

from .model import Dag
from .status import NodeStatus

FOUNDATION_KINDS = ("definition", "core", "transfer")


def methods_of(s: NodeStatus) -> list[str]:
    return sorted({e.kind for e in s.evidence
                   if e.question == "truth" and e.fresh and e.outcome == "pass" and e.grants and e.grants != "refuted"})


def verdict(dag: Dag, node_id: str, st: dict[str, NodeStatus]) -> dict:
    s = st[node_id]
    methods = methods_of(s)
    ancestors = dag.ancestors(node_id)
    core = sorted(a for a in ancestors if dag.nodes[a].kind in FOUNDATION_KINDS)
    out = {"level": s.display_truth, "methods": methods, "stale": bool(s.stale or s.upstream_stale),
           "core_support": len(core), "core_nodes": core, "faithfulness": s.eff_faith}
    if s.eff_truth == "refuted" or s.own_truth == "refuted":
        refuters = sorted({e.kind for e in s.evidence if e.fresh and e.grants == "refuted"})
        return {"state": "rejected", **out, "methods": refuters or methods, "reason": "a counterexample exists"}
    if s.broken:
        bad = sorted(a for a in ancestors if st[a].eff_truth == "refuted")
        return {"state": "rejected", **out, "reason": "relies on a refuted claim" + (f": {', '.join(bad)}" if bad else "")}
    if TRUTH_RANK.get(s.eff_truth, -1) >= TRUTH_RANK["empirical"]:
        return {"state": "verified", **out, "reason": ""}
    if methods:
        return {"state": "open", **out, "reason": "its own checks passed, but a claim it uses is not verified yet"}
    return {"state": "open", **out, "reason": "no passing check yet"}
