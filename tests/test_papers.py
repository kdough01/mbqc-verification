"""The review-site link: paper theorems become open nodes, verdicts are computed, the export carries them."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from dagtool import papers
from dagtool.evidence import write_evidence
from dagtool.hashing import input_hash
from dagtool.model import load_dag
from dagtool.status import check_files, compute
from dagtool.verdict import verdict
from verification.kinds import LEAN_KINDS

REPO = Path(__file__).resolve().parents[1]
SERVER = "https://review.example"


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "dag" / "schema").mkdir(parents=True)
    shutil.copy(REPO / "dag" / "schema" / "node.schema.json", tmp_path / "dag" / "schema")
    (tmp_path / "requirements.txt").write_text("numpy==1\n")
    return tmp_path


def node(root, id, kind="theorem", deps=(), checks=(), **extra):
    data = {"id": id, "kind": kind, "title": f"node {id}", "statement": f"statement of {id}",
            "depends_on": [{"node": d, "kind": k} for d, k in deps], "checks": list(checks), **extra}
    path = root / "dag" / "nodes" / f"{id}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def evidence(root, node_id, kind, outcome="pass", grants=None):
    dag = load_dag(root)
    ih, _ = input_hash(dag, dag.nodes[node_id], {}, check_files(root, kind), uses_lean=kind in LEAN_KINDS)
    write_evidence(dag, node_id, kind, {
        "node": node_id, "kind": kind, "name": kind, "params": {},
        "result": {"outcome": outcome, "grants": grants, "domain": "test", "summary": "", "evidence": {}},
        "input_hash": ih})


def theorem(tid="paper.p_abc.theorem_1_error_bound", **kw):
    t = {"id": tid, "paper_id": "p_abc", "module_id": "m_1", "paper_title": "A transferred paper",
         "title": "Theorem 1: error bound", "summary": "The error is small.", "statement_md": "**Theorem 1.** ...",
         "quotes": [{"page": 4, "text": "Theorem 1. The error is at most ε for all t ≥ 0.", "verified": True}],
         "pages": [4], "withdrawn": False}
    t.update(kw)
    return t


def verdicts(root):
    dag = load_dag(root)
    st = compute(dag)
    return {i: verdict(dag, i, st) for i in dag.nodes}


def test_pull_adds_open_nodes_that_validate(repo):
    node(repo, "core.base", kind="core")
    written = papers.pull(load_dag(repo), SERVER, theorems=[theorem(), theorem("paper.p_abc.lemma_2", title="Lemma 2")])
    assert [p.relative_to(repo).as_posix() for p in written] == [
        "dag/nodes/papers/p_abc/paper.p_abc.theorem_1_error_bound.yaml", "dag/nodes/papers/p_abc/paper.p_abc.lemma_2.yaml"]
    dag = load_dag(repo)   # schema-validated
    n = dag.nodes["paper.p_abc.theorem_1_error_bound"]
    assert n.kind == "theorem" and n.area == "papers/p_abc" and not n.checks
    assert n.statement.startswith("Theorem 1. The error is at most ε")
    assert n.raw["paper"] == {"server": SERVER, "theorem_id": n.id, "paper_id": "p_abc", "module_id": "m_1",
                              "paper_title": "A transferred paper", "pages": [4]}
    assert verdicts(repo)[n.id]["state"] == "open"


def test_pull_is_idempotent_and_keeps_edits(repo):
    papers.pull(load_dag(repo), SERVER, theorems=[theorem()])
    path = repo / "dag/nodes/papers/p_abc/paper.p_abc.theorem_1_error_bound.yaml"
    edited = yaml.safe_load(path.read_text()) | {"checks": [{"kind": "numerical"}]}
    path.write_text(yaml.safe_dump(edited, sort_keys=False, allow_unicode=True))
    again = papers.pull(load_dag(repo), SERVER, theorems=[theorem(title="Renamed upstream")])
    assert again == [] and yaml.safe_load(path.read_text())["checks"] == [{"kind": "numerical"}]


def test_pull_skips_bad_ids_withdrawn_and_nodes_that_already_cite_the_theorem(repo):
    node(repo, "hamsim.moved", paper={"theorem_id": "paper.p_abc.theorem_1_error_bound"})
    out = papers.pull(load_dag(repo), SERVER, theorems=[
        theorem(), theorem("../../etc"), theorem("paper.p_abc.gone", withdrawn=True)])
    assert out == []


def test_statement_falls_back_when_nothing_was_quoted():
    assert papers.statement_of(theorem(quotes=[])) == "**Theorem 1.** ..."
    assert papers.statement_of(theorem(quotes=[], statement_md="", summary="")) == "Theorem 1: error bound"


def test_verdicts(repo):
    node(repo, "def.d", kind="definition")
    node(repo, "core.c", kind="core", deps=[("def.d", "uses")], checks=[{"kind": "lean"}])
    node(repo, "t.proved", deps=[("core.c", "uses")], checks=[{"kind": "lean"}, {"kind": "scaling"}])
    node(repo, "t.refuted", checks=[{"kind": "refuter"}])
    node(repo, "t.broken", deps=[("t.refuted", "uses")], checks=[{"kind": "numerical"}])
    node(repo, "t.waiting", deps=[("t.open_parent", "uses")], checks=[{"kind": "numerical"}])
    node(repo, "t.open_parent")
    evidence(repo, "core.c", "lean", grants="proved")
    evidence(repo, "t.proved", "lean", grants="proved")
    evidence(repo, "t.proved", "scaling", grants="empirical")
    evidence(repo, "t.refuted", "refuter", outcome="fail", grants="refuted")
    evidence(repo, "t.broken", "numerical", grants="empirical")
    evidence(repo, "t.waiting", "numerical", grants="empirical")
    v = verdicts(repo)
    assert v["t.proved"]["state"] == "verified" and v["t.proved"]["methods"] == ["lean", "scaling"]
    assert v["t.proved"]["core_support"] == 2 and v["t.proved"]["core_nodes"] == ["core.c", "def.d"]
    assert v["t.refuted"]["state"] == "rejected" and v["t.refuted"]["methods"] == ["refuter"]
    assert v["t.broken"]["state"] == "rejected" and "t.refuted" in v["t.broken"]["reason"]
    assert v["t.waiting"]["state"] == "open" and v["t.waiting"]["methods"] == ["numerical"]
    assert v["t.open_parent"]["state"] == "open" and v["t.open_parent"]["reason"] == "no passing check yet"


def test_export_carries_verdict_paper_and_checks(repo):
    papers.pull(load_dag(repo), SERVER, theorems=[theorem()])
    node(repo, "t.other", checks=[{"kind": "numerical"}])
    data = json.loads(json.dumps(papers.export(load_dag(repo), circuits=False), default=str))
    by_id = {n["id"]: n for n in data["nodes"]}
    paper_node = by_id["paper.p_abc.theorem_1_error_bound"]
    assert paper_node["verdict"]["state"] == "open" and paper_node["paper"]["paper_id"] == "p_abc"
    assert by_id["t.other"]["checks"] == [{"kind": "numerical", "name": "numerical"}]
    assert data["meta"]["format"] == "mbqc-dag-v1" and "branch" in data["meta"]


def test_push_needs_a_token(repo, monkeypatch):
    monkeypatch.delenv("MODULUS_DAG_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="MODULUS_DAG_TOKEN"):
        papers.push(load_dag(repo), SERVER, circuits=False)
