"""Proposals for open paper theorems: described, given feedback and applied by the verifier's own code only."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from dagtool import proposals as pr
from dagtool.model import load_dag

REPO = Path(__file__).resolve().parents[1]
TID = "paper.p_abc.theorem_1_counts_add"
NS = "MBQC.Papers.Paper_p_abc.T_theorem_1_counts_add"

GOOD_LEAN = f"""import MBQC.Defs.Pattern

namespace {NS}
open MBQC.Defs

theorem counts_add (a b : Nat) (h : a ≤ b) : a + (b - a) = b := by omega

theorem counts_add_nonvacuous : ∃ a b : Nat, a ≤ b := ⟨0, 0, Nat.le_refl 0⟩

end {NS}
"""


def write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "dag" / "schema").mkdir(parents=True)
    shutil.copy(REPO / "dag" / "schema" / "node.schema.json", tmp_path / "dag" / "schema")
    (tmp_path / "dag" / "suites").mkdir(parents=True)
    shutil.copy(REPO / "dag" / "suites" / "policy.yaml", tmp_path / "dag" / "suites")
    (tmp_path / "requirements.txt").write_text("numpy==1\n")
    write(tmp_path, ".gitignore", "dag/build/\n")
    write(tmp_path, "lean/MBQC.lean", "import MBQC.Defs.Pattern\n")
    write(tmp_path, "lean/MBQC/Defs/Pattern.lean", "-- definitions\n")

    def node(id, **data):
        write(tmp_path, f"dag/nodes/{id.split('.')[0]}/{id}.yaml",
              yaml.safe_dump({"id": id, "title": f"node {id}", "statement": f"statement of {id}", **data}, sort_keys=False))
    node("def.pattern", kind="definition", lean_decl=["MBQC.Defs.Pattern"])
    node("core.additivity", kind="core", lean_decl="MBQC.Core.additivity")
    write(tmp_path, f"dag/nodes/papers/p_abc/{TID}.yaml", yaml.safe_dump({
        "id": TID, "kind": "theorem", "title": "Theorem 1: counts add", "statement": "Theorem 1. Counts add up.",
        "paper": {"theorem_id": TID, "paper_id": "p_abc", "paper_title": "A paper", "pages": [3]},
        "tags": ["paper", "open"]}, sort_keys=False, allow_unicode=True))
    return tmp_path


def proposal(**kw):
    p = {"node": TID, "outcome": "formalized", "reason": "direct", "lean_decl": f"{NS}.counts_add",
         "witness": f"{NS}.counts_add_nonvacuous", "depends_on": [{"node": "core.additivity", "kind": "uses"}],
         "statement_tex": "a + (b-a) = b", "notes": "stated over Nat"}
    p.update(kw)
    return p


# The suite every test proposal carries unless it says otherwise: the claim checked exhaustively on a small domain.
CHECKS_PY = """def counts_add(a, b):
    return a > b or a + (b - a) == b
"""
SUITE = {"claim_type": "exact_statement", "checks": [
    {"kind": "finite", "name": "small", "params": {"predicate": "checks.py:counts_add",
                                                   "domain": {"a": {"range": [0, 12]}, "b": {"range": [0, 12]}}},
     "rationale": "the identity on every a, b up to 12"}]}


def submit(tmp, lean=GOOD_LEAN, prop=None, attempts=None, suite=None, checks=CHECKS_PY):
    d = tmp / "in" / TID
    d.mkdir(parents=True, exist_ok=True)
    if suite is not False:
        (d / "suite.json").write_text(json.dumps(suite or SUITE), encoding="utf-8")
    if checks is not None:
        (d / "checks.py").write_text(checks, encoding="utf-8")
    if lean is not None:
        (d / "theorem.lean").write_text(lean, encoding="utf-8")
    if prop is not False:
        (d / "proposal.json").write_text(json.dumps(prop or proposal()), encoding="utf-8")
    if attempts is not None:
        (d / "attempts.json").write_text(json.dumps(attempts), encoding="utf-8")
    return tmp / "in"


def raw(repo):
    return yaml.safe_load((repo / f"dag/nodes/papers/p_abc/{TID}.yaml").read_text(encoding="utf-8"))


def tree(repo):
    """A digest of every file outside the proposal inbox, to show a dry run changes nothing."""
    h = hashlib.sha256()
    for p in sorted(x for x in repo.rglob("*") if x.is_file() and "in" not in x.relative_to(repo).parts[:1]
                    and ".lake" not in x.relative_to(repo).parts):      # Lean build outputs are not the repository
        h.update(p.relative_to(repo).as_posix().encode() + p.read_bytes())
    return h.hexdigest()


def quiet(*a, **k):
    pass


def test_open_theorems_and_what_a_proposal_needs(repo):
    dag = load_dag(repo)
    assert [n.id for n in pr.open_theorems(dag)] == [TID]
    d = pr.describe(dag, dag.nodes[TID])
    assert d["namespace"] == NS and d["lean_file"] == "lean/MBQC/Papers/Paper_p_abc/T_theorem_1_counts_add.lean"
    assert d["statement"] == "Theorem 1. Counts add up." and d["checks_run"][:3] == ["lean", "vocabulary", "nonvacuity"]
    assert "exact_statement" in d["suite_policy"]["claim_types"] and d["proposal_format"]["files"]["suite.json"].startswith("required")
    assert [v["id"] for v in d["vocabulary"]] == ["def.pattern"]
    assert d["proposal_format"]["directory"] == f"proposals/{TID}/"


@pytest.mark.parametrize("bad, why", [
    ("axiom cheat : False", "axiom"), ("theorem t : 1 = 2 := by sorry", "sorry"), ("#eval IO.println 1", "command"),
    ("run_cmd pure ()", "runs code"), ("theorem t : True := by native_decide", "compiled"),
    ("macro \"x\" : term => `(1)", "syntax"), ("import Lean", "imports Lean"), ("@[implemented_by f] def g := 1", "replaces"),
    ("set_option debug.skipKernelTC true", "kernel"),
])
def test_scan_rejects(bad, why):
    assert any(why in p for p in pr.scan_lean(bad)), pr.scan_lean(bad)


def test_scan_accepts_ordinary_proofs():
    assert pr.scan_lean(GOOD_LEAN) == []
    assert pr.scan_lean("-- sorry, axiom in a comment\n/- #eval -/\ntheorem t : 1 + 1 = 2 := by decide") == []


def test_apply_formalized_without_checks_keeps_the_attempt_record(repo):
    rows = pr.apply(repo, submit(repo, attempts=[{"n": 1, "rationale": "first try"}]), run_checks=False, echo=quiet)
    assert rows[0]["outcome"] == "formalized" and rows[0]["accepted"]
    r = raw(repo)
    assert r["statement"] == "Theorem 1. Counts add up."                      # never touched
    assert r["lean_decl"] == f"{NS}.counts_add"
    pred = "dag/predicates/paper.p_abc.theorem_1_counts_add.py"
    assert r["checks"] == [{"test": "lean/proof", "origin": "verifier"}, {"test": "vocabulary/vetted_constants", "origin": "verifier"},
                           {"test": "nonvacuity/witness", "params": {"witness": f"{NS}.counts_add_nonvacuous"}, "origin": "verifier"},
                           {"test": "finite/exhaustive", "name": "small", "params": {"predicate": f"{pred}:counts_add",
                            "domain": {"a": {"range": [0, 12]}, "b": {"range": [0, 12]}}}, "origin": "proposal",
                            "rationale": "the identity on every a, b up to 12"}]
    assert r["code"] == [pred] and (repo / pred).read_text() == CHECKS_PY and "claim:exact_statement" in r["tags"]
    assert r["depends_on"] == [{"node": "core.additivity", "kind": "uses"}]
    assert "formalized" in r["tags"] and "open" not in r["tags"] and "awaits human review" in r["notes"]
    assert (repo / "lean/MBQC/Papers/Paper_p_abc/T_theorem_1_counts_add.lean").read_text(encoding="utf-8") == GOOD_LEAN
    assert "import MBQC.Papers.Paper_p_abc.T_theorem_1_counts_add" in (repo / "lean/MBQC.lean").read_text()
    records = list((repo / "dag/proposals" / TID).glob("attempts-*.json"))
    assert len(records) == 1 and json.loads(records[0].read_text())[0]["rationale"] == "first try"
    assert pr.open_theorems(load_dag(repo)) == []
    assert pr.apply(repo, repo / "in", run_checks=False, echo=quiet)[0]["outcome"] == "skipped"


def test_failing_checks_reject_and_leave_everything_as_it_was(repo):
    if shutil.which("lake"):
        pytest.skip("a Lean toolchain is installed; this test needs compilation to fail")
    before = tree(repo)
    rows = pr.apply(repo, submit(repo), run_checks=True, echo=quiet)
    assert rows[0]["outcome"] == "rejected"
    assert tree(repo) == before                                               # nothing changed, no tag
    assert [n.id for n in pr.open_theorems(load_dag(repo))] == [TID]           # a revised proposal can follow


@pytest.mark.parametrize("lean, prop, why", [
    ("axiom x : False\n" + GOOD_LEAN, None, "Lean file rejected"),
    (GOOD_LEAN.replace(f"namespace {NS}", "namespace Other").replace(f"end {NS}", "end Other"), None, "namespace"),
    (GOOD_LEAN, proposal(lean_decl="MBQC.Core.counts_add"), "lean_decl must be"),
    (GOOD_LEAN, proposal(depends_on=[{"node": "core.missing"}]), "unknown node"),
    (GOOD_LEAN, proposal(depends_on=[{"node": "core.additivity", "kind": "variant_of"}]), "not allowed"),
    (GOOD_LEAN, proposal(extra_checks=[{"kind": "reproduction", "params": {"expect": 1}}]), "cannot choose checks"),
    (GOOD_LEAN, proposal(node="paper.p_abc.other"), "names node"),
    (GOOD_LEAN, proposal(outcome="proved!"), "unknown outcome"),
    (None, None, "no theorem.lean"),
    (GOOD_LEAN, False, "no proposal.json"),
])
def test_bad_proposals_are_rejected_without_a_trace(repo, lean, prop, why):
    before = tree(repo)
    rows = pr.apply(repo, submit(repo, lean, prop), run_checks=False, echo=quiet)
    assert rows[0]["outcome"] == "rejected" and why in rows[0]["reason"], rows
    assert tree(repo) == before


@pytest.mark.parametrize("outcome, tag", [("unproved", "unproved"), ("not_formalizable", "not-formalizable"),
                                          ("counterexample", "counterexample-suspected")])
def test_honest_non_results_are_recorded(repo, outcome, tag):
    rows = pr.apply(repo, submit(repo, prop=proposal(outcome=outcome, reason="needs a definition of fidelity")),
                    run_checks=False, echo=quiet)
    assert rows[0]["outcome"] == tag
    r = raw(repo)
    assert tag in r["tags"] and "needs a definition of fidelity" in r["notes"] and "checks" not in r
    from dagtool.status import compute
    from dagtool.verdict import verdict
    dag = load_dag(repo)
    v = verdict(dag, TID, compute(dag))
    assert v["state"] == "open" and "see notes" in v["reason"]


@pytest.mark.parametrize("prop", [None, proposal(outcome="unproved")])
def test_feedback_is_the_same_verdict_and_changes_nothing(repo, prop):
    before = tree(repo)
    fb = pr.feedback(repo, submit(repo, prop=prop) / TID, run_checks=False)
    assert fb["dry_run"] and fb["accepted"] and fb["outcome"] in ("formalized", "unproved")
    assert tree(repo) == before
    assert [n.id for n in pr.open_theorems(load_dag(repo))] == [TID]


def test_feedback_keeps_crlf_checkouts_byte_identical(repo):
    """A Windows checkout (CRLF) must come back byte for byte, not rewritten as LF."""
    files = [p for p in repo.rglob("*") if p.is_file() and p.suffix in (".yaml", ".lean")]
    for p in files:
        p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    before = {p: p.read_bytes() for p in files}
    pr.feedback(repo, submit(repo, prop=proposal(outcome="unproved")) / TID, run_checks=False)
    assert {p: p.read_bytes() for p in files} == before


def test_feedback_reports_rejections(repo):
    fb = pr.feedback(repo, submit(repo, prop=proposal(extra_checks=[{"kind": "scaling"}])) / TID, run_checks=False)
    assert fb["outcome"] == "rejected" and "cannot choose checks" in fb["reason"]


def test_proposal_paths_allow_only_proposal_files():
    ok, bad = pr.proposal_paths([f"proposals/{TID}/proposal.json", f"proposals/{TID}/theorem.lean",
                                 f"proposals/{TID}/attempts.json"])
    assert ok and not bad
    for path in ("checks/_kinds.py", "checks/scaling/bilinear_formula.py", f"dag/predicates/{TID}.py", f"proposals/{TID}/run.sh", "proposals/x/proposal.json",
                 f"proposals/{TID}/sub/theorem.lean", "dag/nodes/papers/x.yaml", ".github/workflows/proposals.yml"):
        assert not pr.proposal_paths([path])[0], path


def test_reproduction_feedback_scores_candidate_results(tmp_path):
    dag = load_dag(REPO)
    node = "saadatmand2024.qft.n4"
    shutil.copy(REPO / "experiments/rre/results/calibrated/table2_qft_N-4.json", tmp_path)
    fb = pr.reproduction_feedback(dag, node, tmp_path)
    assert fb["of"] == 9 and fb["passed"] == 9
    d = json.loads((tmp_path / "table2_qft_N-4.json").read_text())
    d["quantities"]["time_s"]["ours"] *= 3
    (tmp_path / "table2_qft_N-4.json").write_text(json.dumps(d))
    fb = pr.reproduction_feedback(dag, node, tmp_path)
    assert fb["passed"] == 8 and next(c for c in fb["checks"] if c["name"] == "reproduction-time-s")["outcome"] == "fail"


def test_lean_check_refuses_files_outside_papers_and_forbidden_content(repo):
    ok, msg = pr.lean_check(repo, "lean/MBQC.lean")
    assert not ok and "only files under" in msg
    write(repo, "lean/MBQC/Papers/X/T.lean", "axiom bad : False\n")
    ok, msg = pr.lean_check(repo, "lean/MBQC/Papers/X/T.lean")
    assert not ok and "declares an axiom" in msg


def test_scrubbed_env_drops_credentials(monkeypatch):
    for k in ("GITHUB_TOKEN", "SOME_SERVICE_API_KEY", "MY_SECRET", "DB_PASSWORD"):
        monkeypatch.setenv(k, "x")
    env = pr.scrubbed_env()
    assert not {"GITHUB_TOKEN", "SOME_SERVICE_API_KEY", "MY_SECRET", "DB_PASSWORD"} & set(env)


def test_the_verifier_calls_no_model():
    """No code path in the verifier invokes a model or a model CLI."""
    names = ("claude", "anthropic", "openai", "codex", "gemini")
    hits = []
    for folder in ("tools", "verification", "src", "experiments", ".github"):
        for p in (REPO / folder).rglob("*"):
            if p.is_file() and p.suffix in (".py", ".yml", ".yaml", ".sh", ".toml", ".html") and "results" not in p.parts:
                text = p.read_text(encoding="utf-8", errors="ignore").lower()
                hits += [f"{p.relative_to(REPO)}: {n}" for n in names if n in text]
    assert not hits, hits


def test_reproduction_feedback_refuses_a_moved_target(tmp_path):
    dag = load_dag(REPO)
    shutil.copy(REPO / "experiments/rre/results/calibrated/table2_qft_N-4.json", tmp_path)
    d = json.loads((tmp_path / "table2_qft_N-4.json").read_text())
    d["quantities"]["time_s"]["paper"] = d["quantities"]["time_s"]["ours"] = 1.0
    (tmp_path / "table2_qft_N-4.json").write_text(json.dumps(d))
    fb = pr.reproduction_feedback(dag, "saadatmand2024.qft.n4", tmp_path)
    row = next(c for c in fb["checks"] if c["name"] == "reproduction-time-s")
    assert row["outcome"] == "error" and "frozen" in row["summary"]


def test_candidates_only_from_the_declared_space():
    import sys
    sys.path.insert(0, str(REPO / "experiments" / "rre"))
    from candidates import validate
    good = {"settings": {"target_p_algo": 0.05, "coeffs": "paper", "factories": "rre", "gate_ns": 200},
            "families": {"fh": {"widgets": "q40", "qubit_manager": "greedy-fifo"}}, "instances": ["fh:4"]}
    assert validate(good) == []
    bad = {"settings": {"target_p_algo": 0.07, "coeffs": "paper", "factories": "rre", "gate_ns": 200, "new_knob": 1},
           "families": {"fh": {"widgets": "q12", "qubit_manager": "greedy-fifo"}}, "instances": ["fh:8"], "extra": 1}
    errs = validate(bad)
    for frag in ("0.07", "new_knob", "fh:8", "q12", "extra"):
        assert any(frag in e for e in errs), (frag, errs)
