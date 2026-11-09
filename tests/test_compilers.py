"""The compiler interface: Graphix live, Cabaliser through its recorded counts."""

from __future__ import annotations

import json
import math

import numpy as np
import pytest
from qiskit import QuantumCircuit

from mbqc_verify.compile.cabaliser_adapter import clifford_rz_ops
from mbqc_verify.compile.compilers import COMPILERS, get
from mbqc_verify.hamsim.analysis import count, generic_circuit
from verification.truth.scaling import grids


def test_graphix_compilers_give_the_scaling_counts():
    qc = generic_circuit("trotter2", 2, 1, np.random.default_rng(2001)).circuit
    for name, opt in (("graphix", False), ("graphix_opt", True)):
        c = get(name).counts(qc)
        assert {"N": c.N, "E": c.E, "M": c.M, "space": c.space} == count("trotter2", 2, 1, opt)
    assert {"graphix", "graphix_opt", "cabaliser"} <= set(COMPILERS) and get("cabaliser").env == "rre"


def test_clifford_rotations_are_not_passed_to_cabaliser_as_rotations():
    qc = QuantumCircuit(2)
    qc.rz(math.pi / 2, 0)
    qc.rz(math.pi, 1)
    qc.rz(-math.pi / 2, 0)
    qc.cx(0, 1)
    qc.rz(0.3, 1)
    width, ops = clifford_rz_ops(qc)
    assert width == 2
    assert [o for o in ops if o[0] == "rz"] == [["rz", [1], pytest.approx(0.3)]]
    assert {o[0] for o in ops} <= {"h", "s", "sdg", "x", "y", "z", "cx", "cz", "rz"}


def test_recorded_counts_cover_the_grid(tmp_path, monkeypatch):
    monkeypatch.setattr(grids, "RECORDS", tmp_path)
    with pytest.raises(FileNotFoundError, match="experiments/compilers/run.py"):
        grids.recorded_counts("cabaliser", "trotter2", False, {})
    train, hold = grids.GRIDS["trotter2"]
    rows = {f"{n},{k}": {"N": n * k, "E": 0, "M": 0} for n, k in train + hold}
    (tmp_path / "cabaliser.json").write_text(json.dumps({"counts": {"trotter2": rows}}))
    data = grids.recorded_counts("cabaliser", "trotter2", False, {})
    assert data[(3, 2)]["N"] == 6 and len(data) == len(train + hold)
    del rows["7,6"]
    (tmp_path / "cabaliser.json").write_text(json.dumps({"counts": {"trotter2": rows}}))
    with pytest.raises(ValueError, match="no trotter2 count"):
        grids.recorded_counts("cabaliser", "trotter2", False, {})


def test_the_committed_cabaliser_record_matches_the_grids():
    rec = json.loads(grids.record_path("cabaliser").read_text())
    for method, (train, hold) in grids.GRIDS.items():
        assert {tuple(map(int, k.split(","))) for k in rec["counts"][method]} == set(train + hold)
    assert rec["translation"] and all(r["worst_fidelity"] > 1 - 1e-9 for r in rec["translation"])
