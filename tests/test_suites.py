"""Proposed test suites: the policy decides what a suite must and may hold, checks.py is scanned, and suite_diff
classifies a revision (the Quantum Genesis dashboard holds a revision to its diagnosis with it)."""

from __future__ import annotations

import copy
import json
import shutil

import pytest

from dagtool import proposals as pr
from dagtool.model import load_dag
from dagtool.suites import load_policy, scan_python, suite_diff, validate_suite
from verification.base import load_all

from test_proofs import LEAN_OK, REPO
from test_proposals import CHECKS_PY, NS, SUITE, TID, quiet, raw, repo, submit, tree  # noqa: F401


def test_policy_names_only_implemented_kinds():
    pol = load_policy(REPO)
    kinds = set(load_all())
    assert set(pol["required"]) <= kinds
    for name, spec in pol["claim_types"].items():
        assert set(spec["allowed"]) <= kinds, name
        assert all(set(g) <= set(spec["allowed"]) for g in spec["require_one_of"]), name


def v(repo, suite, checks=CHECKS_PY):
    return validate_suite(repo, TID, NS, suite, checks)


def test_a_good_suite_is_recorded_with_its_origin_and_rationale(repo):
    errs, out = v(repo, SUITE)
    assert errs == [] and out[0]["origin"] == "proposal" and out[0]["rationale"]
    assert out[0]["params"]["predicate"] == f"checks/papers/{TID}.py:counts_add"


@pytest.mark.parametrize("change, why", [
    (lambda s: s.update(claim_type="anything"), "claim_type must be one of"),
    (lambda s: s["checks"].append({"kind": "lean", "name": "x", "rationale": "r"}), "added by the verifier"),
    (lambda s: s["checks"].append({"kind": "scaling", "name": "x", "rationale": "r"}), "not allowed for claim type"),
    (lambda s: s["checks"][0].update(rationale=""), "rationale"),
    (lambda s: s["checks"].append(copy.deepcopy(s["checks"][0])), "name must be unique"),
    (lambda s: s["checks"][0]["params"].update(predicate="checks.py:nope"), "a function in the proposal's checks.py"),
    (lambda s: s["checks"][0]["params"].update(domain={"a": {"range": [0, 5000]}, "b": {"range": [0, 5000]}}),
     "more than"),
    (lambda s: s.update(checks=[{"kind": "equivalence", "name": "e", "rationale": "r",
                                  "params": {"other": "Other.x", "proof": f"{NS}.p"}}]), "must be a declaration in"),
    (lambda s: s.update(checks=[{"kind": "refuter", "name": "h", "rationale": "r", "params": {
        "source": "hypothesis", "predicate": "checks.py:counts_add", "strategy": {"a": {"integers": [0, 9]}},
        "max_examples": 10}}]), "max_examples must be in"),
    (lambda s: s.update(checks=[{"kind": "refuter", "name": "h", "rationale": "r", "params": {
        "predicate": "checks.py:counts_add", "strategy": {"a": {"integers": [0, 9]}}}}]), "source: hypothesis"),
    (lambda s: s.update(claim_type="resource_estimate", checks=[{"kind": "tool", "name": "t", "rationale": "r",
        "params": {"tool": "qualtran.cost", "args": {}, "path": "t", "expect": 4, "domain": "d"}}]), "never from the proposal"),
    (lambda s: s.update(claim_type="logical_error_model", checks=[{"kind": "tool", "name": "t", "rationale": "r",
        "params": {"tool": "qualtran.cost", "path": "t", "expect": {"heldout": "x"}, "domain": "d"}}]), "uses tools"),
    (lambda s: s.update(checks=[]), "needs at least one of"),
])
def test_bad_suites_are_refused(repo, change, why):
    s = copy.deepcopy(SUITE)
    change(s)
    errs, _ = v(repo, s)
    assert any(why in e for e in errs), errs


@pytest.mark.parametrize("code, why", [
    ("import os\ndef f(n):\n    return True\n", "imports os"),
    ("def f(n):\n    return open('x').read() == ''\n", "uses open"),
    ("def f(n):\n    return ().__class__.__bases__ is not None\n", "private name"),
    ("def f(n):\n    return eval('1') == 1\n", "uses eval"),
    ("print('hi')\ndef f(n):\n    return True\n", "runs code at import"),
    ("class A:\n    pass\n", "ClassDef"),
    ("from . import x\n", "relative import"),
    ("def f(n):\n    return getattr(n, 'real')\n", "uses getattr"),
    ("def f(n):\n    with x:\n        return 1\n", "With"),
    ("def f(n):\n    try:\n        return 1\n    except Exception:\n        return 0\n", "Try"),
])
def test_checks_py_is_scanned(code, why):
    probs = scan_python(code, load_policy(REPO)["predicate_imports"])
    assert any(why in p for p in probs), probs


def test_checks_py_may_do_arithmetic():
    ok = "import math\nfrom fractions import Fraction\n\nN = 3\n\ndef f(n, k=2):\n    return math.comb(n, k) == Fraction(n * (n - 1), 2)\n"
    assert scan_python(ok, load_policy(REPO)["predicate_imports"]) == []


# ------------------------------------------------------------------ suite_diff

BASE = {"claim_type": "count_formula", "checks": [
    {"kind": "finite", "name": "small", "params": {"predicate": "checks.py:f", "domain": {"n": {"range": [1, 20]}}}},
    {"kind": "refuter", "name": "big", "params": {"source": "hypothesis", "predicate": "checks.py:f",
                                                  "strategy": {"n": {"integers": [1, 999]}}, "max_examples": 500}}]}


def edit(fn):
    s = copy.deepcopy(BASE)
    fn(s)
    return s


@pytest.mark.parametrize("new, expect", [
    (edit(lambda s: None), {"unchanged": ["big", "small"]}),
    (edit(lambda s: s["checks"].append({"kind": "finite", "name": "more", "params": {}})), {"added": ["more"]}),
    (edit(lambda s: s["checks"].pop(1)), {"removed": ["big"]}),
    (edit(lambda s: s["checks"][0]["params"].update(domain={"n": {"range": [1, 40]}})), {"tightened": ["small"]}),
    (edit(lambda s: s["checks"][0]["params"].update(domain={"n": {"range": [5, 20]}})), {"loosened": ["small"]}),
    (edit(lambda s: s["checks"][0]["params"].update(domain={"n": {"range": [30, 60]}})), {"modified": ["small"]}),
    (edit(lambda s: s["checks"][1]["params"].update(max_examples=5000)), {"tightened": ["big"]}),
    (edit(lambda s: s["checks"][1]["params"].update(max_examples=200)), {"loosened": ["big"]}),
    (edit(lambda s: s["checks"][1]["params"].update(predicate="checks.py:g")), {"modified": ["big"]}),
    (edit(lambda s: s["checks"][0].update(rationale="reworded")), {"unchanged": ["big", "small"]}),
    (edit(lambda s: s.update(claim_type="exact_statement")), {"modified": ["claim_type"]}),
])
def test_suite_diff_classifies_each_change(new, expect):
    d = suite_diff(BASE, new)
    for k in ("added", "removed", "tightened", "loosened", "modified"):
        assert d[k] == expect.get(k, []), (k, d)
    assert d["needs_signoff"] == bool(expect.get("removed") or expect.get("loosened") or expect.get("modified"))


def test_tool_shots_and_tolerance():
    a = {"claim_type": "resource_estimate", "checks": [{"kind": "tool", "name": "t", "params": {
        "tool": "surface_code.memory", "args": {"distance": 3, "p": 0.003, "shots": 1000}, "rel_tol": 0.1}}]}
    more = copy.deepcopy(a)
    more["checks"][0]["params"]["args"]["shots"] = 5000
    looser = copy.deepcopy(a)
    looser["checks"][0]["params"]["rel_tol"] = 0.5
    assert suite_diff(a, more)["tightened"] == ["t"] and suite_diff(a, looser)["loosened"] == ["t"]


# ------------------------------------------------------------------ through the gate

def test_a_formalization_needs_a_suite(repo):
    rows = pr.apply(repo, submit(repo, suite=False), run_checks=False, echo=quiet)
    assert rows[0]["outcome"] == "rejected" and "suite.json is required" in rows[0]["reason"]
    rows = pr.apply(repo, submit(repo, checks="import os\n"), run_checks=False, echo=quiet)
    assert rows[0]["outcome"] == "rejected" and "checks.py refused" in rows[0]["reason"]


@pytest.fixture
def lean_repo(repo):
    shutil.rmtree(repo / "lean")
    shutil.copytree(REPO / "lean", repo / "lean", ignore=shutil.ignore_patterns("Papers"))
    (repo / "lean/MBQC.lean").write_text("\n".join(l for l in (REPO / "lean/MBQC.lean").read_text().splitlines()
                                                   if "MBQC.Papers." not in l) + "\n")
    return repo


@pytest.mark.skipif(not LEAN_OK, reason="Lean (lake) not installed")
def test_the_suite_runs_with_the_fixed_checks_and_reports_each(lean_repo):
    before = tree(lean_repo)
    fb = pr.feedback(lean_repo, submit(lean_repo) / TID, run_checks=True)
    assert fb["outcome"] == "formalized", fb.get("compiler", fb)
    by = {c["name"]: c for c in fb["checks"]}
    assert by["small"]["outcome"] == "pass" and by["small"]["origin"] == "proposal"
    assert by["lean"]["origin"] == "verifier" and by["lean"]["outcome"] == "pass"
    shutil.rmtree(lean_repo / "in")
    assert tree(lean_repo) == before and not list(lean_repo.rglob("__pycache__")) and not (lean_repo / "checks").exists()


@pytest.mark.skipif(not LEAN_OK, reason="Lean (lake) not installed")
def test_a_failing_proposed_check_rejects_with_its_counterexample(lean_repo):
    wrong = "def counts_add(a, b):\n    return a + max(b - a, 0) == b\n"   # the truncated subtraction, without a <= b
    before = tree(lean_repo)
    fb = pr.feedback(lean_repo, submit(lean_repo, checks=wrong) / TID, run_checks=True)
    assert fb["outcome"] == "rejected" and "small" in fb["reason"], fb
    small = next(c for c in fb["checks"] if c["name"] == "small")
    assert small["outcome"] == "fail" and small["origin"] == "proposal" and "fails at" in small["summary"]
    assert all(c["outcome"] == "pass" for c in fb["checks"] if c["origin"] == "verifier")
    shutil.rmtree(lean_repo / "in")
    assert tree(lean_repo) == before
