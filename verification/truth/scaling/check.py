"""
check.py — scaling: does a bilinear cost formula reproduce every MBQC count?

Node params:
    method:   trotter2 | qsvt | gqsp
    optimize: bool     (Pauli measurements removed or not)
    quantity: N | E | M
    claim:    formula (default) | not_bilinear
    coef:     [a, b, c, e]  for value = (a n + b) k + c n + e   (claim: formula)

`formula` passes when the formula matches every training and held-out count
exactly. `not_bilinear` passes when the unique bilinear formula through the
grid's four corner points misses some other grid point, so no bilinear formula
fits the data. A formula that misses a count is refuted on that point.
Grants at most `empirical` on the grid: the counts come from running Graphix.
"""

from __future__ import annotations

from verification.base import Check, CheckResult, register

from .grids import corners, counts, domain_text, grid, interpolate, least_squares, mismatches


@register
class ScalingCheck(Check):
    kind = "scaling"

    def run(self, node, params, ctx):
        method, optimize, q = params["method"], bool(params["optimize"]), params["quantity"]
        data = counts(method, optimize, ctx.quick, ctx.cache)
        train, holdout = grid(method, ctx.quick)
        domain = domain_text(method, ctx.quick)
        ev = {"method": method, "optimize": optimize, "quantity": q,
              "training": [list(p) for p in train], "holdout": [list(p) for p in holdout],
              "counts": [{"n": n, "k": k, q: v[q], "space": v["space"]} for (n, k), v in sorted(data.items())],
              "least_squares_fit": least_squares(data, q, train)}

        if params.get("claim", "formula") == "not_bilinear":
            pts = corners(train)
            interp = interpolate(data, q, pts)
            ev["interpolated_through"] = pts
            ev["interpolated"] = [str(c) for c in interp] if interp else None
            miss = mismatches(interp, data, q) if interp else []
            ev["mismatches"] = miss
            if miss:
                return CheckResult("pass", "empirical", domain,
                                   summary=f"no bilinear formula fits: the one through the 4 corners misses "
                                           f"{len(miss)} of {len(data)} points", evidence=ev)
            return CheckResult("fail", "refuted", domain,
                               summary="a bilinear formula fits every grid point", evidence=ev)

        miss = mismatches(params["coef"], data, q)
        ev["mismatches"] = miss
        if miss:
            m = miss[0]
            return CheckResult("fail", "refuted", f"counterexample at n={m['n']}, k={m['k']}",
                               summary=f"formula misses {len(miss)} of {len(data)} counts "
                                       f"(n={m['n']}, k={m['k']}: count {m['count']}, formula {m['formula']})",
                               evidence=ev)
        return CheckResult("pass", "empirical", domain,
                           summary=f"exact on all {len(train)} training and {len(holdout)} held-out points",
                           evidence=ev)
