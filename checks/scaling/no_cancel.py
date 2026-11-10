"""
scaling/no_cancel — no CZ of the circuit's J/CZ stream cancels an edge, so E = #J + #CZ.

What it checks
    That when Graphix builds the unoptimized pattern gate by gate, no CZ toggles off an edge already in the
    graph. Lean's transfer theorem gives E = #J + #CZ exactly under this condition
    (MBQC.Transfer.compile_edges); the Lean proofs of the E formulas assume it.

How it works
    1. Builds and transpiles the circuit for each (n, k) of the grid, held-out points included.
    2. Replays Graphix's J/CZ stream (instructions_to_jcz): J adds a vertex and an edge along its wire, CZ
       toggles the edge between the two wires' current vertices.
    3. Counts the CZs that removed an edge.

Parameters
    method      trotter2 | qsvt | gqsp

Passes when
    No CZ cancels an edge in any grid circuit.

Fails when
    Some circuit has a cancelling CZ; the first such (n, k) and how many are recorded.

Grants
    empirical on the grid.

Example
    - test: scaling/no_cancel
      params: {method: gqsp}
"""

from __future__ import annotations

from checks._framework import Result
from checks._shared.grids import domain_text, gate_counts, grid

PARAMS = {"method": {"enum": ["trotter2", "qsvt", "gqsp"]}}
REQUIRED = ["method"]


def run(node, params, ctx):
    method = params["method"]
    data = gate_counts(method, ctx.quick, ctx.cache)
    train, holdout = grid(method, ctx.quick)
    ev = {"method": method, "training": [list(p) for p in train], "holdout": [list(p) for p in holdout],
          "counts": [{"n": n, "k": k, "cancels": v["cancels"]} for (n, k), v in sorted(data.items())]}
    bad = [(n, k) for (n, k), v in sorted(data.items()) if v["cancels"]]
    if bad:
        n, k = bad[0]
        return Result("fail", "refuted", f"counterexample at n={n}, k={k}",
                      summary=f"{len(bad)} of {len(data)} circuits have a CZ that cancels an edge "
                              f"(n={n}, k={k}: {data[(n, k)]['cancels']})", evidence=ev)
    return Result("pass", "empirical", domain_text(method, ctx.quick),
                  summary=f"no CZ cancels an edge in any of the {len(data)} circuits", evidence=ev)
