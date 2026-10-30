"""
papers.py — the link to the Thrust 2 review site (Modulus, genesis-thrust2-review.fly.dev).

    dagtool pull-papers --server URL   add every open paper theorem as dag/nodes/papers/<paper>/<id>.yaml
    dagtool export [--out FILE]        the computed DAG as JSON: what the site's Theorem DAG tab shows

When a paper is uploaded to the site it is split into modules; every theorem module becomes a theorem
with a stable id (paper.<paper id>.<title slug>). `pull-papers` adds the ones this DAG does not have yet
as nodes with no checks, so they start as `conjecture` (shown as *open*). A person or agent then adds
`depends_on` edges into the core and the checks that should run; CI computes the status and publishes
`export` as dag.json on GitHub Pages, which the site reads. Existing node files are never overwritten,
so edits made here are kept. Neither direction needs a secret.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

import yaml

from .model import Dag

DEFAULT_SERVER = "https://genesis-thrust2-review.fly.dev"
STATEMENT_LIMIT = 6000


def _request(url: str, timeout: float = 60) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "dagtool"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:   # noqa: S310 (https URL given by the operator)
        return resp.read()


def fetch_open_theorems(server: str) -> list[dict]:
    return json.loads(_request(server.rstrip("/") + "/api/theorems?state=open"))


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "paper"


def statement_of(t: dict) -> str:
    """The verbatim statement when the extraction quoted it, else the module's write-up."""
    quotes = [q.get("text", "").strip() for q in t.get("quotes") or [] if q.get("text", "").strip()]
    verified = [q.get("text", "").strip() for q in t.get("quotes") or [] if q.get("verified") and q.get("text", "").strip()]
    text = "\n\n".join(verified or quotes) or (t.get("statement_md") or "").strip() or (t.get("summary") or "").strip()
    text = text or t.get("title", "")
    if len(text) > STATEMENT_LIMIT:
        text = text[:STATEMENT_LIMIT].rstrip() + " …"
    return text if len(text) >= 3 else f"{text} (statement not extracted)"


def known_paper_theorems(dag: Dag) -> set[str]:
    out = set()
    for n in dag.nodes.values():
        p = n.raw.get("paper")
        if isinstance(p, dict) and p.get("theorem_id"):
            out.add(p["theorem_id"])
        if n.id.startswith("paper."):
            out.add(n.id)
    return out


def node_yaml(t: dict, server: str) -> dict:
    pages = [int(p) for p in t.get("pages") or [] if isinstance(p, int) or str(p).isdigit()]
    where = f", pages {', '.join(map(str, pages))}" if pages else ""
    paper = {"server": server.rstrip("/"), "theorem_id": t["id"], "paper_id": t["paper_id"]}
    if t.get("module_id"):
        paper["module_id"] = t["module_id"]
    if t.get("paper_title"):
        paper["paper_title"] = t["paper_title"]
    if pages:
        paper["pages"] = pages
    return {
        "id": t["id"], "kind": "theorem", "title": (t.get("title") or t["id"]).strip()[:200],
        "statement": statement_of(t),
        "description": (f"From \"{t.get('paper_title') or t['paper_id']}\"{where} on the review site. "
                        "Added by `dagtool pull-papers`; it stays open until depends_on edges and checks are added."),
        "paper": paper, "tags": ["paper", "open"],
    }


def pull(dag: Dag, server: str, theorems: list[dict] | None = None, dry_run: bool = False) -> list[Path]:
    """Write a node file for every open paper theorem this DAG does not have. Returns the files written."""
    theorems = fetch_open_theorems(server) if theorems is None else theorems
    known = known_paper_theorems(dag)
    written = []
    for t in theorems:
        tid = t.get("id", "")
        if not re.fullmatch(r"paper\.[a-z0-9_]+\.[a-z0-9_]+", tid) or tid in known or t.get("withdrawn"):
            continue
        path = dag.root / "dag" / "nodes" / "papers" / _slug(t["paper_id"]) / f"{tid}.yaml"
        if path.exists():
            continue
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump(node_yaml(t, server), sort_keys=False, allow_unicode=True, width=100),
                            encoding="utf-8")
        written.append(path)
        known.add(tid)
    return written


def _git(root: Path, *args: str) -> str:
    try:
        p = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=20)
        return p.stdout.strip() if p.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def export(dag: Dag, circuits: bool = True) -> dict:
    from .render import build_data
    data = build_data(dag, circuits=circuits)
    meta = data["meta"]
    meta["repo"] = os.environ.get("GITHUB_REPOSITORY") or _git(dag.root, "config", "--get", "remote.origin.url")
    meta["branch"] = os.environ.get("GITHUB_REF_NAME") or _git(dag.root, "rev-parse", "--abbrev-ref", "HEAD")
    meta["format"] = "mbqc-dag-v1"
    return data
