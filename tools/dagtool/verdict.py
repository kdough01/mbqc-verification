"""
verdict.py — the one-word answer the review site shows for a claim: open, verified or rejected.

It is derived from the computed status (status.py), never written by hand:

    rejected   a check refuted it (refuted), or the claim rests on a refuted one (broken); `label` says how, from
               the kind of check that refuted it ("Does not pass scaling tests", "Does not reproduce", ...), and
               `explain` what that does and does not mean
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
# Why an open paper theorem is still open, from the outcome a proposal recorded (proposals.py)
OPEN_REASONS = {
    "unproved": "a proposal stated it in Lean but did not prove it yet (see notes)",
    "not-formalizable": "the vetted definitions cannot express it yet (see notes)",
    "counterexample-suspected": "a proposal reports it may be false; a person should check (see notes)",
}


# How a claim fails, by the kind of check that refuted it, most decisive first. A scaling or reproduction failure is
# not a proof that the claim is false: the label and explanation say what was actually observed.
REJECTION = [
    ("refuter", "Counterexample found",
     "a counterexample search found an instance where the claim fails"),
    ("finite", "Fails on a checked case",
     "an exhaustive check over a stated finite domain found a case where it fails"),
    ("symbolic", "Fails symbolic check",
     "computer algebra shows the identity does not hold as stated"),
    ("numerical", "Fails numerical check",
     "a numerical computation disagrees with the claim beyond its tolerance"),
    ("translation", "Compiled pattern differs from its circuit",
     "the MBQC pattern does not implement the circuit on the inputs checked"),
    ("tool", "An independent tool disagrees",
     "a pinned external tool computes a different value"),
    ("reproduction", "Does not reproduce",
     "a recorded run of the pinned pipeline gives a value outside the tolerance of the paper's number; the "
     "difference can come from unstated settings rather than an error in the paper"),
    ("scaling", "Does not pass scaling tests",
     "the measured growth does not fit the claimed form at the sizes tested; an asymptotic claim can still hold "
     "with a large constant factor, or only beyond the largest size measured"),
    ("literature", "Contradicted by the literature",
     "a cited source states something incompatible with the claim"),
]
REJECTION_LABEL = {k: (label, why) for k, label, why in REJECTION}


def rejection(kinds: list[str]) -> tuple[str, str]:
    """(label, explanation) for a claim refuted by these check kinds; the most decisive kind names it."""
    for k, label, why in REJECTION:
        if k in kinds:
            others = [REJECTION_LABEL[o][0].lower() for o in kinds if o != k and o in REJECTION_LABEL]
            return label, why + (f" (also: {', '.join(others)})" if others else "")
    return "Refuted by a check", "a check refuted it"


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
        label, why = rejection(refuters)
        return {"state": "rejected", **out, "methods": refuters or methods, "reason": why, "label": label,
                "explain": why}
    if s.broken:
        bad = sorted(a for a in ancestors if st[a].eff_truth == "refuted")
        how = sorted({rejection(sorted({e.kind for e in st[a].evidence if e.fresh and e.grants == "refuted"}))[0]
                      for a in bad})
        why = "relies on a claim that " + (", ".join(h.lower() for h in how) if how else "was refuted")
        return {"state": "rejected", **out, "reason": why + (f": {', '.join(bad)}" if bad else ""),
                "label": "Relies on a claim that does not pass", "explain": why}
    if TRUTH_RANK.get(s.eff_truth, -1) >= TRUTH_RANK["empirical"]:
        return {"state": "verified", **out, "reason": "", "label": "Verified"}
    if methods:
        return {"state": "open", **out, "reason": "its own checks passed, but a claim it uses is not verified yet",
                "label": "Open"}
    for tag, why in OPEN_REASONS.items():
        if tag in dag.nodes[node_id].tags:
            return {"state": "open", **out, "reason": why, "label": "Open"}
    if dag.nodes[node_id].raw.get("paper") and not dag.nodes[node_id].checks:
        return {"state": "open", **out, "reason": "waiting for a proposal", "label": "Open"}
    return {"state": "open", **out, "reason": "no passing check yet", "label": "Open"}
