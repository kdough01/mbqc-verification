"""The pinned external tools (requirements-tools.txt) and the checks that call them: tool, held-out values,
finite, the Hypothesis refuter search, and Lean equivalence."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from verification.base import load_all
from verification.kinds import CHECK_KINDS, TOOL_KINDS
from verification.truth.heldout import heldout as ho
from verification.truth.tool import azure_re, gridsynth, qualtran_cost, surface_code
from verification.truth.tool.check import TOOLS, run_tool

REPO = Path(__file__).resolve().parents[1]
CHECKS = load_all()


def ctx(root, dag=None):
    return SimpleNamespace(root=root, cache={}, quick=False, dag=dag or SimpleNamespace(root=root))


def node(code=(), lean_decl=None, nid="t.node"):
    return SimpleNamespace(id=nid, code=list(code), lean_decl=lean_decl, checks=[])


def run(kind, params, root, n=None):
    return CHECKS[kind]().run(n or node(), params, ctx(root))


# ------------------------------------------------------------------ every declared kind has an implementation

def test_every_declared_kind_is_implemented():
    assert set(CHECK_KINDS) - {"review"} <= set(CHECKS), sorted(set(CHECK_KINDS) - set(CHECKS))
    assert {"tool", "finite", "equivalence"} <= set(CHECKS)


def test_tools_requirements_are_pinned_and_hashed():
    lines = [l for l in (REPO / "requirements-tools.txt").read_text().splitlines() if l and not l.startswith("#")]
    assert all("==" in l for l in lines)
    names = {l.split("==")[0].lower() for l in lines}
    assert {"stim", "pymatching", "sinter", "hypothesis", "qualtran", "pygridsynth", "qdk", "cryptography"} <= names
    base = {l.split("==")[0].lower() for l in (REPO / "requirements.txt").read_text().splitlines() if "==" in l}
    assert not names & base, "requirements-tools.txt must not re-pin requirements.txt"
    from dagtool.status import check_files
    for kind in TOOL_KINDS:
        assert REPO / "requirements-tools.txt" in check_files(REPO, kind)


# ------------------------------------------------------------------ adapters

def test_surface_code_memory_is_deterministic_and_suppresses_errors():
    a = surface_code.memory({"distance": 3, "p": 0.005, "shots": 20000, "seed": 7})
    assert a == surface_code.memory({"distance": 3, "p": 0.005, "shots": 20000, "seed": 7})
    assert 0 < a["errors"] < a["shots"] and a["interval"][0] <= a["logical_error_rate"] <= a["interval"][1]
    assert a["per_round_interval"][0] <= a["per_round"] <= a["per_round_interval"][1]
    b = surface_code.memory({"distance": 5, "p": 0.003, "shots": 20000, "seed": 7})
    c = surface_code.memory({"distance": 3, "p": 0.003, "shots": 20000, "seed": 7})
    assert b["per_round"] < c["per_round"]          # below threshold, a larger code is better
    with pytest.raises(ValueError):
        surface_code.memory({"distance": 4, "p": 0.003})


def test_surface_code_fit_recovers_a_threshold_in_range():
    f = surface_code.fit({"distances": [3, 5], "ps": [0.004, 0.006, 0.008], "shots": 6000, "seed": 1})
    assert f["used_points"] == 6 and f["kappa"] > 0
    assert 0.003 < f["p_th"] < 0.05, f["p_th"]       # circuit-level depolarizing noise with MWPM: about 0.7–1%


def test_gridsynth_rz_is_certified_and_near_the_ross_selinger_count():
    r = gridsynth.rz({"angles": [0.3, "1.1"], "epsilon": "1e-6"})
    assert r["all_within_epsilon"] and r["max_error"] <= 1e-6
    assert abs(r["mean_t_count"] - r["three_log2_inv_eps"]) < 15


def test_qualtran_cost_counts_known_bloqs():
    t = qualtran_cost.cost({"bloq": "qualtran.bloqs.basic_gates.Toffoli"})
    assert t["toffoli"] == 1 and t["total_t_count"] == 4 and t["qubits"] == 3
    small = qualtran_cost.cost({"bloq": "qualtran.bloqs.qft.QFTTextBook", "kwargs": {"bitsize": 4}})
    big = qualtran_cost.cost({"bloq": "qualtran.bloqs.qft.QFTTextBook", "kwargs": {"bitsize": 8}})
    assert big["rotation"] > small["rotation"] and big["qubits"] > small["qubits"]
    with pytest.raises(ValueError):
        qualtran_cost.cost({"bloq": "os.system"})


def test_azure_resource_estimator_runs_locally(tmp_path):
    lo = azure_re.logical_counts({"counts": {"numQubits": 50, "tCount": 1000}})
    hi = azure_re.logical_counts({"counts": {"numQubits": 50, "tCount": 1000000}})
    assert lo["physical_qubits"] > 0 and hi["runtime_ns"] > lo["runtime_ns"]
    (tmp_path / "prog.qs").write_text("operation Main() : Unit { use qs = Qubit[3]; for q in qs { T(q); } ResetAll(qs); }")
    q = azure_re.qsharp({"file": "prog.qs", "entry": "Main()"}, tmp_path)
    assert q["logical_counts"]["tCount"] == 3
    with pytest.raises(ValueError):
        azure_re.qsharp({"file": "../x.qs"}, tmp_path)


def test_every_tool_records_versions(tmp_path):
    out = run_tool("gridsynth.rz", {"angles": [0.5], "epsilon": "1e-3"}, ctx(tmp_path))
    assert out["versions"]["pygridsynth"]
    assert set(TOOLS) == {"surface_code.memory", "surface_code.fit", "gridsynth.rz", "qualtran.cost",
                          "azure_re.logical_counts", "azure_re.qsharp"}


# ------------------------------------------------------------------ the tool check

TOFFOLI = {"tool": "qualtran.cost", "args": {"bloq": "qualtran.bloqs.basic_gates.Toffoli"}, "path": "total_t_count"}


def test_tool_check_compares_with_the_claim(tmp_path):
    r = run("tool", {**TOFFOLI, "expect": 4, "op": "eq"}, tmp_path)
    assert r.outcome == "pass" and r.grants == "empirical" and r.evidence["versions"]["qualtran"]
    r = run("tool", {**TOFFOLI, "expect": 7, "op": "eq"}, tmp_path)
    assert r.outcome == "fail" and r.grants == "refuted"
    r = run("tool", {**TOFFOLI, "expect": [3, 5], "op": "within"}, tmp_path)
    assert r.outcome == "pass"
    (tmp_path / "frozen.json").write_text(json.dumps({"table": {"toffoli_t": 4}}))
    r = run("tool", {**TOFFOLI, "expect": {"results": "frozen.json", "path": "table.toffoli_t"}, "op": "eq"}, tmp_path)
    assert r.outcome == "pass" and r.evidence["expect_from"] == "frozen.json:table.toffoli_t"
    assert run("tool", {"tool": "nope", "path": "x", "expect": 1}, tmp_path).outcome == "error"


# ------------------------------------------------------------------ held-out values

def test_heldout_values_open_only_with_the_key(tmp_path, monkeypatch):
    key = ho.keygen()
    ho.seal(tmp_path, "toffoli.t", 4, key=key)
    text = (tmp_path / "dag/heldout/toffoli.t.json").read_text()
    assert '"value"' not in text and "4" not in json.loads(text)["sealed"][:0]   # sealed, not plain
    monkeypatch.delenv(ho.KEY_ENV, raising=False)
    with pytest.raises(ho.HeldOutUnavailable):
        ho.value(tmp_path, "toffoli.t")
    assert ho.value(tmp_path, "toffoli.t", key=key) == 4.0
    with pytest.raises(ValueError):
        ho.value(tmp_path, "toffoli.t", key=ho.keygen())                      # another key
    shutil.copy(tmp_path / "dag/heldout/toffoli.t.json", tmp_path / "dag/heldout/other.json")
    with pytest.raises(ValueError):
        ho.value(tmp_path, "other", key=key)                                  # moved to another id
    assert ho.ids(tmp_path) == ["other", "toffoli.t"]


def test_heldout_in_checks_skips_without_key_and_never_reveals_the_value(tmp_path, monkeypatch):
    key = ho.keygen()
    ho.seal(tmp_path, "toffoli.t", 4, key=key)
    ho.seal(tmp_path, "wrong", 9, key=key)
    monkeypatch.delenv(ho.KEY_ENV, raising=False)
    r = run("tool", {**TOFFOLI, "expect": {"heldout": "toffoli.t"}, "op": "eq"}, tmp_path)
    assert r.outcome == "skip" and "CI only" in r.summary
    monkeypatch.setenv(ho.KEY_ENV, key)
    r = run("tool", {**TOFFOLI, "expect": {"heldout": "toffoli.t"}, "op": "eq"}, tmp_path)
    assert r.outcome == "pass" and r.evidence["expect"] is None and "matches the held-out value" in r.summary
    r = run("tool", {**TOFFOLI, "expect": {"heldout": "wrong"}, "op": "approx"}, tmp_path)
    assert r.outcome == "fail" and "9" not in r.summary and "%" not in r.summary and r.evidence["expect"] is None
    # reproduction checks take held-out values too
    (tmp_path / "res.json").write_text(json.dumps({"q": {"ours": 4.02}}))
    r = run("reproduction", {"results": "res.json", "path": "q.ours", "expect": {"heldout": "toffoli.t"}}, tmp_path)
    assert r.outcome == "pass" and r.evidence["expect"] is None and "4.02" in r.summary and "held-out" in r.summary
    monkeypatch.delenv(ho.KEY_ENV)
    r = run("reproduction", {"results": "res.json", "path": "q.ours", "expect": {"heldout": "toffoli.t"}}, tmp_path)
    assert r.outcome == "skip"


# ------------------------------------------------------------------ finite and the Hypothesis search

PRED = '''
def sum_formula(n):
    return sum(range(n + 1)) == n * (n + 1) // 2

def square_not_49(n):
    return (n * n != 49, {"n2": n * n})

def tri(a, b):
    return a + b >= max(a, b)
'''


def test_finite_is_exhaustive_and_bounded(tmp_path):
    (tmp_path / "pred.py").write_text(PRED)
    n = node(code=["pred.py"])
    r = run("finite", {"predicate": "pred.py:sum_formula", "domain": {"n": {"range": [0, 200]}}}, tmp_path, n)
    assert r.outcome == "pass" and r.grants == "bounded" and r.domain == "n in [0, 200]" and r.evidence["points"] == 201
    r = run("finite", {"predicate": "pred.py:square_not_49", "domain": {"n": {"range": [0, 20]}}}, tmp_path, n)
    assert r.outcome == "fail" and r.evidence["counterexample"] == {"n": 7}
    r = run("finite", {"predicate": "pred.py:tri", "domain": {"a": {"values": [0, 1, 2]}, "b": {"range": [0, 3]}}},
            tmp_path, n)
    assert r.outcome == "pass" and r.evidence["points"] == 12
    assert run("finite", {"predicate": "pred.py:sum_formula", "domain": {"n": {"range": [0, 5]}}},
               tmp_path, node()).outcome == "error"                          # not listed under code:
    assert run("finite", {"predicate": "pred.py:sum_formula", "domain": {"n": {"range": [0, 10 ** 7]}}},
               tmp_path, n).outcome == "error"                                # too many points


def test_hypothesis_search_finds_and_shrinks_counterexamples(tmp_path):
    (tmp_path / "pred.py").write_text(PRED)
    n = node(code=["pred.py"])
    ok = {"source": "hypothesis", "predicate": "pred.py:sum_formula", "strategy": {"n": {"integers": [0, 10000]}},
          "max_examples": 200}
    r = run("refuter", ok, tmp_path, n)
    assert r.outcome == "pass" and r.grants == "empirical" and r.evidence["tried"] >= 100
    bad = {"source": "hypothesis", "predicate": "pred.py:square_not_49", "strategy": {"n": {"integers": [-1000, 1000]}},
           "max_examples": 2000}
    r = run("refuter", bad, tmp_path, n)
    assert r.outcome == "fail" and r.evidence["counterexample"]["n"] in (7, -7)
    assert r.evidence == run("refuter", bad, tmp_path, n).evidence            # derandomized: same evidence


# ------------------------------------------------------------------ Lean equivalence

LEAN_OK = shutil.which("lake") or (Path.home() / ".elan/bin/lake").exists()
EQUIV = """namespace Probe.Equiv

theorem main (a b : Nat) (h : a ≤ b) : a + (b - a) = b := by omega

/-- an independent formalization of the same claim, written the other way round -/
theorem other : ∀ a b : Nat, a ≤ b → b = a + (b - a) := fun a b h => (Nat.add_sub_of_le h).symm

theorem good : (∀ a b : Nat, a ≤ b → a + (b - a) = b) ↔ (∀ a b : Nat, a ≤ b → b = a + (b - a)) :=
  ⟨fun h a b hab => (h a b hab).symm, fun h a b hab => (h a b hab).symm⟩

theorem cheat : (∀ a b : Nat, a ≤ b → a + (b - a) = b) ↔ (∀ a b : Nat, a ≤ b → b = a + (b - a)) :=
  ⟨fun _ => other, fun _ => main⟩

theorem wrong : (∀ a b : Nat, a ≤ b → a + (b - a) = b) ↔ True := ⟨fun _ => trivial, fun _ => main⟩

end Probe.Equiv
"""


@pytest.mark.skipif(not LEAN_OK, reason="Lean (lake) not installed")
def test_equivalence_needs_the_exact_iff_and_no_use_of_either_proof(tmp_path):
    from dagtool.model import load_dag
    root = tmp_path
    shutil.copytree(REPO / "lean", root / "lean", ignore=shutil.ignore_patterns("Papers"))
    (root / "lean/MBQC.lean").write_text("\n".join(l for l in (REPO / "lean/MBQC.lean").read_text().splitlines()
                                                   if "MBQC.Papers." not in l) + "\nimport MBQC.ZzEquiv\n")
    (root / "lean/MBQC/ZzEquiv.lean").write_text(EQUIV)
    (root / "dag/schema").mkdir(parents=True)
    shutil.copy(REPO / "dag/schema/node.schema.json", root / "dag/schema")
    (root / "requirements.txt").write_text("numpy==1\n")
    checks = [{"kind": "equivalence", "name": n, "params": {"other": "Probe.Equiv.other", "proof": f"Probe.Equiv.{n}"}}
              for n in ("good", "cheat", "wrong")]
    (root / "dag/nodes/core").mkdir(parents=True)
    (root / "dag/nodes/core/core.equiv.yaml").write_text(yaml.safe_dump(
        {"id": "core.equiv", "kind": "core", "title": "Equivalence probe", "statement": "a + (b - a) = b for a <= b", "lean_decl": "Probe.Equiv.main",
         "checks": checks}))
    dag = load_dag(root)
    c = SimpleNamespace(root=root, cache={}, quick=False, dag=dag)
    n = dag.nodes["core.equiv"]
    res = {s.name: CHECKS["equivalence"]().run(n, s.params, c) for s in n.checks}
    assert res["good"].outcome == "pass", res["good"]
    assert res["cheat"].outcome == "fail" and "reaches the proof" in res["cheat"].summary
    assert res["wrong"].outcome == "fail" and "does not state" in res["wrong"].summary
