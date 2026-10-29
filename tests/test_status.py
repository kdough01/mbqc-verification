"""Unit tests for the DAG status rules (tools/dagtool/status.py) on small synthetic DAGs."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from dagtool.evidence import Review, append_review, write_evidence
from dagtool.hashing import input_hash, statement_hash
from dagtool.model import DagError, load_dag
from dagtool.status import check_files, compute
from verification.kinds import LEAN_KINDS

REPO = Path(__file__).resolve().parents[1]


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


def evidence(root, node_id, kind, outcome="pass", grants=None, name=None, params=None, fresh=True, payload=None):
    dag = load_dag(root)
    n = dag.nodes[node_id]
    ih, _ = input_hash(dag, n, params or {}, check_files(root, kind), uses_lean=kind in LEAN_KINDS)
    write_evidence(dag, node_id, name or kind, {
        "node": node_id, "kind": kind, "name": name or kind, "params": params or {},
        "result": {"outcome": outcome, "grants": grants, "domain": "test", "summary": "", "evidence": payload or {}},
        "input_hash": ih if fresh else "0" * 16})


def status(root):
    return compute(load_dag(root))


def test_uses_parent_caps_truth(repo):
    node(repo, "t.parent")
    node(repo, "t.child", deps=[("t.parent", "uses")], checks=[{"kind": "numerical"}])
    evidence(repo, "t.child", "numerical", grants="empirical")
    st = status(repo)
    assert st["t.child"].own_truth == "empirical"
    assert st["t.child"].eff_truth == "conjecture"


def test_instantiates_does_not_cap_observational_evidence(repo):
    node(repo, "t.transfer", kind="transfer")
    node(repo, "t.formula", deps=[("t.transfer", "instantiates")], checks=[{"kind": "scaling"}])
    evidence(repo, "t.formula", "scaling", grants="empirical")
    assert status(repo)["t.formula"].eff_truth == "empirical"


def test_instantiates_caps_a_proof(repo):
    node(repo, "t.transfer", kind="transfer")
    node(repo, "t.formula", deps=[("t.transfer", "instantiates")], checks=[{"kind": "lean"}])
    evidence(repo, "t.formula", "lean", grants="proved")
    assert status(repo)["t.formula"].eff_truth == "conjecture"


def test_assumption_joins_frontier_and_gives_proved_modulo(repo):
    node(repo, "a.lit", kind="assumption", checks=[{"kind": "literature"}])
    node(repo, "t.thm", deps=[("a.lit", "assumes")], checks=[{"kind": "lean"}])
    evidence(repo, "a.lit", "literature", grants="assumed")
    evidence(repo, "t.thm", "lean", grants="proved")
    s = status(repo)["t.thm"]
    assert s.eff_truth == "proved_modulo"
    assert s.frontier == ["a.lit"]


def test_frontier_is_inherited(repo):
    node(repo, "a.lit", kind="assumption")
    node(repo, "t.mid", deps=[("a.lit", "assumes")], checks=[{"kind": "lean"}])
    node(repo, "t.top", deps=[("t.mid", "uses")], checks=[{"kind": "lean"}])
    evidence(repo, "t.mid", "lean", grants="proved")
    evidence(repo, "t.top", "lean", grants="proved")
    s = status(repo)["t.top"]
    assert s.frontier == ["a.lit"] and s.eff_truth == "proved_modulo"


def test_listed_empirical_ancestor_is_allowed(repo):
    node(repo, "t.emp", checks=[{"kind": "numerical"}])
    node(repo, "t.thm", deps=[("t.emp", "uses")], assumptions=["t.emp"], checks=[{"kind": "lean"}])
    evidence(repo, "t.emp", "numerical", grants="empirical")
    evidence(repo, "t.thm", "lean", grants="proved")
    s = status(repo)["t.thm"]
    assert s.eff_truth == "proved_modulo" and s.frontier == ["t.emp"]


def test_unlisted_empirical_ancestor_weakens(repo):
    node(repo, "t.emp", checks=[{"kind": "numerical"}])
    node(repo, "t.thm", deps=[("t.emp", "uses")], checks=[{"kind": "lean"}])
    evidence(repo, "t.emp", "numerical", grants="empirical")
    evidence(repo, "t.thm", "lean", grants="proved")
    assert status(repo)["t.thm"].eff_truth == "empirical"


def test_refuted_parent_breaks_child(repo):
    node(repo, "t.bad", checks=[{"kind": "refuter"}])
    node(repo, "t.child", deps=[("t.bad", "uses")], checks=[{"kind": "numerical"}])
    evidence(repo, "t.bad", "refuter", outcome="fail", grants="refuted")
    evidence(repo, "t.child", "numerical", grants="empirical")
    st = status(repo)
    assert st["t.bad"].display_truth == "refuted"
    assert st["t.child"].broken and st["t.child"].display_truth == "broken"


def test_ceiling_clamps_grants(repo):
    node(repo, "t.fit", checks=[{"kind": "scaling"}])
    evidence(repo, "t.fit", "scaling", grants="proved")       # a scaling fit cannot prove
    assert status(repo)["t.fit"].own_truth == "empirical"


def test_stale_evidence_does_not_count_and_propagates(repo):
    node(repo, "t.a", checks=[{"kind": "numerical"}])
    node(repo, "t.b", deps=[("t.a", "uses")])
    evidence(repo, "t.a", "numerical", grants="empirical", fresh=False)
    st = status(repo)
    assert st["t.a"].stale and st["t.a"].own_truth == "conjecture"
    assert st["t.b"].upstream_stale


def test_editing_statement_makes_evidence_stale(repo):
    node(repo, "t.a", checks=[{"kind": "numerical"}])
    evidence(repo, "t.a", "numerical", grants="empirical")
    assert status(repo)["t.a"].own_truth == "empirical"
    node(repo, "t.a", checks=[{"kind": "numerical"}], statement_tex="x = 1")
    s = status(repo)["t.a"]
    assert s.stale and s.own_truth == "conjecture"


def test_review_is_pinned_to_statement_hash(repo):
    node(repo, "d.def", kind="definition")
    dag = load_dag(repo)
    h = statement_hash(dag.nodes["d.def"])
    append_review(dag, "d.def", Review("kevin", "2026-10-29", h, "approve"))
    assert status(repo)["d.def"].own_faith == "human_reviewed"
    node(repo, "d.def", kind="definition", statement_tex="changed")
    s = status(repo)["d.def"]
    assert s.own_faith == "unreviewed"
    assert any(f.code == "review_outdated" for f in s.flags)


def test_faithfulness_tested_needs_all_required_checks(repo):
    node(repo, "t.f", checks=[{"kind": "scaling"}, {"kind": "mutation"}, {"kind": "differential"}])
    evidence(repo, "t.f", "mutation")
    s = status(repo)["t.f"]
    assert s.own_faith == "unreviewed" and s.faith_missing == ["differential"]
    evidence(repo, "t.f", "differential")
    assert status(repo)["t.f"].own_faith == "tested"


def test_effective_faithfulness_limited_by_definitions(repo):
    node(repo, "d.def", kind="definition")
    node(repo, "t.f", deps=[("d.def", "uses")], checks=[{"kind": "mutation"}])
    evidence(repo, "t.f", "mutation")
    s = status(repo)["t.f"]
    assert s.own_faith == "tested" and s.eff_faith == "unreviewed"


def test_convention_mismatch_flagged_unless_converted(repo):
    node(repo, "t.p", conventions={"endian": "big"})
    node(repo, "t.c", deps=[("t.p", "uses")], conventions={"endian": "little"})
    assert any(f.code == "convention_mismatch" for f in status(repo)["t.c"].flags)
    data = yaml.safe_load((repo / "dag/nodes/t.c.yaml").read_text())
    data["depends_on"][0]["convert"] = ["little_to_big_endian"]
    (repo / "dag/nodes/t.c.yaml").write_text(yaml.safe_dump(data))
    assert not any(f.code == "convention_mismatch" for f in status(repo)["t.c"].flags)


def test_cycle_rejected(repo):
    node(repo, "t.x", deps=[("t.y", "uses")])
    node(repo, "t.y", deps=[("t.x", "uses")])
    with pytest.raises(DagError, match="cycle"):
        load_dag(repo)


def test_schema_rejects_status_field(repo):
    node(repo, "t.x", truth="proved")          # status is computed, never written
    with pytest.raises(DagError, match="truth"):
        load_dag(repo)


def test_assumption_must_be_an_ancestor(repo):
    node(repo, "t.x")
    node(repo, "t.y", assumptions=["t.x"])
    with pytest.raises(DagError, match="not an ancestor"):
        load_dag(repo)


def test_queue_ranks_by_descendants(repo):
    node(repo, "d.root", kind="definition")
    node(repo, "d.leaf", kind="definition")
    for i in range(3):
        node(repo, f"t.n{i}", deps=[("d.root", "uses")])
    st = status(repo)
    assert st["d.root"].queue_score > st["d.leaf"].queue_score > 0


def test_evidence_json_roundtrip(repo):
    node(repo, "t.a", checks=[{"kind": "numerical"}])
    evidence(repo, "t.a", "numerical", grants="empirical")
    rec = json.loads((repo / "dag/evidence/t.a/numerical.json").read_text())
    assert rec["result"]["grants"] == "empirical"


def test_lean_edges_replace_declared_edges(repo):
    node(repo, "t.transfer", kind="transfer")
    node(repo, "a.facts", kind="assumption")
    node(repo, "t.lemma", checks=[{"kind": "lean"}])
    node(repo, "t.thm", deps=[("t.transfer", "uses"), ("t.lemma", "uses")], checks=[{"kind": "lean"}])
    evidence(repo, "t.lemma", "lean", grants="proved")
    evidence(repo, "t.thm", "lean", grants="proved_modulo",
             payload={"node_deps": ["t.lemma"], "assumption_nodes": ["a.facts"]})
    s = status(repo)["t.thm"]
    # the unproved transfer node no longer caps it; the assumption joins the frontier
    assert s.eff_truth == "proved_modulo" and s.frontier == ["a.facts"]
    codes = {f.code for f in s.flags}
    assert "edge_unused" in codes and "edge_mismatch" in codes


def test_lean_edge_against_declared_order(repo):
    # node ids sort so that the user comes before the used node; the Lean edge must still order them
    node(repo, "t.z_used", checks=[{"kind": "lean"}])
    node(repo, "t.a_user", checks=[{"kind": "lean"}])
    evidence(repo, "t.z_used", "lean", grants="proved")
    evidence(repo, "t.a_user", "lean", grants="proved", payload={"node_deps": ["t.z_used"]})
    s = status(repo)["t.a_user"]
    assert s.eff_truth == "proved"
    assert any(f.code == "edge_mismatch" for f in s.flags)


def test_prune_removes_orphaned_evidence(repo):
    from dagtool.evidence import prune
    node(repo, "t.a", checks=[{"kind": "numerical"}])
    evidence(repo, "t.a", "numerical", grants="empirical")
    evidence(repo, "t.a", "numerical", grants="empirical", name="old-check")
    node(repo, "t.gone", checks=[{"kind": "numerical"}])
    evidence(repo, "t.gone", "numerical", grants="empirical")
    (repo / "dag/nodes/t.gone.yaml").unlink()
    removed = {p.relative_to(repo).as_posix() for p in prune(load_dag(repo))}
    assert removed == {"dag/evidence/t.a/old-check.json", "dag/evidence/t.gone/numerical.json"}
    assert not (repo / "dag/evidence/t.gone").exists()
    assert not status(repo)["t.a"].stale


def test_summary_reports_changes_and_problems(repo):
    from dagtool.summary import markdown
    node(repo, "t.a", checks=[{"kind": "numerical"}, {"kind": "mutation"}])
    evidence(repo, "t.a", "numerical", grants="empirical")
    evidence(repo, "t.a", "mutation", outcome="fail")
    md = markdown(load_dag(repo), before={"t.a": {"truth": "conjecture", "faithfulness": "unreviewed"}}, ran=[])
    assert "conjecture → **empirical**" in md
    assert "Needs attention: 1 problem" in md and "mutation" in md


def test_regression_is_detected(repo):
    from dagtool.summary import regressions
    node(repo, "t.a", checks=[{"kind": "scaling"}])
    evidence(repo, "t.a", "scaling", outcome="fail", grants="refuted")
    st = status(repo)
    assert regressions(st, {"t.a": {"truth": "empirical", "stale": False}}) == [("t.a", "empirical", "refuted")]
    assert regressions(st, {"t.a": {"truth": "refuted", "stale": False}}) == []      # already known
    # an edited claim: its old evidence was stale, so judge against what it last said
    assert regressions(st, {"t.a": {"truth": "conjecture", "last_truth": "empirical", "stale": True}}) == \
        [("t.a", "empirical", "refuted")]
    assert regressions(st, {"t.a": {"truth": "conjecture", "last_truth": "conjecture", "stale": True}}) == \
        [("t.a", "conjecture", "refuted")]
