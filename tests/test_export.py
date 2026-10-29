"""The browser's circuit and pattern export lines up with the compiler."""

from __future__ import annotations

from mbqc_verify.compile.export import circuit_json, pattern_json
from mbqc_verify.compile.qiskit_to_mbqc import pattern_stats
from mbqc_verify.hamsim.circuits import IsingChain, trotter_circuit


def _circuit():
    return trotter_circuit(IsingChain.random(2, seed=2), 1.0, 2, order=2)


def test_circuit_columns_never_overlap_on_a_wire():
    c = circuit_json(_circuit().circuit)
    seen = set()
    for op in c["ops"]:
        for w in range(min(op["qubits"]), max(op["qubits"]) + 1):
            assert (w, op["col"]) not in seen
            seen.add((w, op["col"]))
    assert c["gates"] == len(c["ops"]) and c["wires"] == ["q0", "q1"]


def test_unoptimized_pattern_edges_all_come_from_the_construction():
    p = pattern_json(_circuit().circuit, optimize=False)
    ids = {n[0] for n in p["nodes"]}
    assert all(u in ids and v in ids for u, v, _ in p["edges"])
    # every edge is a J edge (-1) or a CZ at a column (>= 0); none are unexplained (-2)
    assert all(col >= -1 for _, _, col in p["edges"])
    # a CZ is drawn vertically between the two vertices' wires, at or after both were made
    pos = {n[0]: (n[1], n[2]) for n in p["nodes"]}
    for u, v, col in p["edges"]:
        if col >= 0:
            assert pos[u][0] != pos[v][0] and col >= max(pos[u][1], pos[v][1])
    assert p["stats"]["N"] == len(p["nodes"]) and p["stats"]["E"] == len(p["edges"])


def test_optimized_pattern_keeps_vertex_positions():
    qc = _circuit().circuit
    a, b = pattern_json(qc, optimize=False), pattern_json(qc, optimize=True)
    pa = {n[0]: n[1:3] for n in a["nodes"]}
    assert all(pa[n[0]] == n[1:3] for n in b["nodes"])
    assert len(b["nodes"]) < len(a["nodes"])
