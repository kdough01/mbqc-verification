"""
runner.py — run the tests nodes name (checks/<type>/<name>.py) and write their evidence.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from checks import _framework as framework
from checks._framework import Context
from checks._kinds import CHECK_KINDS, LEAN_KINDS, clamp_truth

from .evidence import evidence_path, git_commit, now_utc, read_all, versions, write_evidence
from .hashing import input_hash
from .model import CheckSpec, Dag, Node
from .status import check_files

# Fields of a result that must match exactly when a check is re-run (graph/repro).
REPRO_FIELDS = ("outcome", "grants", "domain")


@dataclass
class Planned:
    node: Node
    spec: CheckSpec
    reason: str      # missing | stale | forced


def plan(dag: Dag, node_ids=None, kinds=None, only_stale=False) -> list[Planned]:
    """kinds: types ("scaling") or tests ("scaling/no_cancel") to restrict to."""
    tests = framework.discover()
    existing = read_all(dag)
    out = []
    for node_id in dag.topo_order():
        if node_ids and node_id not in node_ids:
            continue
        node = dag.nodes[node_id]
        for spec in node.checks:
            if kinds and spec.kind not in kinds and spec.test not in kinds:
                continue
            if spec.test not in tests:
                continue
            rec = existing.get(node_id, {}).get(spec.name)
            current, _ = input_hash(dag, node, spec.params, check_files(dag.root, spec.test),
                                    uses_lean=spec.kind in LEAN_KINDS)
            if rec is None:
                reason = "missing"
            elif rec.get("input_hash") != current or rec.get("test") != spec.test:
                reason = "stale"
            else:
                reason = "forced"
            if only_stale and reason == "forced":
                continue
            out.append(Planned(node, spec, reason))
    return out


def run_one(ctx: Context, node: Node, spec: CheckSpec) -> dict:
    """Run one test and return the evidence record (not written)."""
    t0 = time.time()
    result = framework.run(spec.test, node, spec.params, ctx)
    if CHECK_KINDS[spec.kind].question == "truth":
        clamped = clamp_truth(result.grants, spec.kind)
        if clamped != result.grants:
            result.evidence["clamped_from"] = result.grants
            result.grants = clamped
    else:
        result.grants = None
    ih, parts = input_hash(ctx.dag, node, spec.params, check_files(ctx.root, spec.test),
                           uses_lean=spec.kind in LEAN_KINDS)
    return {
        "node": node.id,
        "test": spec.test,
        "kind": spec.kind,
        "name": spec.name,
        "params": spec.params,
        "result": result.to_dict(),
        "input_hash": ih,
        "inputs": parts,
        "provenance": {**git_commit(ctx.root), "versions": versions(), "finished": now_utc(),
                       "seconds": round(time.time() - t0, 2), "quick": ctx.quick},
    }


def run(dag: Dag, planned: list[Planned], quick=False, echo=print) -> list[dict]:
    ctx = Context(dag=dag, quick=quick)
    records = []
    for i, p in enumerate(planned, 1):
        echo(f"[{i}/{len(planned)}] {p.node.id} :: {p.spec.name} ({p.reason}) ...", end=" ", flush=True)
        rec = run_one(ctx, p.node, p.spec)
        write_evidence(dag, p.node.id, p.spec.name, rec)
        r = rec["result"]
        echo(f"{r['outcome']}{' -> ' + r['grants'] if r['grants'] else ''}  ({rec['provenance']['seconds']}s)")
        records.append(rec)
    return records


def repro(dag: Dag, planned: list[Planned], quick=False, echo=print) -> list[dict]:
    """Re-run checks without writing; report where the verdict differs from stored evidence."""
    ctx = Context(dag=dag, quick=quick)
    diffs = []
    for p in planned:
        path = evidence_path(dag, p.node.id, p.spec.name)
        if not path.exists():
            continue
        stored = json.loads(path.read_text(encoding="utf-8"))["result"]
        fresh = run_one(ctx, p.node, p.spec)["result"]
        bad = {f: (stored.get(f), fresh.get(f)) for f in REPRO_FIELDS if stored.get(f) != fresh.get(f)}
        echo(f"{p.node.id} :: {p.spec.name}: {'REPRODUCED' if not bad else 'DIFFERS ' + str(bad)}")
        if bad:
            diffs.append({"node": p.node.id, "check": p.spec.name, "diff": bad})
    return diffs
