"""
refuter/qsvt_exceeds_gqsp_counts — search the compiled counts for a case where QSVT is not costlier than GQSP.

What it checks
    The same claim as refuter/qsvt_exceeds_gqsp_formulas (for n ≥ 2 and D ≥ d, QSVT costs more), for a count
    with no closed form (such as the edges of the Graphix-optimized patterns): it compares compiled counts
    directly instead of formulas.

How it works
    1. Compiles both methods on their scaling grids with the chosen compiler (checks/_shared/grids.py).
    2. Pairs every QSVT point (n, D) with every GQSP point (n, d) with the same n and d ≤ D.
    3. Stops at the first pair where QSVT ≤ GQSP.

Parameters
    quantity    N | E | M
    compiler    graphix | graphix_opt | cabaliser (default graphix)

Passes when
    No grid pair is a counterexample.

Fails when
    Some pair is (refuted), with both counts.

Grants
    empirical on the grid pairs, or refuted.

Example
    - test: refuter/qsvt_exceeds_gqsp_counts
      params: {quantity: E, compiler: graphix_opt}
"""

from __future__ import annotations

from checks._framework import Result
from checks._shared.grids import compiler_counts

from ._d_ge_g import counterexample

PARAMS = {"quantity": {"enum": ["N", "E", "M"]}, "compiler": {"enum": ["graphix", "graphix_opt", "cabaliser"]}}
REQUIRED = ["quantity"]


def run(node, params, ctx):
    q, compiler = params["quantity"], params.get("compiler", "graphix")
    cq = compiler_counts(compiler, "qsvt", ctx.quick, ctx.cache)
    cg = compiler_counts(compiler, "gqsp", ctx.quick, ctx.cache)
    searched = 0
    for (nq, D), rq in sorted(cq.items()):
        for (ng, d), rg in sorted(cg.items()):
            if nq != ng or D < d:
                continue
            searched += 1
            if not rq[q] > rg[q]:
                return counterexample(q, nq, D, d, rq[q], rg[q], searched)
    return Result("pass", "empirical", "compiled counts on the Layer B grids",
                  summary=f"no counterexample in {searched} grid pairs", evidence={"searched": searched})
