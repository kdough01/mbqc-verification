"""
evidence.py — reading and writing dag/evidence/<node>/<name>.json, and review records.
"""

from __future__ import annotations

import json
import platform
import subprocess
from dataclasses import dataclass
from datetime import date, datetime, timezone
from importlib import metadata
from pathlib import Path

import yaml

from .model import Dag

TRACKED_PACKAGES = ("qiskit", "graphix", "numpy", "scipy", "sympy")


def versions() -> dict[str, str]:
    out = {"python": platform.python_version()}
    for pkg in TRACKED_PACKAGES:
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            pass
    return out


def git_commit(root: Path) -> dict:
    """HEAD and whether the tree had uncommitted changes; nulls outside a git checkout."""
    def run(*args):
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=20)
    try:
        head = run("rev-parse", "HEAD")
        if head.returncode != 0:
            return {"commit": None, "dirty": None}
        dirty = run("--no-optional-locks", "status", "--porcelain", "--untracked-files=no")
        return {"commit": head.stdout.strip(), "dirty": bool(dirty.stdout.strip())}
    except (OSError, subprocess.TimeoutExpired):
        return {"commit": None, "dirty": None}


def evidence_path(dag: Dag, node_id: str, name: str) -> Path:
    return dag.evidence_dir / node_id / f"{name}.json"


def write_evidence(dag: Dag, node_id: str, name: str, record: dict) -> Path:
    path = evidence_path(dag, node_id, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return path


def prune(dag: Dag) -> list[Path]:
    """Delete evidence of nodes or checks that no longer exist. Returns what was removed."""
    removed: list[Path] = []
    if not dag.evidence_dir.exists():
        return removed
    for d in sorted(p for p in dag.evidence_dir.iterdir() if p.is_dir()):
        declared = {c.name for c in dag.nodes[d.name].checks} if d.name in dag.nodes else set()
        for f in sorted(d.glob("*.json")):
            if f.stem not in declared:
                f.unlink()
                removed.append(f)
        if not any(d.iterdir()):
            d.rmdir()
    return removed


def read_all(dag: Dag) -> dict[str, dict[str, dict]]:
    """{node_id: {evidence name: record}} for every evidence file of a node that still exists."""
    out: dict[str, dict[str, dict]] = {}
    if not dag.evidence_dir.exists():
        return out
    for path in sorted(dag.evidence_dir.glob("*/*.json")):
        node_id = path.parent.name
        if node_id in dag.nodes:
            out.setdefault(node_id, {})[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    return out


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# Human review records: dag/reviews/<id>.yaml is a list, newest last.
# ---------------------------------------------------------------------------

@dataclass
class Review:
    reviewer: str
    date: str
    statement_hash: str
    decision: str          # approve | reject
    notes: str = ""


def read_reviews(dag: Dag) -> dict[str, list[Review]]:
    out: dict[str, list[Review]] = {}
    if not dag.reviews_dir.exists():
        return out
    for path in sorted(dag.reviews_dir.glob("*.yaml")):
        records = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        out[path.stem] = [Review(**{k: str(v) for k, v in r.items()}) for r in records]
    return out


def append_review(dag: Dag, node_id: str, review: Review) -> Path:
    path = dag.reviews_dir / f"{node_id}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    records = (yaml.safe_load(path.read_text(encoding="utf-8")) or []) if path.exists() else []
    records.append({"reviewer": review.reviewer, "date": review.date or date.today().isoformat(),
                    "statement_hash": review.statement_hash, "decision": review.decision,
                    "notes": review.notes})
    path.write_text(yaml.safe_dump(records, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path
