"""
compilers — one interface for every circuit-to-MBQC compiler the verifier compares.

A resource formula is a claim about one compiler: Graphix's gate-by-gate
construction gives one count, Graphix after Pauli-measurement removal another,
Cabaliser a third. Each compiler here maps a Qiskit circuit to the counts the
DAG talks about:

    N  vertices of the graph state (qubits the pattern ever uses)
    E  edges of the graph state (CZ entanglers)
    M  measured vertices
    space (optional) peak number of qubits alive at once

and names the environment it runs in. Compilers that need their own pinned
environment (Cabaliser builds from C and Rust with RRE) are run there by
experiments/compilers/run.py, which records the counts in
experiments/compilers/results/; the verifier's checks read those records, so a
check's evidence names the record it came from.

Adding a compiler (for example another thrust's optimizer):
  1. subclass Compiler here: set `name`, `label` and `env`, implement `counts`, decorate with @register;
  2. add `name` to the `compiler` convention (mbqc_verify/conventions.py, Compiler) and to the schema's
     conventions.compiler enum (dag/schema/node.schema.json); tests/test_hamsim_lean.py keeps the three in step;
  3. if it runs outside the main environment, record its counts with
     `python experiments/compilers/run.py --compiler <name>` (and its translation runs, if it can be simulated);
  4. add variant nodes `hamsim.B.<method>.<N|M|E>.<name>` with a `variant_of` edge to the Graphix claim they
     compare with, conventions `compiler: <name>`, and a scaling check with `compiler: <name>`
     (dag/nodes/hamsim/B/compilers/ has the Cabaliser ones). A formula that also holds for the new compiler
     passes; one that does not shows as "Does not pass scaling tests" on that variant only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from qiskit import QuantumCircuit

COMPILERS: dict[str, "Compiler"] = {}


@dataclass
class Counts:
    N: int
    E: int
    M: int
    space: int | None = None
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"N": self.N, "E": self.E, "M": self.M, "space": self.space} | self.extra


class Compiler:
    name = ""          # the value of the `compiler` convention and of scaling checks' `compiler` param
    label = ""         # how sites and reports name it
    env = "main"       # "main": runs in the verifier's environment; otherwise the experiments env that runs it
    description = ""

    def counts(self, qc: QuantumCircuit) -> Counts:
        raise NotImplementedError


def register(cls):
    COMPILERS[cls.name] = cls()
    return cls


def get(name: str) -> Compiler:
    if name not in COMPILERS:
        raise KeyError(f"unknown compiler {name!r}; known: {', '.join(sorted(COMPILERS))}")
    return COMPILERS[name]


@register
class GraphixUnoptimized(Compiler):
    name = "graphix"
    label = "Graphix unoptimized"
    description = ("Graphix 0.4.1, gate by gate: Qiskit transpile (level 1) to Graphix's gate set, each gate's J/CZ "
                   "decomposition, the J-∧z pattern construction. No pattern optimization.")

    def counts(self, qc):
        from .graphix import pattern_stats, qiskit_to_pattern
        s = pattern_stats(qiskit_to_pattern(qc, optimize=False))
        return Counts(s["total_nodes"], s["edges (CZ)"], s["measurements"], s["max_space"])


@register
class GraphixOptimized(Compiler):
    name = "graphix_opt"
    label = "Graphix optimized"
    description = ("Graphix 0.4.1 with its own pattern optimizations: standardize, then remove Pauli measurements "
                   "(graphix.optimize_pattern).")

    def counts(self, qc):
        from .graphix import pattern_stats, qiskit_to_pattern
        s = pattern_stats(qiskit_to_pattern(qc, optimize=True))
        return Counts(s["total_nodes"], s["edges (CZ)"], s["measurements"], s["max_space"])


CABALISER_BASIS = ["h", "s", "sdg", "x", "y", "z", "cx", "cz", "rz"]


@register
class Cabaliser(Compiler):
    name = "cabaliser"
    label = "Cabaliser"
    env = "rre"
    description = ("Cabaliser (Rigetti RRE's graph-state compiler, pinned in tools/rre/environment.sh): the "
                   "circuit, transpiled by Qiskit (level 1) to Clifford + Rz, is compiled to a graph state in one "
                   "widget. Each non-Clifford Rz becomes a measured vertex; Clifford gates are absorbed into the graph "
                   "and a local-Clifford frame.")

    def counts(self, qc):
        from .cabaliser import compile_counts
        return compile_counts(qc)
