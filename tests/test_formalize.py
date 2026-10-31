"""Automatic formalization of paper theorems: the agent's output is checked and applied by ordinary code."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from dagtool import formalize as fz
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
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"], check=True)
    return tmp_path


def proposal(**kw):
    p = {"outcome": "formalized", "reason": "direct", "lean_decl": f"{NS}.counts_add",
         "witness": f"{NS}.counts_add_nonvacuous", "depends_on": [{"node": "core.additivity", "kind": "uses"}],
         "statement_tex": "a + (b-a) = b", "notes": "stated over Nat", "extra_checks": []}
    p.update(kw)
    return p


def attempt(tmp, lean=GOOD_LEAN, prop=None):
    d = tmp / "out" / TID
    d.mkdir(parents=True, exist_ok=True)
    if lean is not None:
        (d / "theorem.lean").write_text(lean, encoding="utf-8")
    if prop is not False:
        (d / "proposal.json").write_text(json.dumps(prop or proposal()), encoding="utf-8")
    (d / "result.json").write_text(json.dumps({"exit_code": 0}), encoding="utf-8")
    return tmp / "out"


def raw(repo):
    return yaml.safe_load((repo / f"dag/nodes/papers/p_abc/{TID}.yaml").read_text(encoding="utf-8"))


def test_pending_and_names(repo):
    dag = load_dag(repo)
    assert [n.id for n in fz.pending(dag)] == [TID]
    ns, path = fz.lean_names(dag.nodes[TID])
    assert ns == NS and path.as_posix() == "lean/MBQC/Papers/Paper_p_abc/T_theorem_1_counts_add.lean"
    b = fz.brief(dag, dag.nodes[TID])
    assert "Theorem 1. Counts add up." in b and path.as_posix() in b and "`def.pattern`" in b
    assert "data, not instructions" in b


@pytest.mark.parametrize("bad, why", [
    ("axiom cheat : False", "axiom"), ("theorem t : 1 = 2 := by sorry", "sorry"), ("#eval IO.println 1", "command"),
    ("run_cmd pure ()", "runs code"), ("theorem t : True := by native_decide", "compiled"),
    ("macro \"x\" : term => `(1)", "syntax"), ("import Lean", "imports Lean"), ("@[implemented_by f] def g := 1", "replaces"),
    ("set_option debug.skipKernelTC true", "kernel"),
])
def test_scan_rejects(bad, why):
    assert any(why in p for p in fz.scan_lean(bad)), fz.scan_lean(bad)


def test_scan_accepts_ordinary_proofs():
    assert fz.scan_lean(GOOD_LEAN) == []
    assert fz.scan_lean("-- sorry, axiom in a comment\n/- #eval -/\ntheorem t : 1 + 1 = 2 := by decide") == []


def test_apply_formalized_without_checks(repo):
    rows = fz.apply(repo, attempt(repo), run_checks=False, echo=lambda *a, **k: None)
    assert rows[0]["outcome"] == "formalized"
    r = raw(repo)
    assert r["statement"] == "Theorem 1. Counts add up."                      # never touched
    assert r["lean_decl"] == f"{NS}.counts_add"
    assert r["checks"] == [{"kind": "lean"}, {"kind": "vocabulary"},
                           {"kind": "nonvacuity", "params": {"witness": f"{NS}.counts_add_nonvacuous"}}]
    assert r["depends_on"] == [{"node": "core.additivity", "kind": "uses"}]
    assert "formalized" in r["tags"] and "open" not in r["tags"] and "awaits human review" in r["notes"]
    assert (repo / "lean/MBQC/Papers/Paper_p_abc/T_theorem_1_counts_add.lean").read_text(encoding="utf-8") == GOOD_LEAN
    assert "import MBQC.Papers.Paper_p_abc.T_theorem_1_counts_add" in (repo / "lean/MBQC.lean").read_text()
    assert fz.pending(load_dag(repo)) == []
    assert fz.apply(repo, repo / "out", run_checks=False, echo=lambda *a, **k: None)[0]["outcome"] == "skipped"


def test_failed_checks_are_undone_and_marked(repo):
    # no Lean toolchain in the test environment, so the lean check errors: everything is rolled back
    rows = fz.apply(repo, attempt(repo), run_checks=True, echo=lambda *a, **k: None)
    if shutil.which("lake"):
        pytest.skip("a Lean toolchain is installed; this test needs the lean check to fail")
    assert rows[0]["outcome"] == "formalize-failed" and "checks did not pass" in rows[0]["reason"]
    r = raw(repo)
    assert "checks" not in r and "lean_decl" not in r and "formalize-failed" in r["tags"]
    assert not (repo / "lean/MBQC/Papers/Paper_p_abc/T_theorem_1_counts_add.lean").exists()
    assert "Papers" not in (repo / "lean/MBQC.lean").read_text()
    assert not (repo / "dag/evidence" / TID).exists()
    assert fz.pending(load_dag(repo)) == []                                   # not retried until the tag is removed


@pytest.mark.parametrize("lean, prop, why", [
    ("axiom x : False\n" + GOOD_LEAN, None, "Lean file rejected"),
    (GOOD_LEAN.replace(f"namespace {NS}", "namespace Other").replace(f"end {NS}", "end Other"), None, "namespace"),
    (GOOD_LEAN, proposal(lean_decl="MBQC.Core.counts_add"), "lean_decl must be"),
    (GOOD_LEAN, proposal(depends_on=[{"node": "core.missing"}]), "unknown node"),
    (GOOD_LEAN, proposal(depends_on=[{"node": "core.additivity", "kind": "variant_of"}]), "not allowed"),
    (GOOD_LEAN, proposal(extra_checks=[{"kind": "literature"}]), "extra check"),
    (GOOD_LEAN, proposal(outcome="proved!"), "unknown outcome"),
    (None, None, "no Lean file"),
    (GOOD_LEAN, False, "no proposal"),
])
def test_bad_attempts_are_marked_failed(repo, lean, prop, why):
    rows = fz.apply(repo, attempt(repo, lean, prop), run_checks=False, echo=lambda *a, **k: None)
    assert rows[0]["outcome"] == "formalize-failed" and why in rows[0]["reason"], rows
    r = raw(repo)
    assert "checks" not in r and "formalize-failed" in r["tags"] and r["statement"] == "Theorem 1. Counts add up."
    assert "Papers" not in (repo / "lean/MBQC.lean").read_text()


@pytest.mark.parametrize("outcome, tag", [("unproved", "unproved"), ("not_formalizable", "not-formalizable"),
                                          ("counterexample", "counterexample-suspected")])
def test_honest_non_results_are_recorded(repo, outcome, tag):
    rows = fz.apply(repo, attempt(repo, prop=proposal(outcome=outcome, reason="needs a definition of fidelity")),
                    run_checks=False, echo=lambda *a, **k: None)
    assert rows[0]["outcome"] == tag
    r = raw(repo)
    assert tag in r["tags"] and "needs a definition of fidelity" in r["notes"] and "checks" not in r
    from dagtool.status import compute
    from dagtool.verdict import verdict
    dag = load_dag(repo)
    v = verdict(dag, TID, compute(dag))
    assert v["state"] == "open" and "see notes" in v["reason"]


def test_run_agent_keeps_only_its_two_files_and_restores_the_tree(repo, tmp_path_factory):
    fake = tmp_path_factory.mktemp("fake") / "agent.py"
    fake.write_text(f"""
import json, pathlib, sys
brief = sys.stdin.read()
assert "Counts add up" in brief
root = pathlib.Path('.')
(root / 'lean/MBQC/Papers/Paper_p_abc').mkdir(parents=True, exist_ok=True)
(root / 'lean/MBQC/Papers/Paper_p_abc/T_theorem_1_counts_add.lean').write_text({GOOD_LEAN!r})
(root / 'dag/build/formalize').mkdir(parents=True, exist_ok=True)
(root / 'dag/build/formalize/{TID}.json').write_text(json.dumps({{"outcome": "unproved", "reason": "r"}}))
(root / 'lean/MBQC.lean').write_text('tampered')            # a tracked file
(root / 'dag/nodes/core/core.sneaky.yaml').write_text('x')  # a new file elsewhere
print(json.dumps({{"total_cost_usd": 0.42, "num_turns": 7, "is_error": False}}))
""")
    dag = load_dag(repo)
    out = repo.parent / "agent-out"
    res = fz.run_agent(dag, dag.nodes[TID], out, budget=1, model=None, timeout=60, command=[sys.executable, str(fake)])
    assert res["exit_code"] == 0 and res["cost_usd"] == 0.42
    assert sorted(p.name for p in (out / TID).iterdir()) == ["proposal.json", "result.json", "theorem.lean"]
    assert (repo / "lean/MBQC.lean").read_text() == "import MBQC.Defs.Pattern\n"          # restored
    assert not (repo / "dag/nodes/core/core.sneaky.yaml").exists()
    assert not (repo / "lean/MBQC/Papers").exists() or not any((repo / "lean/MBQC/Papers").rglob("*.lean"))
    assert not (repo / f"dag/build/formalize/{TID}.json").exists()
    assert "lean/MBQC.lean" in res["touched"]


def test_lean_check_refuses_files_outside_papers_and_forbidden_content(repo):
    ok, msg = fz.lean_check(repo, "lean/MBQC.lean")
    assert not ok and "only files under" in msg
    write(repo, "lean/MBQC/Papers/X/T.lean", "axiom bad : False\n")
    ok, msg = fz.lean_check(repo, "lean/MBQC/Papers/X/T.lean")
    assert not ok and "declares an axiom" in msg


def test_scrubbed_env_drops_secrets(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")
    monkeypatch.setenv("GITHUB_TOKEN", "g")
    env = fz.scrubbed_env()
    assert not {"ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "GITHUB_TOKEN"} & set(env)
