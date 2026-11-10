"""
scaling/not_bilinear — no bilinear formula fits a count: it is not of the form (a n + b) k + c n + e.

What it checks
    That a count of the compiled pattern has no exact bilinear formula in n and k on the method's grid. This
    is the claim for counts that depend on more than how many gates or rotations there are (for example the
    edges of a Graphix-optimized pattern).

How it works
    1. Counts every point of the method's grid, as scaling/bilinear_formula does.
    2. A bilinear formula has four coefficients, so the four corners of the training grid determine the only
       candidate. Solves for it exactly.
    3. Evaluates that candidate at every other point of the grid.

Parameters
    method      trotter2 | qsvt | gqsp
    compiler    graphix | graphix_opt | cabaliser (default graphix)
    quantity    N | E | M

Passes when
    The formula through the four corners misses at least one other grid point, so no bilinear formula fits.

Fails when
    The corner formula fits every point: the count is bilinear on the grid after all.

Grants
    empirical on the grid.

Example
    - test: scaling/not_bilinear
      params: {method: qsvt, compiler: graphix_opt, quantity: E}
"""

from __future__ import annotations

from checks._framework import Result
from checks._shared.grids import compiler_counts, corners, domain_text, grid, interpolate, mismatches

from ._compare import evidence

PARAMS = {
    "method": {"enum": ["trotter2", "qsvt", "gqsp"]},
    "compiler": {"enum": ["graphix", "graphix_opt", "cabaliser"]},
    "quantity": {"enum": ["N", "E", "M"]},
}
REQUIRED = ["method", "quantity"]


def run(node, params, ctx):
    method, q, compiler = params["method"], params["quantity"], params.get("compiler", "graphix")
    data = compiler_counts(compiler, method, ctx.quick, ctx.cache)
    ev = evidence(method, q, data, ctx.quick, compiler=compiler, optimize=compiler == "graphix_opt")
    train, _ = grid(method, ctx.quick)
    pts = corners(train)
    interp = interpolate(data, q, pts)
    ev["interpolated_through"] = pts
    ev["interpolated"] = [str(c) for c in interp] if interp else None
    miss = mismatches(interp, data, q) if interp else []
    ev["mismatches"] = miss
    if miss:
        return Result("pass", "empirical", domain_text(method, ctx.quick),
                      summary=f"no bilinear formula fits: the one through the 4 corners misses {len(miss)} of "
                              f"{len(data)} points", evidence=ev)
    return Result("fail", "refuted", domain_text(method, ctx.quick),
                  summary="a bilinear formula fits every grid point", evidence=ev)
