"""Every file in checks/ follows the shape checks/README.md describes, and every node's checks name real tests.

A test is checks/<type>/<name>.py with a sectioned docstring, PARAMS/REQUIRED and run(); its Example validates;
the README tables are generated from the docstrings and up to date; the evidence of a test pins its helpers.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from checks import _framework as fw
from checks._kinds import CHECK_KINDS
from dagtool.model import load_dag

REPO = Path(__file__).resolve().parents[1]
TESTS = fw.discover()


def test_every_type_is_a_folder_with_tests_and_a_readme():
    folders = {p.name for p in (REPO / "checks").iterdir() if p.is_dir() and not p.name.startswith("_")
               and p.name != "__pycache__"}
    assert folders == set(CHECK_KINDS)
    for kind in CHECK_KINDS:
        assert (REPO / "checks" / kind / "__init__.py").exists(), kind
        assert (REPO / "checks" / kind / "README.md").exists(), kind
        assert any(t.type == kind for t in TESTS.values()), f"{kind} has no tests"


@pytest.mark.parametrize("test_id", sorted(TESTS))
def test_file_follows_the_contract(test_id):
    t = TESTS[test_id]
    assert t.problems() == [], t.problems()
    mod = importlib.import_module("checks." + test_id.replace("/", "."))
    assert callable(getattr(mod, "run", None))
    assert mod.PARAMS == t.params and list(mod.REQUIRED) == t.required     # what dagtool reads without importing


@pytest.mark.parametrize("test_id", sorted(TESTS))
def test_example_is_a_valid_checks_entry(test_id):
    examples = TESTS[test_id].examples()
    assert examples, "the Example section has no entry"
    for e in examples:
        assert e["test"] == test_id
        assert set(e) <= {"test", "name", "params", "origin", "rationale"}
        assert fw.validate(test_id, e.get("params") or {}) == []


def test_unknown_and_missing_params_are_refused_before_running():
    assert any("Additional properties" in e for e in fw.validate("scaling/no_cancel", {"method": "qsvt", "optimize": 1}))
    assert any("'method' is a required property" in e for e in fw.validate("scaling/no_cancel", {}))
    r = fw.run("scaling/no_cancel", None, {"method": "trotter9"}, None)
    assert r.outcome == "error" and "invalid params" in r.summary


def test_evidence_pins_the_helpers_a_test_imports():
    files = {p.relative_to(REPO).as_posix() for p in fw.source_files("scaling/bilinear_formula")}
    assert {"checks/scaling/bilinear_formula.py", "checks/scaling/_compare.py", "checks/_shared/grids.py"} <= files
    assert "checks/_framework.py" not in files
    files = {p.relative_to(REPO).as_posix() for p in fw.source_files("mutation/scaling_coefficients")}
    assert "checks/scaling/_compare.py" in files                  # a helper of another type, imported
    assert {p.name for p in fw.source_files("lean/proof")} >= {"proof.py", "_axioms.py", "lean.py"}


def test_readme_tables_are_up_to_date():
    from dagtool.readmes import readmes
    assert readmes(REPO, write=False) == [], "run `dagtool readmes`"
    index = (REPO / "checks" / "README.md").read_text()
    for t in TESTS.values():
        assert f"({t.type}/{t.name}.py)" in index
        assert f"[`{t.id}`]({t.name}.py)" in (REPO / "checks" / t.type / "README.md").read_text()


def test_every_node_check_names_a_test_with_valid_params():
    from dagtool.cli import _check_tests
    assert _check_tests(load_dag(REPO)) == []


def test_the_template_becomes_a_valid_test(tmp_path):
    text = (REPO / "checks" / "_template.py").read_text().replace("TYPE/NAME", "scaling/probe")
    (tmp_path / "scaling").mkdir()
    (tmp_path / "scaling" / "probe.py").write_text(text)
    t = fw.read_test(tmp_path / "scaling" / "probe.py")
    assert t.id == "scaling/probe" and t.problems() == []
    assert t.examples() == [{"test": "scaling/probe", "params": {"example_param": 3}}]


def test_new_test_command_scaffolds_and_refuses_unknown_types(tmp_path, monkeypatch, capsys):
    import shutil
    from types import SimpleNamespace

    from dagtool.cli import cmd_new_test
    (tmp_path / "checks" / "scaling").mkdir(parents=True)
    shutil.copy(REPO / "checks" / "_template.py", tmp_path / "checks" / "_template.py")
    dag = SimpleNamespace(root=tmp_path)
    assert cmd_new_test(dag, SimpleNamespace(type="scaling", name="probe")) == 0
    assert fw.read_test(tmp_path / "checks" / "scaling" / "probe.py").problems() == []
    assert cmd_new_test(dag, SimpleNamespace(type="scaling", name="probe")) == 1          # exists
    assert cmd_new_test(dag, SimpleNamespace(type="nonsense", name="x")) == 2
