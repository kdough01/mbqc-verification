"""
status.py — compute every node's status from evidence, reviews and the graph.

Own status comes from the node's own fresh evidence. Effective status then
propagates down the DAG:

  * Effective truth is the weakest truth among the node and the ancestors it
    relies on, except that an ancestor reached by an `assumes` edge, which is an
    `assumption` node, or which is listed in the node's `assumptions:`, does not
    weaken it. Such ancestors join the node's frontier instead, and a proved
    node with a non-empty frontier is `proved_modulo`.
  * `instantiates` edges are a proof route: they only count once the node's own
    truth comes from a proof. Empirical or bounded evidence stands on its own.
  * Once a Lean proof passes, the edges extracted from it replace the declared
    ones for this computation (verification/graph/edges).
  * A refuted ancestor makes the node `broken` (its support is gone).
  * Effective faithfulness is the weakest faithfulness among the node and its
    `definition` / `core` ancestors.
  * Evidence whose input hash no longer matches is stale and does not count;
    the node and its descendants are marked stale until it is re-run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from verification.kinds import (CHECK_KINDS, EXTRA_FOLDERS, FAITH_ORDER, FAITH_RANK, LEAN_KINDS, LEAN_ONLY,
                                REQUIRED_FAITH,
                                TRUTH_ORDER, TRUTH_RANK, clamp_truth)

from .evidence import Review, read_all, read_reviews
from .hashing import input_hash, statement_hash
from .model import Dag, Edge


def check_files(root: Path, kind: str) -> list[Path]:
    """Implementation files of a check kind (hashed into its evidence)."""
    files: list[Path] = []
    for rel in [CHECK_KINDS[kind].folder, *EXTRA_FOLDERS.get(kind, [])]:
        folder = root / "verification" / rel
        files += sorted(p for p in folder.glob("*.py") if p.name != "__init__.py")
    return files


@dataclass
class EvidenceView:
    name: str
    kind: str
    question: str
    outcome: str
    grants: str | None
    domain: str | None
    summary: str
    fresh: bool
    record: dict


@dataclass
class Flag:
    level: str      # warn | info
    code: str       # convention_mismatch | variant_conventions | check_failed | mutation_survived | stale | review_rejected | missing_evidence | edge_mismatch
    message: str


@dataclass
class NodeStatus:
    id: str
    own_truth: str = "conjecture"
    last_truth: str = "conjecture"    # what the evidence says if freshness is ignored (for regression checks)
    own_domain: str | None = None
    own_faith: str = "unreviewed"
    eff_truth: str = "conjecture"
    eff_faith: str = "unreviewed"
    frontier: list[str] = field(default_factory=list)
    stale: bool = False
    upstream_stale: bool = False
    broken: bool = False
    statement_hash: str = ""
    faith_required: list[str] = field(default_factory=list)
    faith_missing: list[str] = field(default_factory=list)
    evidence: list[EvidenceView] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)
    review: Review | None = None
    descendants: int = 0
    queue_score: float = 0.0

    @property
    def display_truth(self) -> str:
        return "broken" if self.broken else self.eff_truth


def _rank_min(states: list[str]) -> str:
    return min(states, key=lambda s: TRUTH_RANK[s])


def edge_convention_conflicts(dag: Dag) -> list[tuple]:
    from verification.graph.conventions.conventions import edge_conflicts
    return edge_conflicts(dag)


def compute(dag: Dag, evidence: dict | None = None, reviews: dict | None = None) -> dict[str, NodeStatus]:
    evidence = read_all(dag) if evidence is None else evidence
    reviews = read_reviews(dag) if reviews is None else reviews
    st: dict[str, NodeStatus] = {i: NodeStatus(id=i) for i in dag.nodes}
    file_cache: dict[str, list[Path]] = {}

    # ---- own status ------------------------------------------------------
    for node_id, node in dag.nodes.items():
        s = st[node_id]
        s.statement_hash = statement_hash(node)
        declared = {c.name: c for c in node.checks}
        for name, rec in sorted(evidence.get(node_id, {}).items()):
            kind = rec.get("kind", name.split("-")[0])
            if kind not in CHECK_KINDS:
                continue
            spec = declared.get(name)
            if kind not in file_cache:
                file_cache[kind] = check_files(dag.root, kind)
            current, _ = input_hash(dag, node, spec.params if spec else {}, file_cache[kind],
                                    uses_lean=kind in LEAN_KINDS)
            fresh = spec is not None and rec.get("input_hash") == current
            res = rec.get("result", {})
            grant = clamp_truth(res.get("grants"), kind) if CHECK_KINDS[kind].question == "truth" else None
            s.evidence.append(EvidenceView(name=name, kind=kind, question=CHECK_KINDS[kind].question,
                                           outcome=res.get("outcome", "error"), grants=grant,
                                           domain=res.get("domain"), summary=res.get("summary", ""),
                                           fresh=fresh, record=rec))
        for spec in node.checks:
            if spec.name not in {e.name for e in s.evidence}:
                s.flags.append(Flag("info", "missing_evidence", f"check {spec.name!r} has not run yet"))

        fresh = [e for e in s.evidence if e.fresh]
        if any(not e.fresh for e in s.evidence):
            s.stale = True
            names = ", ".join(e.name for e in s.evidence if not e.fresh)
            s.flags.append(Flag("warn", "stale", f"evidence out of date (inputs changed): {names}"))

        # truth
        def verdict(evs):
            truth = [e for e in evs if e.question == "truth"]
            ref = next((e for e in truth if e.grants == "refuted"), None)
            if ref:
                return "refuted", ref.domain
            passing = [e for e in truth if e.outcome == "pass" and e.grants]
            if passing:
                best = max(passing, key=lambda e: TRUTH_RANK[e.grants])
                return best.grants, best.domain
            return "conjecture", None
        if node.kind == "definition":
            s.own_truth = s.last_truth = "defined"
        else:
            s.own_truth, s.own_domain = verdict(fresh)
            s.last_truth = verdict(s.evidence)[0]
        for e in fresh:
            if e.outcome in ("fail", "error") and e.grants != "refuted":
                code = "mutation_survived" if e.kind == "mutation" else "check_failed"
                s.flags.append(Flag("warn", code, f"{e.name}: {e.summary or e.outcome}"))

        # faithfulness
        declared_kinds = {c.kind for c in node.checks}
        required = [k for k in REQUIRED_FAITH[node.kind]
                    if k in declared_kinds or (node.lean_decl and k in LEAN_ONLY)]
        s.faith_required = required

        def satisfied(k: str) -> bool:
            for e in fresh:
                if e.kind == k and e.outcome == "pass":
                    if k == "literature" and not e.record.get("result", {}).get("evidence", {}).get("convention_map"):
                        return False
                    return True
            return False
        s.faith_missing = [k for k in required if not satisfied(k)]
        if required and not s.faith_missing:
            s.own_faith = "tested"
        recs = reviews.get(node_id, [])
        matching = [r for r in recs if r.statement_hash == s.statement_hash]
        if matching:
            s.review = matching[-1]
            if s.review.decision == "approve":
                s.own_faith = "human_reviewed"
            else:
                s.flags.append(Flag("warn", "review_rejected",
                                    f"rejected by {s.review.reviewer} on {s.review.date}: {s.review.notes}"))
        elif recs:
            s.flags.append(Flag("info", "review_outdated",
                                "statement changed since the last review; it needs a new one"))

    # ---- graph-level flags -------------------------------------------------
    for e, left in edge_convention_conflicts(dag):
        detail = ", ".join(f"{ax}: {a} (in {e.src}) vs {b}" for ax, (a, b) in sorted(left.items()))
        if e.kind == "variant_of":
            st[e.dst].flags.append(Flag("info", "variant_conventions",
                                        f"compared with {e.src} under different conventions — {detail}"))
        else:
            st[e.dst].flags.append(Flag("warn", "convention_mismatch",
                                        f"edge from {e.src} ({e.kind}) without a converter — {detail}"))

    # ---- edges extracted from Lean proofs (graph/edges) --------------------
    from verification.graph.edges.lean_edges import extracted
    lean_parents: dict[str, list[Edge]] = {}
    for node_id, s in st.items():
        rec = next((e.record for e in s.evidence if e.kind == "lean" and e.fresh and e.outcome == "pass"), None)
        if rec is None:
            continue
        lean_parents[node_id] = [Edge(src=p, dst=node_id, kind=k, declared=False)
                                 for p, k in extracted(rec, node_id) if p in dag.nodes]
        got = {e.src for e in lean_parents[node_id]}
        declared = {e.src for e in dag.parents(node_id, kinds=("uses", "assumes"))}
        for p in sorted(got - declared):
            s.flags.append(Flag("warn", "edge_mismatch", f"the Lean proof uses {p}, but no edge is declared"))
        for p in sorted(declared - got):
            s.flags.append(Flag("info", "edge_unused", f"declared edge from {p} is not used by the Lean proof"))

    # ---- propagation (parents before children) ----------------------------
    # `uses` parents always count: the node's evidence or proof relies on them.
    # `assumes` parents (and any listed in `assumptions:`) join the frontier instead.
    # `instantiates` parents are a proof route: they count only once the node's own
    # truth comes from a proof (proved / proved_modulo); observational evidence
    # (empirical, bounded) stands on its own.
    frontier: dict[str, set[str]] = {}

    def parents_of(i: str) -> list[Edge]:
        return lean_parents.get(i) or dag.parents(i)

    order, done = [], set()

    def visit(i: str, path: tuple = ()) -> None:      # parents first, over the edges actually used
        if i in done:
            return
        if i in path:
            raise ValueError(f"cycle through Lean-extracted edges at {i}")
        for e in parents_of(i):
            visit(e.src, path + (i,))
        done.add(i)
        order.append(i)
    for i in dag.topo_order():
        visit(i)

    for node_id in order:
        node, s = dag.nodes[node_id], st[node_id]
        eff = s.own_truth
        front: set[str] = set()
        broken = False
        proof_grade = TRUTH_RANK.get(s.own_truth, -1) >= TRUTH_RANK["proved_modulo"] and node.kind != "definition"
        for e in parents_of(node_id):
            p, ps = dag.nodes[e.src], st[e.src]
            if e.kind == "instantiates" and not proof_grade:
                continue
            if ps.eff_truth == "refuted" or ps.broken:
                broken = True
            if ps.stale or ps.upstream_stale:
                s.upstream_stale = True
            allowed = e.kind == "assumes" or p.kind == "assumption" or e.src in node.assumptions
            front |= frontier[e.src]
            if allowed:
                if ps.eff_truth not in ("proved", "defined"):
                    front.add(e.src)
            elif eff != "refuted" and ps.eff_truth != "refuted" and not ps.broken:
                eff = _rank_min([eff, "proved" if ps.eff_truth == "defined" else ps.eff_truth])
        faith = [s.own_faith] + [st[a].own_faith for a in dag.ancestors(node_id)
                                 if dag.nodes[a].kind in ("definition", "core")]
        if eff == "proved" and front:
            eff = "proved_modulo"
        if broken and eff != "refuted":
            s.broken = True
            s.flags.append(Flag("warn", "broken", "a parent it relies on is refuted, so this node has lost its support"))
        s.eff_truth = eff
        s.eff_faith = min(faith, key=lambda f: FAITH_RANK[f])
        frontier[node_id] = front
        s.frontier = sorted(front)

    # ---- acknowledged warnings ---------------------------------------------
    for node_id, node in dag.nodes.items():
        for f in st[node_id].flags:
            if f.level == "warn" and f.code in node.acknowledged:
                f.level = "info"
                f.message += f" (acknowledged: {node.acknowledged[f.code]})"

    # ---- review queue -------------------------------------------------------
    for node_id, node in dag.nodes.items():
        s = st[node_id]
        s.descendants = len(dag.descendants(node_id))
        warn = any(f.level == "warn" for f in s.flags)
        if (node.needs_human_review and s.own_faith != "human_reviewed") or warn:
            weakness = len(FAITH_ORDER) - FAITH_RANK[s.own_faith]
            s.queue_score = (1 + s.descendants) * weakness * (2 if warn else 1)
    return st


def summary_counts(statuses: dict[str, NodeStatus]) -> dict[str, dict[str, int]]:
    truth: dict[str, int] = {}
    faith: dict[str, int] = {}
    for s in statuses.values():
        truth[s.display_truth] = truth.get(s.display_truth, 0) + 1
        faith[s.eff_faith] = faith.get(s.eff_faith, 0) + 1
    return {"truth": truth, "faithfulness": faith}


__all__ = ["compute", "NodeStatus", "Flag", "EvidenceView", "check_files", "summary_counts",
           "edge_convention_conflicts", "TRUTH_ORDER", "FAITH_ORDER"]
