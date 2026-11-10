"""The Lean Hamiltonian-simulation files say the same thing as the DAG nodes.

The gate-count axioms (lean/MBQC/Assumptions/HamSimGates.lean) must state the
coefficients the assumption nodes' scaling checks test, and each Lean result
must state the formula its node's scaling check tests. Otherwise the Lean proof
and the measured evidence would be about different claims.
"""

from __future__ import annotations

import re
from fractions import Fraction
from pathlib import Path

import pytest

from dagtool.model import load_dag

REPO = Path(__file__).resolve().parents[1]
LEAN = REPO / "lean" / "MBQC"
NS = {"trotter2": "Trotter2UnoptGates", "qsvt": "QsvtUnoptGates", "gqsp": "GqspUnoptGates"}


def bilinear(expr: str, k: str) -> list[Fraction]:
    """[a, b, c, e] of a Lean Int expression a*n*k + b*k + c*n + e (in any arrangement of those terms)."""
    import sympy as sp
    n, kk = sp.symbols("n k")
    e = expr.replace("(n : Int)", "n").replace(f"{k}", "k") if k != "n" else expr
    p = sp.Poly(sp.expand(sp.sympify(e, locals={"n": n, "k": kk})), n, kk)
    get = lambda i, j: Fraction(str(p.coeff_monomial(n**i * kk**j)))
    assert all(i <= 1 and j <= 1 for i, j in p.monoms()), expr
    return [get(1, 1), get(0, 1), get(1, 0), get(0, 0)]


def namespace_block(text: str, ns: str) -> str:
    return text.split(f"namespace MBQC.Assumptions.HamSim.{ns}")[1].split(f"end MBQC.Assumptions.HamSim.{ns}")[0]


@pytest.fixture(scope="module")
def dag():
    return load_dag(REPO)


@pytest.mark.parametrize("method", sorted(NS))
def test_gate_count_axioms_match_the_assumption_node(dag, method):
    text = namespace_block((LEAN / "Assumptions" / "HamSimGates.lean").read_text(), NS[method])
    k = re.search(r"axiom count_cnot : ∀ n (\w) : Nat", text).group(1)
    axioms = {m.group(1): bilinear(m.group(2), k)
              for m in re.finditer(r"axiom count_(\w+) :.*?\n\s*\(countKind \.\w+ \(circuit n \w\) : Int\) = (.+)", text)}
    node = dag.nodes[f"assume.hamsim.{method}_unopt_gates"]
    tested = {c.params["gate"]: [Fraction(str(x)) for x in c.params["coef"]]
              for c in node.checks if c.test == "scaling/gate_counts"}
    assert axioms == tested and len(axioms) == 10
    # the width the Lean results compile on is the width the node's check measures
    width = next(c.params["coef"] for c in node.checks if c.test == "scaling/circuit_width")
    lean_width = re.search(r"axiom no_cancel : .*?NoCancel \((.+?)\) \(gatesToJcz", text).group(1)
    assert bilinear(lean_width, k) == [Fraction(x) for x in width]
    assert any(c.test == "scaling/no_cancel" for c in node.checks)


@pytest.mark.parametrize("method", sorted(NS))
@pytest.mark.parametrize("q,word", [("N", "vertices"), ("M", "measurements"), ("E", "edges")])
def test_unopt_theorem_states_the_scaling_formula(dag, method, q, word):
    node = dag.nodes[f"hamsim.B.{method}.{q}.unopt"]
    assert node.lean_decl == f"MBQC.Results.HamSim.{method}_{word}_unopt"
    text = (LEAN / "Results" / "HamSim" / "Unopt.lean").read_text()
    m = re.search(rf"theorem {method}_{word}_unopt \(n (\w) : Nat\).*?\n.*?: Int\) = (.+?) := by", text)
    assert m, f"{node.lean_decl} not found"
    coef = next(c.params["coef"] for c in node.checks if c.test == "scaling/bilinear_formula")
    assert bilinear(m.group(2), m.group(1)) == [Fraction(str(x)) for x in coef]
    assert f"{NS[method]}.circuit" in m.group(0) and {"lean", "vocabulary", "nonvacuity"} <= {c.kind for c in node.checks}


OPT = [("trotter2", "N", "Trotter2OptN"), ("trotter2", "M", "Trotter2OptM"), ("gqsp", "N", "GqspOptN"),
       ("gqsp", "M", "GqspOptM"), ("qsvt", "M", "QsvtOptM")]


@pytest.mark.parametrize("method,q,ns", OPT)
def test_opt_corners_and_theorem_match_the_formula(dag, method, q, ns):
    from mbqc_verify.hamsim.analysis import evaluate
    node = dag.nodes[f"hamsim.B.{method}.{q}.opt"]
    coef = next(c.params["coef"] for c in node.checks if c.test == "scaling/bilinear_formula")
    block = (LEAN / "Assumptions" / "HamSimOpt.lean").read_text().split(f"namespace MBQC.Assumptions.HamSim.{ns}")[1]
    block = block.split(f"end MBQC.Assumptions.HamSim.{ns}")[0]
    corners = {(int(a), int(b)): int(v) for a, b, v in re.findall(r"axiom at_(\d+)_(\d+) : count \d+ \d+ = (-?\d+)", block)}
    assert len(corners) == 4 and all(evaluate(coef, n, k) == v for (n, k), v in corners.items())
    word = {"N": "vertices", "M": "measurements"}[q]
    text = (LEAN / "Results" / "HamSim" / "Opt.lean").read_text()
    m = re.search(rf"theorem {method}_{word}_opt \(n (\w) : Nat\).*?\n\s*{ns}\.count n \w = (.+?) := by", text)
    assert m and node.lean_decl == f"MBQC.Results.HamSim.{method}_{word}_opt"
    assert bilinear(m.group(2), m.group(1)) == [Fraction(str(x)) for x in coef]
    assumption = dag.nodes[f"assume.hamsim.{method}_opt_{q}"]
    assert assumption.lean_names == [f"MBQC.Assumptions.HamSim.{ns}"]
    assert next(c.params["coef"] for c in assumption.checks if c.test == "scaling/bilinear_formula") == coef


def test_compiler_convention_names_every_registered_compiler():
    from mbqc_verify.compilers import COMPILERS
    from mbqc_verify.conventions import Compiler
    assert {c.value for c in Compiler} == set(COMPILERS)


def test_compiler_variants_point_at_their_graphix_claim(dag):
    variants = [n for n in dag.nodes.values() if n.id.endswith(".cabaliser")]
    assert len(variants) == 9
    for n in variants:
        assert n.conventions.compiler.value == "cabaliser"
        base = [e.src for e in dag.parents(n.id, kinds=("variant_of",))]
        assert base == [n.id.replace(".cabaliser", ".opt")]
        assert all(c.params.get("compiler") == "cabaliser" for c in n.checks if c.kind == "scaling")
        assert "experiments/compilers/results/cabaliser.json" in n.raw["code"]


def test_compiler_of_reads_the_older_optimize_spelling():
    from checks._shared.grids import compiler_of
    assert compiler_of({"optimize": True}) == "graphix_opt" and compiler_of({}) == "graphix"
    assert compiler_of({"compiler": "cabaliser"}) == "cabaliser"
    with pytest.raises(ValueError):
        compiler_of({"compiler": "graphix", "optimize": True})


def test_schema_lists_the_same_compilers():
    import json
    from mbqc_verify.conventions import Compiler
    schema = json.loads((REPO / "dag" / "schema" / "node.schema.json").read_text())
    assert set(schema["properties"]["conventions"]["properties"]["compiler"]["enum"]) == {c.value for c in Compiler}
