"""
refuter/qsvt_exceeds_gqsp_formulas — search the two methods' cost formulas for a case where QSVT is not costlier.

What it checks
    The slide's conclusion restated with our formulas: for all n ≥ 2 and degrees D ≥ d (QSVT's D odd), QSVT's
    count (N, E or M) exceeds GQSP's. A single case where it does not refutes the claim.

How it works
    1. Reads the scaling formula (scaling/bilinear_formula coefficients) of the two Layer B nodes named.
    2. Evaluates both exactly for n in [2, n_max], d in [1, k_max] and odd D in [d, k_max], in order.
    3. Stops at the first case where QSVT ≤ GQSP.

Parameters
    quantity    N | E | M
    qsvt        the node id of QSVT's formula, e.g. hamsim.B.qsvt.N.unopt
    gqsp        the node id of GQSP's formula
    n_max       largest n searched (default 50)
    k_max       largest degree searched (default 41)

Passes when
    No counterexample in the searched range; the evidence says how many cases were searched.

Fails when
    A counterexample is found (refuted), with both counts.

Grants
    empirical on the searched range, or refuted.

Example
    - test: refuter/qsvt_exceeds_gqsp_formulas
      params: {quantity: N, qsvt: hamsim.B.qsvt.N.unopt, gqsp: hamsim.B.gqsp.N.unopt, n_max: 50, k_max: 41}
"""

from __future__ import annotations

from fractions import Fraction

from checks._framework import Result
from mbqc_verify.hamsim.analysis import evaluate

from ._d_ge_g import counterexample

PARAMS = {"quantity": {"enum": ["N", "E", "M"]}, "qsvt": {"type": "string"}, "gqsp": {"type": "string"},
          "n_max": {"type": "integer", "minimum": 2}, "k_max": {"type": "integer", "minimum": 3}}
REQUIRED = ["quantity", "qsvt", "gqsp"]


def _coef(dag, node_id):
    spec = next(c for c in dag.nodes[node_id].checks if c.test == "scaling/bilinear_formula")
    return [Fraction(str(c)) for c in spec.params["coef"]]


def run(node, params, ctx):
    q = params["quantity"]
    fq, fg = _coef(ctx.dag, params["qsvt"]), _coef(ctx.dag, params["gqsp"])
    n_max, k_max = int(params.get("n_max", 50)), int(params.get("k_max", 41))
    domain = f"n in [2, {n_max}], d in [1, {k_max}], odd D in [d, {k_max}]"
    searched = 0
    for n in range(2, n_max + 1):
        for d in range(1, k_max + 1):
            for D in range(d if d % 2 else d + 1, k_max + 1, 2):
                searched += 1
                vq, vg = evaluate(fq, n, D), evaluate(fg, n, d)
                if not vq > vg:
                    return counterexample(q, n, D, d, vq, vg, searched)
    return Result("pass", "empirical", domain, summary=f"no counterexample in {searched} cases",
                  evidence={"searched": searched})
