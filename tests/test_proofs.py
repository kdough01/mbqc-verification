"""More than one Lean proof of a formalized theorem: proposed, checked by lean_proof, counted on the node."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from dagtool import proposals as pr
from dagtool.model import load_dag

from test_proposals import GOOD_LEAN, NS, TID, proposal, quiet, raw, repo, submit, tree  # noqa: F401

REPO = Path(__file__).resolve().parents[1]
P2 = f"{NS}.Proof_2"
LEAN_OK = shutil.which("lake") or (Path.home() / ".elan/bin/lake").exists()

# A second proof of `counts_add`: the same statement, a different idea (the library lemma instead of omega).
PROOF_2 = f"""namespace {P2}

theorem counts_add (a b : Nat) (h : a ≤ b) : a + (b - a) = b := Nat.add_sub_of_le h

end {P2}
"""


def proof_prop(**kw):
    p = {"node": TID, "outcome": "proof", "lean_decl": f"{P2}.counts_add",
         "approach": "Nat.add_sub_of_le instead of linear arithmetic"}
    p.update(kw)
    return p


def formalize(repo):
    rows = pr.apply(repo, submit(repo), run_checks=False, echo=quiet)
    assert rows[0]["outcome"] == "formalized"
    shutil.rmtree(repo / "in")


def test_only_formalized_theorems_take_another_proof(repo):
    rows = pr.apply(repo, submit(repo, PROOF_2, proof_prop()), run_checks=False, echo=quiet)
    assert rows[0]["outcome"] == "skipped" and "formalize it first" in rows[0]["reason"]
    assert pr.proof_targets(load_dag(repo)) == []


def test_a_second_proof_is_recorded_as_a_lean_proof_check(repo):
    formalize(repo)
    dag = load_dag(repo)
    d = pr.describe_proof(dag, dag.nodes[TID])
    assert d["next_index"] == 2 and d["namespace"] == P2 and d["main_decl"] == f"{NS}.counts_add"
    assert d["lean_file"] == "lean/MBQC/Papers/Paper_p_abc/T_theorem_1_counts_add/Proof_2.lean"
    assert "theorem counts_add" in d["main_lean_source"] and [p["index"] for p in d["proofs"]] == [1]
    rows = pr.apply(repo, submit(repo, PROOF_2, proof_prop()), run_checks=False, echo=quiet)
    assert rows[0]["outcome"] == "proof_added" and rows[0]["index"] == 2, rows
    r = raw(repo)
    assert r["checks"][-1]["test"] == "lean_proof/independent_proof" and r["checks"][-1]["name"] == "lean-proof-2"
    assert r["checks"][-1]["params"]["decl"] == f"{P2}.counts_add"
    assert r["checks"][-1]["params"]["approach"] == "Nat.add_sub_of_le instead of linear arithmetic"
    assert r["lean_decl"] == f"{NS}.counts_add" and r["statement"] == "Theorem 1. Counts add up."   # untouched
    assert (repo / d["lean_file"]).read_text(encoding="utf-8") == PROOF_2
    assert f"import {P2}" in (repo / "lean/MBQC.lean").read_text()
    node = load_dag(repo).nodes[TID]
    assert [p["index"] for p in pr.proofs_of(node)] == [1, 2]
    assert pr.describe_proof(load_dag(repo), node)["namespace"] == f"{NS}.Proof_3"


@pytest.mark.parametrize("lean, prop, why", [
    (PROOF_2, proof_prop(approach=""), "approach"),
    (PROOF_2, proof_prop(lean_decl=f"{NS}.Proof_3.counts_add"), "this is proof 2"),
    (PROOF_2, proof_prop(depends_on=[{"node": "core.additivity"}]), "cannot choose checks or edges"),
    (PROOF_2, proof_prop(extra_checks=[{"kind": "lean"}]), "cannot choose checks or edges"),
    (PROOF_2.replace(P2, NS), proof_prop(), "namespace"),
    (f"import {NS.replace('.T_theorem_1_counts_add', '')}.T_theorem_1_counts_add\n" + PROOF_2, proof_prop(),
     "imports MBQC.Papers"),
    ("axiom x : False\n" + PROOF_2, proof_prop(), "declares an axiom"),
    (GOOD_LEAN.replace(f"namespace {NS}", f"namespace {P2}").replace(f"end {NS}", f"end {P2}"), proof_prop(),
     "repeats an earlier proof"),
    (None, proof_prop(), "no theorem.lean"),
])
def test_bad_proof_proposals_leave_no_trace(repo, lean, prop, why):
    formalize(repo)
    before = tree(repo)
    rows = pr.apply(repo, submit(repo, lean, prop), run_checks=False, echo=quiet)
    assert rows[0]["outcome"] == "rejected" and why in rows[0]["reason"], rows
    assert tree(repo) == before


def test_proof_feedback_is_a_dry_run(repo):
    formalize(repo)
    before = tree(repo)
    fb = pr.feedback(repo, submit(repo, PROOF_2, proof_prop()) / TID, run_checks=False)
    assert fb["dry_run"] and fb["accepted"] and fb["outcome"] == "proof_added"
    assert tree(repo) == before


def test_proof_paths_reuse_the_proposal_files():
    ok, _ = pr.proposal_paths([f"proposals/{TID}/proposal.json", f"proposals/{TID}/theorem.lean"])
    assert ok


# ---------------------------------------------------------------- with Lean

@pytest.fixture
def lean_repo(repo):
    """The fixture DAG on top of the verifier's real Lean project, with the theorem formalized and compiled."""
    shutil.rmtree(repo / "lean")
    shutil.copytree(REPO / "lean", repo / "lean", ignore=shutil.ignore_patterns("Papers"))
    (repo / "lean/MBQC.lean").write_text("\n".join(l for l in (REPO / "lean/MBQC.lean").read_text().splitlines()
                                                   if "MBQC.Papers." not in l) + "\n")
    rows = pr.apply(repo, submit(repo), run_checks=False, echo=quiet)
    assert rows[0]["outcome"] == "formalized"
    shutil.rmtree(repo / "in")
    return repo


def run_proof(repo, lean, **kw):
    fb = pr.feedback(repo, submit(repo, lean, proof_prop(**kw)) / TID, run_checks=True)
    shutil.rmtree(repo / "in")
    return fb


def checks_by_name(fb):
    return {c["name"]: c for c in fb.get("checks", [])}


@pytest.mark.skipif(not LEAN_OK, reason="Lean (lake) not installed")
def test_lean_accepts_a_different_proof_of_the_same_statement(lean_repo):
    before = tree(lean_repo)
    fb = run_proof(lean_repo, PROOF_2)
    assert fb["outcome"] == "proof_added", fb
    c = checks_by_name(fb)["lean-proof-2"]
    assert c["outcome"] == "pass" and c["grants"] == "proved" and "another proof" in c["summary"]
    assert tree(lean_repo) == before


@pytest.mark.skipif(not LEAN_OK, reason="Lean (lake) not installed")
def test_lean_refuses_a_different_statement(lean_repo):
    fb = run_proof(lean_repo, PROOF_2.replace(": a + (b - a) = b := Nat.add_sub_of_le h",
                                              ": b = a + (b - a) := (Nat.add_sub_of_le h).symm"))
    assert fb["outcome"] == "rejected" and "a different statement" in fb["reason"], fb


@pytest.mark.skipif(not LEAN_OK, reason="Lean (lake) not installed")
def test_lean_refuses_a_definitionally_equal_restatement(lean_repo):
    # a + (b - a) + 0 = b reduces to the original but is not the same statement
    fb = run_proof(lean_repo, PROOF_2.replace(": a + (b - a) = b := Nat.add_sub_of_le h",
                                              ": a + (b - a) + 0 = b := Nat.add_sub_of_le h"))
    assert fb["outcome"] == "rejected" and "definitionally equal but not the same statement" in fb["reason"], fb


@pytest.mark.skipif(not LEAN_OK, reason="Lean (lake) not installed")
def test_lean_refuses_the_same_proof_term_as_any_earlier_proof(lean_repo):
    rows = pr.apply(lean_repo, submit(lean_repo, PROOF_2, proof_prop()), run_checks=True, echo=quiet)
    assert rows[0]["outcome"] == "proof_added", rows
    shutil.rmtree(lean_repo / "in")
    p3 = PROOF_2.replace(P2, f"{NS}.Proof_3").replace(":= Nat.add_sub_of_le h", ":= (Nat.add_sub_of_le h)")
    fb = run_proof(lean_repo, p3, lean_decl=f"{NS}.Proof_3.counts_add", approach="the same lemma, in brackets")
    assert fb["outcome"] == "rejected" and f"same proof term as {P2}.counts_add" in fb["reason"], fb
    p3 = p3.replace(":= (Nat.add_sub_of_le h)", ":= by simp_all [Nat.add_sub_cancel' h]")
    fb = run_proof(lean_repo, p3, lean_decl=f"{NS}.Proof_3.counts_add", approach="simp with the cancellation lemma")
    assert fb["outcome"] == "proof_added" and fb["index"] == 3, fb
