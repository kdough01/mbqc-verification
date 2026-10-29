"""
qiskit_to_mbqc.py — translate a Qiskit circuit into a Graphix MBQC pattern.

Pipeline
--------
    Qiskit QuantumCircuit
      └─ qiskit.transpile(...)          rewrite into a gate set Graphix understands
         └─ to_graphix_circuit(...)      gate-by-gate copy into graphix.transpiler.Circuit
            └─ circuit.transpile()       each gate -> its J(α)/CZ measurement pattern
               └─ optimize_pattern(...)  standardize, shift signals, remove Pauli measurements

Demo: python -m mbqc_verify.compile.qiskit_to_mbqc  (from the repo root)

Tested with qiskit 2.5 and graphix 0.4.1. Plotting also needs matplotlib,
networkx and pylatexenc (pip install "qiskit[visualization]").

Conventions to know
-------------------
* Graphix angles are in units of π (rz(q, 0.25) is a T-like rotation). Qiskit
  uses radians. `to_graphix_circuit` divides by π for you.
* Graphix statevectors are big-endian (qubit 0 is the leftmost tensor factor);
  Qiskit is little-endian. `verify` accounts for this.
* MBQC patterns take |+>^n as their default input state, not |0>^n. If you want
  a |0>^n start, add an H on every qubit at the start of the Qiskit circuit.
* Global phase is dropped (MBQC patterns are only defined up to global phase).
* Mid-circuit measurements, resets and classically controlled gates are not
  supported: strip final measurements with `qc.remove_final_measurements()`.

These are recorded in code as `mbqc_verify.conventions.GRAPHIX` (patterns) and
`mbqc_verify.conventions.QISKIT` (circuits); DAG nodes cite them by name.
"""

from __future__ import annotations

import math

import networkx as nx
import numpy as np
from graphix.transpiler import Circuit as GraphixCircuit
from qiskit import QuantumCircuit, transpile
from qiskit.quantum_info import Statevector

from ..conventions import GRAPHIX as CONVENTIONS  # noqa: F401  (re-exported for checks)
from ..conventions import radians_to_pi_units

# Gates we map one-to-one into Graphix. Everything else gets decomposed into
# these by Qiskit's transpiler first.
BASIS_GATES = [
    "h", "s", "sdg", "t", "tdg", "x", "y", "z", "sx", "sxdg",
    "rx", "ry", "rz", "u",
    "cx", "cz", "cy", "swap", "rzz", "ccx",
]

_ONE_QUBIT = {"h", "s", "sdg", "t", "tdg", "x", "y", "z", "sx", "sxdg"}
_ONE_QUBIT_ROT = {"rx", "ry", "rz"}
_TWO_QUBIT = {"cx": "cnot", "cz": "cz", "cy": "cy", "swap": "swap"}
_SKIP = {"barrier", "delay", "id"}


def to_graphix_circuit(qc: QuantumCircuit, optimization_level: int = 1) -> GraphixCircuit:
    """Rewrite `qc` into Graphix's gate set and return a graphix Circuit.

    Qubit i in Qiskit becomes qubit i in Graphix. Parameterized circuits must be
    bound first (qc.assign_parameters(...)).
    """
    if qc.parameters:
        raise ValueError(f"Bind parameters first; unbound: {sorted(p.name for p in qc.parameters)}")
    if qc.num_clbits:
        qc = qc.remove_final_measurements(inplace=False)

    tqc = transpile(qc, basis_gates=BASIS_GATES, optimization_level=optimization_level)
    g = GraphixCircuit(tqc.num_qubits)

    for inst in tqc.data:
        name = inst.operation.name
        qs = [tqc.find_bit(q).index for q in inst.qubits]
        angles = [radians_to_pi_units(float(p)) for p in inst.operation.params]

        if name in _SKIP:
            continue
        elif name in _ONE_QUBIT:
            getattr(g, name)(qs[0])
        elif name in _ONE_QUBIT_ROT:
            getattr(g, name)(qs[0], angles[0])
        elif name == "u":
            g.u(qs[0], *angles)  # same U(θ, φ, λ) matrix in both libraries
        elif name in _TWO_QUBIT:
            getattr(g, _TWO_QUBIT[name])(qs[0], qs[1])
        elif name == "rzz":
            g.rzz(qs[0], qs[1], angles[0])  # same exp(-iθ/2 Z⊗Z) in both libraries
        elif name == "ccx":
            g.ccx(qs[0], qs[1], qs[2])
        else:
            raise NotImplementedError(f"Unsupported instruction after transpile: {name!r}")
    return g


def optimize_pattern(pattern):
    """Standard measurement-calculus clean-up, done in place and returned.

    1. standardize: rewrite to N* E* M* C* order (prepare, entangle, measure, correct).
    2. shift_signals: move Z-dependencies off measurement angles where possible,
       which reduces how much feedforward the pattern needs.
    3. infer_pauli_measurements: tag XY-plane measurements at 0, π/2, π, 3π/2
       as Pauli X/Y measurements (Graphix won't treat them as Pauli otherwise).
    4. remove_pauli_measurements: Pauli measurements (the Clifford part of the
       circuit) are simulated classically and deleted via local complementation,
       leaving a smaller graph whose remaining measurements are mostly the
       non-Clifford ones.
    5. minimize_space: reorder so few qubits are alive at once (standardization
       alone puts every N and E up front, which maximizes space).
    """
    pattern.standardize()
    pattern.shift_signals()
    pattern.infer_pauli_measurements()
    pattern.remove_pauli_measurements()
    pattern.minimize_space()
    return pattern


def qiskit_to_pattern(qc: QuantumCircuit, optimize: bool = True):
    """Qiskit circuit -> Graphix measurement pattern."""
    pattern = to_graphix_circuit(qc).transpile().pattern
    return optimize_pattern(pattern) if optimize else pattern


def pattern_stats(pattern) -> dict:
    """Quick resource summary of a pattern."""
    cmds = list(pattern)
    kind = lambda c: type(c).__name__
    meas = [c for c in cmds if kind(c) == "M"]
    return {
        "inputs": len(pattern.input_nodes),
        "outputs": len(pattern.output_nodes),
        "total_nodes": sum(kind(c) == "N" for c in cmds) + len(pattern.input_nodes),
        "edges (CZ)": sum(kind(c) == "E" for c in cmds),
        "measurements": len(meas),
        "max_space": pattern.max_space(),
    }


def verify(qc: QuantumCircuit, pattern, seed: int = 0, n_states: int = 3, atol: float = 1e-8) -> float:
    """Check the pattern against the circuit. Returns the worst |<ψ_qiskit|ψ_mbqc>|.

    Both are run on `n_states` random input states (Haar-random over all qubits),
    so a pattern that agrees with the circuit on one special input but not in
    general is caught. Measurement outcomes inside the pattern are sampled at
    random; a correct deterministic pattern gives overlap 1 on every branch.
    Global phase is ignored (patterns don't track it).
    """
    from qiskit.quantum_info import random_statevector

    qc = qc.remove_final_measurements(inplace=False)
    rng = np.random.default_rng(seed)
    worst = 1.0
    for _ in range(n_states):
        psi = random_statevector(2 ** qc.num_qubits, seed=int(rng.integers(2 ** 31)))
        ref = psi.evolve(qc).reverse_qargs().data                  # Graphix is big-endian
        out = pattern.simulate(input_state=psi.reverse_qargs().data, rng=rng, optimized=False)
        worst = min(worst, abs(np.vdot(ref, np.asarray(out.flatten()))))
    if not math.isclose(worst, 1.0, abs_tol=atol):
        raise AssertionError(f"Pattern does not match circuit: |overlap| = {worst:.6f}")
    return worst


# ----------------------------------------------------------------------------
# Plotting
# ----------------------------------------------------------------------------

_NODE_COLORS = {
    "output": "#4C9F70",   # unmeasured output qubits
    "pauli": "#B8BCC6",    # Pauli measurement: no feedforward needed, Clifford part
    "nonpauli": "#E8833A", # non-Pauli angle: the adaptive (T-like) measurements
}


def _measurement_label(m) -> str:
    """Short label for a measurement: 'X', '-Y', 'XY 1.75π', 'YZ 0.25π'."""
    pauli = m.to_pauli_or_none()
    if pauli is not None:
        s = str(pauli)
        return s[1:] if s.startswith("+") else s
    return f"{m.plane.name} {float(m.angle):.3g}π"


def _layered_layout(pattern, graph) -> dict:
    """Place nodes left-to-right in measurement order.

    x = layer from the pattern's partial order (first-measured layer on the left,
    outputs on the right). Within a layer, nodes are sorted by the average height
    of their already-placed neighbors, which keeps edges from crossing much.
    """
    try:
        layers = [sorted(layer) for layer in reversed(pattern.partial_order_layers())]
    except Exception:  # fall back to a generic layout if the order can't be computed
        return nx.spring_layout(graph, seed=0)

    pos: dict = {}
    for x, layer in enumerate(layers):
        def key(n):
            ys = [pos[nb][1] for nb in graph.neighbors(n) if nb in pos]
            return (-(sum(ys) / len(ys)) if ys else 0.0, n)
        layer = sorted(layer, key=key)
        k = len(layer)
        for i, n in enumerate(layer):
            pos[n] = (float(x), (k - 1) / 2 - i)
    return pos


def plot_circuit_and_pattern(
    qc: QuantumCircuit,
    pattern=None,
    optimize: bool = True,
    show_labels: bool = True,
    filename: str | None = None,
    figsize: tuple[float, float] | None = None,
):
    """Plot a Qiskit circuit above the graph of its MBQC pattern.

    Parameters
    ----------
    qc : the original Qiskit circuit.
    pattern : a Graphix pattern to plot. If None, it's built with
        qiskit_to_pattern(qc, optimize=optimize).
    show_labels : write each node's measurement (plane and angle in units of π,
        or the Pauli axis) next to it.
    filename : if given, save the figure there (png, pdf, svg, ...).

    Returns the matplotlib Figure.

    Reading the graph
    -----------------
    * Edges are the CZ entangling operations (the graph state).
    * Square nodes are the circuit's input qubits; green nodes are the
      unmeasured outputs.
    * Grey = Pauli measurement (Clifford, no adaptivity needed); orange =
      non-Pauli angle (the measurements that need feedforward).
    * Columns are measurement layers: everything in one column can be measured
      at the same time once the columns to its left are done.

    For Graphix's own drawing, with flow/correction arrows, use
    pattern.draw(filename=...) instead.
    """
    import matplotlib.pyplot as plt

    if pattern is None:
        pattern = qiskit_to_pattern(qc, optimize=optimize)

    og = pattern.to_opengraph()
    graph = og.graph
    inputs, outputs, meas = set(og.input_nodes), set(og.output_nodes), og.measurements
    pos = _layered_layout(pattern, graph)

    n_cols = int(1 + max((x for x, _ in pos.values()), default=0))
    n_rows = int(1 + max((abs(y) * 2 for _, y in pos.values()), default=0))
    h_circ, h_graph = 0.4 + 0.5 * qc.num_qubits, 1.0 + 0.85 * n_rows
    if figsize is None:
        figsize = (max(9.0, 1.7 * n_cols + 3), h_circ + h_graph + 1)

    fig, (ax_c, ax_g) = plt.subplots(
        2, 1, figsize=figsize, gridspec_kw={"height_ratios": [h_circ, h_graph]},
    )

    # Top: the original circuit
    qc.remove_final_measurements(inplace=False).draw("mpl", ax=ax_c, fold=-1)
    ax_c.set_title("Gate-based circuit", loc="left", fontsize=12)

    # Bottom: the MBQC graph
    def kind(n):
        if n in outputs:
            return "output"
        return "pauli" if meas[n].to_pauli_or_none() is not None else "nonpauli"

    # Edges within one column that skip over a node would be drawn straight
    # through it, so bend those into arcs.
    straight, bent = [], []
    for u, v in graph.edges:
        same_col = pos[u][0] == pos[v][0] and abs(pos[u][1] - pos[v][1]) > 1
        (bent if same_col else straight).append((u, v))
    nx.draw_networkx_edges(graph, pos, edgelist=straight, ax=ax_g, edge_color="#555555", width=1.4)
    if bent:
        nx.draw_networkx_edges(graph, pos, edgelist=bent, ax=ax_g, edge_color="#555555", width=1.4,
                               arrows=True, arrowstyle="-", connectionstyle="arc3,rad=0.45",
                               node_size=520)
    for shape, group in (("s", inputs), ("o", set(graph.nodes) - inputs)):
        nodes = sorted(group)
        nx.draw_networkx_nodes(
            graph, pos, nodelist=nodes, ax=ax_g, node_shape=shape, node_size=520,
            node_color=[_NODE_COLORS[kind(n)] for n in nodes],
            edgecolors="#222222", linewidths=1.2,
        )
    nx.draw_networkx_labels(graph, pos, ax=ax_g, font_size=8)

    if show_labels:
        for n, m in meas.items():
            x, y = pos[n]
            ax_g.annotate(_measurement_label(m), (x, y), xytext=(14, -14),
                          textcoords="offset points", ha="left", va="top", fontsize=8,
                          bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85),
                          zorder=5)

    stats = pattern_stats(pattern)
    ax_g.set_title(
        f"MBQC pattern: {stats['total_nodes']} qubits, {stats['edges (CZ)']} CZ edges, "
        f"{stats['measurements']} measurements, {n_cols - 1} measurement layers",
        loc="left", fontsize=12,
    )
    from matplotlib.lines import Line2D
    legend = [
        Line2D([], [], marker="s", ls="", mfc="white", mec="#222222", ms=10, label="input"),
        Line2D([], [], marker="o", ls="", mfc=_NODE_COLORS["output"], mec="#222222", ms=10, label="output"),
        Line2D([], [], marker="o", ls="", mfc=_NODE_COLORS["pauli"], mec="#222222", ms=10, label="Pauli meas."),
        Line2D([], [], marker="o", ls="", mfc=_NODE_COLORS["nonpauli"], mec="#222222", ms=10, label="non-Pauli meas."),
    ]
    ax_g.legend(handles=legend, loc="upper left", bbox_to_anchor=(1.0, 1.0), frameon=False)
    ax_g.margins(x=0.08, y=0.25)
    ax_g.axis("off")

    fig.tight_layout()
    if filename:
        fig.savefig(filename, dpi=150, bbox_inches="tight")
    return fig


if __name__ == "__main__":
    # Small demo: a 3-qubit circuit with Clifford, T and Trotter-style ZZ terms.
    qc = QuantumCircuit(3)
    qc.h(0)
    qc.cx(0, 1)
    qc.t(1)
    qc.rzz(0.3, 1, 2)
    qc.rx(0.7, 2)
    qc.ccx(0, 1, 2)

    raw = qiskit_to_pattern(qc, optimize=False)
    opt = qiskit_to_pattern(qc, optimize=True)
    print("raw      :", pattern_stats(raw))
    print("optimized:", pattern_stats(opt))
    print("fidelity :", verify(qc, opt))

    plot_circuit_and_pattern(qc, opt, filename="docs/img/mbqc_demo.png")
    print("saved    : docs/img/mbqc_demo.png")