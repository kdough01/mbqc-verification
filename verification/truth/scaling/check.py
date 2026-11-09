"""
check.py — scaling: does a bilinear cost formula reproduce every MBQC count?

Node params:
    method:   trotter2 | qsvt | gqsp
    compiler: graphix | graphix_opt | cabaliser | ...   (mbqc_verify.compile.compilers; default from optimize)
    optimize: bool     (Graphix only: Pauli measurements removed or not; same as compiler graphix_opt)
    quantity: N | E | M         MBQC counts of the pattern
            | gate:<kind>       how many gates of a kind (cnot, cz, rzz, ccx, h, x, rx, ry, rz, u)
                                the transpiled circuit has, as Graphix instructions (optimize is ignored)
            | width             the circuit's qubit count
    claim:    formula (default) | not_bilinear | no_cancel
    coef:     [a, b, c, e]  for value = (a n + b) k + c n + e   (claim: formula)

`no_cancel` passes when no CZ of any grid circuit's J/CZ stream toggles an edge
off, so the unoptimized pattern has exactly #J + #CZ edges.

`formula` passes when the formula matches every training and held-out count
exactly. `not_bilinear` passes when the unique bilinear formula through the
grid's four corner points misses some other grid point, so no bilinear formula
fits the data. A formula that misses a count is refuted on that point.
Grants at most `empirical` on the grid: the counts come from running the compiler.
Graphix runs here; a compiler that needs its own environment (Cabaliser) is read
from its record in experiments/compilers/results/, which experiments/compilers/run.py
writes (list the record in the node's `code:` so the evidence goes stale with it).
"""

from __future__ import annotations

from verification.base import Check, CheckResult, register

from .grids import compiler_counts, corners, domain_text, gate_counts, grid, interpolate, least_squares, mismatches


def compiler_of(params: dict) -> str:
    """The compiler a scaling spec is about; `optimize` is the older spelling of graphix vs graphix_opt."""
    comp = params.get("compiler")
    if comp is None:
        return "graphix_opt" if params.get("optimize") else "graphix"
    if "optimize" in params and comp in ("graphix", "graphix_opt") and bool(params["optimize"]) != (comp == "graphix_opt"):
        raise ValueError(f"optimize: {params['optimize']} contradicts compiler: {comp}")
    return comp


@register
class ScalingCheck(Check):
    kind = "scaling"

    def run(self, node, params, ctx):
        method = params["method"]
        claim, q = params.get("claim", "formula"), params.get("quantity", "cancels")
        circuit_level = claim == "no_cancel" or q.startswith("gate:") or q == "width"
        compiler = compiler_of(params)
        optimize = compiler == "graphix_opt"
        data = gate_counts(method, ctx.quick, ctx.cache) if circuit_level else compiler_counts(compiler, method, ctx.quick, ctx.cache)
        train, holdout = grid(method, ctx.quick)
        domain = domain_text(method, ctx.quick)
        if claim == "no_cancel":
            ev = {"method": method, "training": [list(p) for p in train], "holdout": [list(p) for p in holdout],
                  "counts": [{"n": n, "k": k, "cancels": v["cancels"]} for (n, k), v in sorted(data.items())]}
            bad = [(n, k) for (n, k), v in sorted(data.items()) if v["cancels"]]
            if bad:
                n, k = bad[0]
                return CheckResult("fail", "refuted", f"counterexample at n={n}, k={k}",
                                   summary=f"{len(bad)} of {len(data)} circuits have a CZ that cancels an edge "
                                           f"(n={n}, k={k}: {data[(n, k)]['cancels']})", evidence=ev)
            return CheckResult("pass", "empirical", domain,
                               summary=f"no CZ cancels an edge in any of the {len(data)} circuits", evidence=ev)
        ev = {"method": method, "compiler": compiler, "optimize": optimize, "quantity": q,
              "training": [list(p) for p in train], "holdout": [list(p) for p in holdout],
              "counts": [{"n": n, "k": k, q: v[q], "space": v.get("space")} for (n, k), v in sorted(data.items())],
              "least_squares_fit": least_squares(data, q, train)}

        if claim == "not_bilinear":
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
