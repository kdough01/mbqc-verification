"""Integration tests for the Lean-backed checks. Skipped when `lake` is not installed."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dagtool.model import load_dag
from verification.base import RunContext, load_all

REPO = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not (shutil.which("lake") or (Path.home() / ".elan/bin/lake").exists()),
                                reason="Lean (lake) not installed")


@pytest.fixture(scope="module")
def ctx():
    return RunContext(dag=load_dag(REPO))


def run(ctx, node_id, kind):
    node = ctx.dag.nodes[node_id]
    spec = next(c for c in node.checks if c.kind == kind)
    return load_all()[kind]().run(node, spec.params, ctx)


def test_slide_claims_are_proved_outright(ctx):
    for q in "NEM":
        r = run(ctx, f"hamsim.C.slide.d_ge_g.{q}", "lean")
        assert (r.outcome, r.grants) == ("pass", "proved")


def test_qsvt_formula_rests_on_its_assumption_node_only(ctx):
    r = run(ctx, "hamsim.B.qsvt.N.opt", "lean")
    assert (r.outcome, r.grants) == ("pass", "proved_modulo")
    assert r.evidence["assumption_nodes"] == ["assume.hamsim.qsvt_opt_N"]
    assert set(r.evidence["node_deps"]) == {"lemma.bilinear_interpolation", "assume.hamsim.qsvt_opt_N"}
    assert len(r.evidence["assumption_axioms"]) == 6


def test_vocabulary_and_nonvacuity(ctx):
    for nid in ("core.resource_additivity", "hamsim.B.qsvt.N.opt", "lemma.bilinear_interpolation"):
        assert run(ctx, nid, "vocabulary").outcome == "pass", nid
        assert run(ctx, nid, "nonvacuity").outcome == "pass", nid


def test_differential_matches_graphix(ctx):
    r = run(ctx, "def.jcz_construction", "differential")
    assert r.outcome == "pass", r.summary
