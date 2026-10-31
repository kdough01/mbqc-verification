"""The `reproduction` check: a recorded run of a pinned pipeline against the claimed value."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import verification.truth.reproduction.check  # noqa: F401  (registers the kind)
from verification.base import REGISTRY
from verification.kinds import CHECK_KINDS

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def run(tmp_path):
    (tmp_path / "res.json").write_text(json.dumps({
        "quantities": {"q": {"paper": 100.0, "ours": 100.5}, "far": {"paper": 36, "ours": 87}},
        "rows": [{"f": 0.4}, {"f": 1.0}], "provenance": {"rre_commit": "abc"}}))
    (tmp_path / "other.json").write_text(json.dumps({"x": 87}))
    ctx = SimpleNamespace(dag=SimpleNamespace(root=tmp_path))
    check = REGISTRY["reproduction"]()

    def go(**params):
        return check.run(None, {"results": "res.json", **params}, ctx)
    return go


def test_kind_is_registered_with_empirical_ceiling():
    assert "reproduction" in REGISTRY
    assert CHECK_KINDS["reproduction"].ceiling == "empirical"


def test_approx_within_tolerance_grants_empirical(run):
    r = run(path="quantities.q.ours", expect={"path": "quantities.q.paper"}, domain="d")
    assert (r.outcome, r.grants, r.domain) == ("pass", "empirical", "d")
    assert r.evidence["provenance"] == {"rre_commit": "abc"}


def test_approx_outside_tolerance_refutes_and_says_by_how_much(run):
    r = run(path="quantities.far.ours", expect={"path": "quantities.far.paper"})
    assert (r.outcome, r.grants) == ("fail", "refuted")
    assert "+141.7%" in r.summary


def test_tolerance_is_a_parameter(run):
    assert run(path="quantities.q.ours", expect=100, rel_tol=0.001).outcome == "fail"
    assert run(path="quantities.q.ours", expect=100, rel_tol=0.01).outcome == "pass"


def test_ops_and_list_paths(run):
    assert run(path="rows.1.f", expect=0.999, op="ge").outcome == "pass"
    assert run(path="rows.0.f", expect=0.999, op="ge").outcome == "fail"
    assert run(path="rows.0.f", expect=0.5, op="le").outcome == "pass"
    assert run(path="quantities.far.ours", expect={"results": "other.json", "path": "x"}, op="eq").outcome == "pass"


def test_missing_results_skip_and_bad_params_error(run):
    assert run(results="nope.json", path="a").outcome == "skip"
    assert run(path="quantities.missing.ours", expect=1).outcome == "error"
    assert run(path="quantities.q.ours", expect=1, op="between").outcome == "error"
    assert REGISTRY["reproduction"]().run(None, {}, None).outcome == "error"


def test_saadatmand_results_cover_every_reproduction_check():
    """Every committed small-instance node points at values that exist (large instances may skip)."""
    import yaml
    for f in (REPO / "dag" / "nodes" / "reproductions").rglob("*.yaml"):
        node = yaml.safe_load(f.read_text(encoding="utf-8"))
        for c in node.get("checks", []):
            if c["kind"] != "reproduction":
                continue
            res = REPO / c["params"]["results"]
            if not res.exists():
                assert any(s in node["id"] for s in ("8x8", "16x16", "20x20")), f"{node['id']}: {res} missing"
                continue
            ctx = SimpleNamespace(dag=SimpleNamespace(root=REPO))
            r = REGISTRY["reproduction"]().run(None, c["params"], ctx)
            assert r.outcome in ("pass", "fail"), f"{node['id']} {c.get('name')}: {r.summary}"
