"""
export.py — circuits and MBQC patterns as JSON, for the theorem browser.

circuit_json(): the Qiskit circuit as built (before transpiling), one entry per
    gate with its drawing column, controls and parameters.
pattern_json(): the Graphix pattern's graph. Every vertex keeps the circuit wire
    it was created on and a column, from the J-∧z construction Graphix uses: J on
    a wire adds the next vertex along that wire, and each CZ is drawn as a vertical
    line at the column where it happens. Pauli-measurement removal keeps vertex
    ids, so the optimized pattern is drawn on the same coordinates; edges it
    creates are marked so they can be drawn differently.
"""

from __future__ import annotations

import math

from graphix.transpiler import instructions_to_jcz

from .qiskit_to_mbqc import optimize_pattern, pattern_stats, to_graphix_circuit


def _fmt_param(p) -> str:
    try:
        x = float(p)
    except (TypeError, ValueError):
        return str(p)
    return f"{x / math.pi:.3g}π"


def wire_names(num_qubits: int, layout=None) -> list[str]:
    """q0.. for data qubits, a0.. for ancillas, then named extras (sig, lcu)."""
    if layout is None:
        return [f"q{i}" for i in range(num_qubits)]
    names = [f"q{i}" for i in range(layout.n)] + [f"a{k}" for k in range(layout.m)] + list(layout.extra)
    return names + [f"x{i}" for i in range(len(names), num_qubits)]


def circuit_json(qc, layout=None, postselect=None) -> dict:
    """Gates of `qc` with drawing columns (as-soon-as-possible over each gate's wire span)."""
    nq = qc.num_qubits
    free = [0] * nq                 # first free column on each wire
    ops = []
    for inst in qc.data:
        op = inst.operation
        if op.name in ("barrier", "delay", "id"):
            continue
        qs = [qc.find_bit(q).index for q in inst.qubits]
        lo, hi = min(qs), max(qs)
        col = max(free[lo: hi + 1])
        for w in range(lo, hi + 1):
            free[w] = col + 1
        n_ctrl = getattr(op, "num_ctrl_qubits", 0) or 0
        entry = {"name": op.name, "qubits": qs, "col": col}
        if n_ctrl:
            state = int(getattr(op, "ctrl_state", (1 << n_ctrl) - 1))
            entry["controls"] = qs[:n_ctrl]
            entry["ctrl_state"] = [(state >> i) & 1 for i in range(n_ctrl)]
            entry["targets"] = qs[n_ctrl:]
            entry["base"] = op.base_gate.name
        params = [_fmt_param(p) for p in op.params] if op.name != "unitary" else []
        if params:
            entry["params"] = params
        ops.append(entry)
    return {
        "wires": wire_names(nq, layout),
        "ops": ops,
        "columns": max(free) if free else 0,
        "gates": len(ops),
        "depth": qc.depth(),
        "postselect": {str(q): b for q, b in (postselect or {}).items()},
    }


def _measurement(m) -> tuple[str, str]:
    """(kind, label): kind is 'pauli' or 'nonpauli'; label like 'X', '-Y' or 'XY 1.75π'."""
    pauli = m.to_pauli_or_none() if hasattr(m, "to_pauli_or_none") else m
    if pauli is not None and not hasattr(pauli, "plane"):
        s = str(pauli)
        return "pauli", s[1:] if s.startswith("+") else s
    return "nonpauli", f"{m.plane.name} {float(m.angle):.3g}π"


def _coordinates(gc):
    """Vertex positions and CZ times from the J-∧z stream, matching Graphix's vertex ids.

    Returns ({vertex: (wire, column)}, {(u, v): column}, {(u, v)}): where each vertex is
    created, the column of each CZ edge (drawn vertically between the two wires), and the
    J edges (consecutive vertices on one wire). Columns are as-soon-as-possible, and a
    CZ line never crosses a vertex on a wire between its two ends.
    """
    current = list(range(gc.width))
    dot = [0] * gc.width            # column of the newest vertex on each wire
    busy = [-1] * gc.width          # last column a CZ line used on each wire
    coords = {q: (q, 0) for q in range(gc.width)}
    cz: dict[tuple[int, int], int] = {}
    j_edges: set[tuple[int, int]] = set()
    nxt = gc.width
    for ins in instructions_to_jcz(gc.instruction):
        kind = ins.kind.name
        if kind == "J":
            q = ins.target
            dot[q] = max(dot[q], busy[q]) + 1
            coords[nxt] = (q, dot[q])
            j_edges.add((current[q], nxt))
            current[q] = nxt
            nxt += 1
        elif kind == "CZ":
            a, b = ins.targets
            lo, hi = min(a, b), max(a, b)
            t = max(dot[a], dot[b], *(busy[w] + 1 for w in range(lo, hi + 1)),
                    *(dot[w] + 1 for w in range(lo + 1, hi)))
            for w in range(lo, hi + 1):
                busy[w] = t
            e = (min(current[a], current[b]), max(current[a], current[b]))
            if e in cz:                 # two CZs on the same pair cancel
                del cz[e]
            else:
                cz[e] = t
    return coords, cz, j_edges


def pattern_json(qc, optimize: bool) -> dict:
    """The pattern's graph with wire/time coordinates and measurement labels."""
    gc = to_graphix_circuit(qc)
    coords, cz, j_edges = _coordinates(gc)
    pattern = gc.transpile().pattern
    if optimize:
        pattern = optimize_pattern(pattern)
    og = pattern.to_opengraph()
    inputs, outputs = set(og.input_nodes), set(og.output_nodes)
    nodes = []
    for v in sorted(og.graph.nodes):
        wire, t = coords.get(v, (-1, 0))
        if v in outputs:
            kind, label = "output", "output"
        else:
            kind, label = _measurement(og.measurements[v])
        nodes.append([v, wire, t, kind, label, int(v in inputs)])
    edges = []
    for u, v in sorted((min(u, v), max(u, v)) for u, v in og.graph.edges):
        # col >= 0: a CZ drawn at that column; -1: a J edge along the wire; -2: an edge
        # that was not in the J-∧z construction (made by removing Pauli measurements)
        edges.append([u, v, cz.get((u, v), -1 if (u, v) in j_edges else -2)])
    stats = pattern_stats(pattern)
    return {
        "nodes": nodes,              # [id, wire, column, kind, label, is_input]
        "edges": edges,              # [u, v, column | -1 (J) | -2 (new)]
        "times": max([t for _, t in coords.values()] + list(cz.values()) + [0]),
        "stats": {"N": stats["total_nodes"], "E": stats["edges (CZ)"], "M": stats["measurements"],
                  "space": stats["max_space"]},
    }
