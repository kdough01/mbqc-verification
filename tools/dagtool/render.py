"""
render.py — the theorem browser: one self-contained HTML page.

    dagtool render                      -> dag/build/index.html
    dagtool render --out somewhere.html

The page embeds the whole DAG (nodes, edges, computed status, evidence
summaries) as JSON and needs no server and no external scripts. Search, click a
theorem for its statement, status, evidence and edges, or open the review queue.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from verification.kinds import CHECK_KINDS

from .evidence import git_commit, now_utc
from .model import Dag
from .status import compute, summary_counts

TEMPLATE = Path(__file__).with_name("browser.html")
COL_W, ROW_H, NODE_W, NODE_H = 260, 46, 216, 34
EVIDENCE_LIMIT = 6000    # bytes of check-specific payload kept per evidence record
KEEP_KEYS = {"counts", "training", "holdout", "mismatches", "interpolated", "interpolated_through",
             "counterexample"}   # always kept: the browser plots or shows them

# One small instance per method for the circuit viewer: (id, method, n, k, label)
CIRCUIT_INSTANCES = [
    ("trotter1", "trotter1", 2, 2, "First-order Trotter · n = 2, r = 2"),
    ("trotter2", "trotter2", 2, 2, "Second-order Trotter · n = 2, r = 2"),
    ("qsvt", "qsvt", 2, 3, "QSVT · n = 2, D = 3"),
    ("gqsp", "gqsp", 2, 1, "GQSP · n = 2, d = 1"),
]


def _slug(node_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", node_id).strip("-")


def layout(dag: Dag) -> dict[str, tuple[float, float, int]]:
    """Layered left-to-right layout: column = longest path from a root, rows ordered by barycenters."""
    parents = defaultdict(list)
    children = defaultdict(list)
    for e in dag.edges:
        parents[e.dst].append(e.src)
        children[e.src].append(e.dst)
    col: dict[str, int] = {}

    def depth(i: str, seen=()) -> int:
        if i not in col:
            col[i] = 0 if not parents[i] else 1 + max(depth(p, seen + (i,)) for p in parents[i])
        return col[i]
    for i in dag.nodes:
        depth(i)
    cols = defaultdict(list)
    for i in sorted(dag.nodes, key=lambda i: (dag.nodes[i].area, i)):
        cols[col[i]].append(i)
    pos = {i: r for c in cols.values() for r, i in enumerate(c)}
    for _ in range(6):   # barycenter sweeps, forward then backward
        for c in sorted(cols)[1:]:
            cols[c].sort(key=lambda i: (sum(pos[p] for p in parents[i]) / len(parents[i])) if parents[i] else pos[i])
            pos.update({i: r for r, i in enumerate(cols[c])})
        for c in sorted(cols, reverse=True)[1:]:
            cols[c].sort(key=lambda i: (sum(pos[k] for k in children[i]) / len(children[i])) if children[i] else pos[i])
            pos.update({i: r for r, i in enumerate(cols[c])})
    tallest = max(len(v) for v in cols.values())
    out = {}
    for c, ids in cols.items():
        offset = (tallest - len(ids)) * ROW_H / 2
        for r, i in enumerate(ids):
            out[i] = (24 + c * COL_W, 24 + offset + r * ROW_H, c)
    return out


def _evidence_payload(ev) -> dict:
    rec = ev.record
    res = rec.get("result", {})
    payload = res.get("evidence", {}) or {}
    text = json.dumps(payload, default=str)
    trimmed = False
    if len(text) > EVIDENCE_LIMIT:
        payload = {k: v for k, v in payload.items()
                   if k in KEEP_KEYS or len(json.dumps(v, default=str)) < 1200}
        trimmed = True
    prov = rec.get("provenance", {})
    return {
        "name": ev.name, "kind": ev.kind, "question": ev.question, "outcome": ev.outcome,
        "grants": ev.grants, "domain": ev.domain, "summary": ev.summary, "fresh": ev.fresh,
        "params": rec.get("params", {}), "payload": payload, "trimmed": trimmed,
        "finished": prov.get("finished"), "seconds": prov.get("seconds"), "quick": prov.get("quick"),
        "commit": prov.get("commit"), "versions": prov.get("versions", {}),
    }


def circuit_instances() -> list[dict]:
    """The circuit viewer's data: each instance's Qiskit circuit and its two MBQC patterns.
    Empty when qiskit/graphix are not installed (the browser then hides the viewer)."""
    try:
        import numpy as np

        from mbqc_verify.compile.export import circuit_json, pattern_json
        from mbqc_verify.hamsim.analysis import generic_circuit
        from mbqc_verify.hamsim.circuits import IsingChain, trotter_circuit
    except ImportError:
        return []
    out = []
    for iid, method, n, k, label in CIRCUIT_INSTANCES:
        if method == "trotter1":
            hc = trotter_circuit(IsingChain.random(n, seed=n), 1.0, k, order=1)
        else:
            hc = generic_circuit(method, n, k, np.random.default_rng(1000 * n + k))
        out.append({"id": iid, "method": method, "n": n, "k": k, "label": label,
                    "circuit": circuit_json(hc.circuit, hc.layout, hc.postselect),
                    "patterns": {"unopt": pattern_json(hc.circuit, optimize=False),
                                 "opt": pattern_json(hc.circuit, optimize=True)}})
    return out


def node_method(node) -> str | None:
    """Which circuit family a node is about, if any (for linking it to the circuit viewer)."""
    for c in node.checks:
        m = c.params.get("method")
        if m in ("trotter1", "trotter2", "qsvt", "gqsp"):
            return m
        if c.params.get("instances"):
            return c.params["instances"][-1].get("method")
    for m in ("qsvt", "gqsp"):
        if m in node.tags:
            return m
    if "trotter" in node.tags:
        return "trotter1" if "trotter1" in node.id else "trotter2"
    return None


def build_data(dag: Dag, circuits: bool = True) -> dict:
    st = compute(dag)
    pos = layout(dag)
    slugs = {i: _slug(i) for i in dag.nodes}
    if len(set(slugs.values())) != len(slugs):
        raise ValueError("node ids collide after slugging; rename one")
    nodes = []
    for i in dag.topo_order():
        n, s = dag.nodes[i], st[i]
        x, y, c = pos[i]
        nodes.append({
            "id": i, "slug": slugs[i], "kind": n.kind, "layer": n.layer, "area": n.area or "(root)",
            "title": n.title, "statement": n.statement.strip(), "statement_tex": n.statement_tex,
            "method": node_method(n),
            "description": (n.description or "").strip(), "notes": (n.notes or "").strip(),
            "lean_decl": n.lean_decl, "code": n.code, "conventions": n.conventions.as_dict(),
            "assumptions": n.assumptions, "source": n.source, "tags": n.tags,
            "path": n.path.relative_to(dag.root).as_posix(), "x": x, "y": y, "col": c,
            "status": {
                "truth": s.display_truth, "own_truth": s.own_truth, "domain": s.own_domain,
                "faith": s.eff_faith, "own_faith": s.own_faith, "frontier": s.frontier,
                "stale": s.stale, "upstream_stale": s.upstream_stale, "broken": s.broken,
                "statement_hash": s.statement_hash, "faith_required": s.faith_required,
                "faith_missing": s.faith_missing, "queue_score": s.queue_score, "descendants": s.descendants,
                "review": s.review.__dict__ if s.review else None,
            },
            "flags": [f.__dict__ for f in s.flags],
            "evidence": [_evidence_payload(e) for e in s.evidence],
        })
    return {
        "meta": {"generated": now_utc(), **git_commit(dag.root), "counts": summary_counts(st),
                 "node_w": NODE_W, "node_h": NODE_H,
                 "width": max(p[0] for p in pos.values()) + NODE_W + 24,
                 "height": max(p[1] for p in pos.values()) + NODE_H + 24,
                 "check_kinds": {k: {"question": m.question, "ceiling": m.ceiling, "summary": m.summary}
                                 for k, m in CHECK_KINDS.items()}},
        "nodes": nodes,
        "edges": [{"src": e.src, "dst": e.dst, "kind": e.kind, "convert": list(e.convert)} for e in dag.edges],
        "circuits": circuit_instances() if circuits else [],
    }


def render(dag: Dag, out: Path, fragment: bool = False) -> Path:
    """Write the browser. fragment=True drops <!doctype>/<html>/<head>/<body> (for hosts that add their own)."""
    data = json.dumps(build_data(dag), ensure_ascii=False, separators=(",", ":"), default=str)
    data = data.replace("</", "<\\/")
    page = TEMPLATE.read_text(encoding="utf-8").replace("/*__DAG_DATA__*/{}", data)
    if fragment:
        head = re.search(r"(?s)<!--HEAD-START-->(.*)<!--HEAD-END-->", page).group(1)
        body = re.search(r"(?s)<!--BODY-START-->(.*)<!--BODY-END-->", page).group(1)
        page = head.strip() + "\n" + body.strip() + "\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out
