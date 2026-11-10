"""
differential/lean_counts — Lean's model of the J-∧z construction gives Graphix's N, E and M.

What it checks
    That Lean's computable definition of how Graphix builds a pattern from a J/CZ stream (compileJcz,
    lean/MBQC/Defs/JCZ.lean) produces the same vertex, edge and measurement counts as Graphix itself. Two
    independent implementations agreeing is strong evidence that the Lean definition means what we intend.

How it works
    1. For each instance, builds the circuit, transpiles it to Graphix's gate set and takes Graphix's J/CZ
       stream (instructions_to_jcz).
    2. Builds the unoptimized pattern with Graphix and counts N, E, M.
    3. Feeds the same stream to Lean's `mbqc_counts` executable (lean/Main.lean), which runs compileJcz.
    4. Compares the two triples exactly.

Parameters
    method      trotter2 | qsvt | gqsp: compare on the method's whole scaling grid
    instances   or a list of {method, n, k} to compare on

Passes when
    Lean and Graphix agree on N, E and M for every instance.

Fails when
    Any instance differs (the first is recorded), or Lean is unavailable (error).

Grants
    tested (faithfulness) for the Lean definitions the node names.

Example
    - test: differential/lean_counts
      params: {method: trotter2}
"""

from __future__ import annotations

from checks._framework import Result
from checks._shared.grids import grid
from checks._shared.lean import LeanUnavailable, run_counts

from ._streams import stream_and_counts

PARAMS = {
    "method": {"enum": ["trotter2", "qsvt", "gqsp"]},
    "instances": {"type": "array", "items": {"type": "object", "required": ["method", "n", "k"],
                                             "properties": {"method": {"enum": ["trotter2", "qsvt", "gqsp"]},
                                                            "n": {"type": "integer"}, "k": {"type": "integer"}}}},
}
REQUIRED = []


def run(node, params, ctx):
    if "instances" in params:
        pts = [(i["method"], i["n"], i["k"]) for i in params["instances"]]
    elif "method" in params:
        train, holdout = grid(params["method"], ctx.quick)
        pts = [(params["method"], n, k) for n, k in train + holdout]
    else:
        return Result("error", summary="differential/lean_counts needs method or instances")
    data = [stream_and_counts(m, n, k, ctx.cache) for m, n, k in pts]
    try:
        lean = run_counts(ctx, [line for line, _ in data])
    except LeanUnavailable as e:
        return Result("error", summary=str(e))
    rows, bad = [], []
    for (m, n, k), (_, gx), lx in zip(pts, data, lean):
        rows.append({"method": m, "n": n, "k": k, "graphix": list(gx), "lean": list(lx), "agree": gx == lx})
        if gx != lx:
            bad.append(rows[-1])
    ev = {"rows": rows}
    if bad:
        b = bad[0]
        return Result("fail", summary=f"{len(bad)} of {len(rows)} instances disagree (first: {b['method']} "
                                      f"n={b['n']} k={b['k']}: Graphix {b['graphix']}, Lean {b['lean']})", evidence=ev)
    return Result("pass", summary=f"Lean and Graphix agree on N, E, M for all {len(rows)} instances", evidence=ev)
