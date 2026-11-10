"""
legacy.py — translate a check written the old way, {kind, params} with a switch inside params, into a test.

Nodes name tests directly (`test: scaling/bilinear_formula`). Proposals from the Quantum Genesis dashboard may
still send {"kind": ..., "params": ...}; suites.py translates those here, so both forms are accepted at that
boundary and only the test form is ever written to a node.

    to_test("scaling", {"claim": "not_bilinear", "method": "qsvt", "optimize": True, "quantity": "E"})
      -> ("scaling/not_bilinear", {"method": "qsvt", "compiler": "graphix_opt", "quantity": "E"})
"""

from __future__ import annotations

SIMPLE = {   # types with one test: the params carry over unchanged (minus the keys listed)
    "lean_proof": ("lean_proof/independent_proof", ()),
    "vocabulary": ("vocabulary/vetted_constants", ()),
    "nonvacuity": ("nonvacuity/witness", ()),
    "equivalence": ("equivalence/iff_proof", ()),
    "literature": ("literature/source_record", ()),
    "mutation": ("mutation/scaling_coefficients", ("target",)),
    "finite": ("finite/exhaustive", ()),
    "symbolic": ("symbolic/slide_positivity", ("certificate",)),
    "reproduction": ("reproduction/recorded_value", ()),
}
TOOLS = {"surface_code.memory": "surface_code_memory", "surface_code.fit": "surface_code_fit",
         "gridsynth.rz": "gridsynth_rz", "qualtran.cost": "qualtran_cost",
         "azure_re.logical_counts": "azure_re_logical_counts", "azure_re.qsharp": "azure_re_qsharp"}


def _compiler(p: dict) -> str:
    comp = p.pop("compiler", None)
    opt = p.pop("optimize", None)
    return comp or ("graphix_opt" if opt else "graphix")


def to_test(kind: str, params: dict | None) -> tuple[str, dict]:
    """(test id, params for that test) for a check written as {kind, params}."""
    p = dict(params or {})
    if kind in SIMPLE:
        test, drop = SIMPLE[kind]
        for k in drop:
            p.pop(k, None)
        return test, p
    if kind == "lean":
        return ("lean/disproof" if p.pop("refutes", False) else "lean/proof"), p
    if kind == "differential":
        return ("differential/lean_gate_streams" if p.pop("gates", False) else "differential/lean_counts"), p
    if kind == "numerical":
        which = p.pop("which")
        return {"accuracy": "numerical/hamsim_accuracy", "trotter_circuit": "numerical/trotter_circuit",
                "equal_accuracy": "numerical/equal_accuracy"}[which], p
    if kind == "translation":
        if p.get("compiler") not in (None, "graphix", "graphix_opt"):
            return "translation/recorded_compiler", p
        p.pop("compiler", None)
        return "translation/graphix_pattern", p
    if kind == "refuter":
        source = p.pop("source", "formula")
        if source == "hypothesis":
            return "refuter/hypothesis", p
        if source == "counts":
            return "refuter/qsvt_exceeds_gqsp_counts", {"quantity": p["quantity"], "compiler": _compiler(p)}
        return "refuter/qsvt_exceeds_gqsp_formulas", p
    if kind == "tool":
        return "tool/" + TOOLS[p.pop("tool")], p
    if kind == "scaling":
        claim = p.pop("claim", "formula")
        q = str(p.get("quantity", ""))
        if claim == "no_cancel":
            return "scaling/no_cancel", {"method": p["method"]}
        if q.startswith("gate:"):
            return "scaling/gate_counts", {"method": p["method"], "gate": q.split(":", 1)[1], "coef": p["coef"]}
        if q == "width":
            return "scaling/circuit_width", {"method": p["method"], "coef": p["coef"]}
        out = {"method": p["method"], "compiler": _compiler(p), "quantity": q}
        if claim == "not_bilinear":
            return "scaling/not_bilinear", out
        return "scaling/bilinear_formula", out | {"coef": p["coef"]}
    raise ValueError(f"unknown check kind {kind!r}")


# The main test of each type: what a check written as just {kind: TYPE} means (used for synthetic nodes in tests).
DEFAULT_TEST = {
    "lean": "lean/proof", "lean_proof": "lean_proof/independent_proof", "vocabulary": "vocabulary/vetted_constants",
    "nonvacuity": "nonvacuity/witness", "equivalence": "equivalence/iff_proof", "differential": "differential/lean_counts",
    "mutation": "mutation/scaling_coefficients", "finite": "finite/exhaustive", "symbolic": "symbolic/slide_positivity",
    "translation": "translation/graphix_pattern", "numerical": "numerical/hamsim_accuracy",
    "scaling": "scaling/bilinear_formula", "refuter": "refuter/qsvt_exceeds_gqsp_formulas",
    "literature": "literature/source_record", "reproduction": "reproduction/recorded_value", "tool": "tool/qualtran_cost",
}
