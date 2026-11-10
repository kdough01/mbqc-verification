"""
differential/lean_gate_streams — Lean's per-gate decompositions give Graphix's J/CZ stream token for token.

What it checks
    That Lean's model of how Graphix turns each gate into J and CZ instructions (Gate.jcz and gatesToJcz,
    lean/MBQC/Defs/GraphixGates.lean) is exactly Graphix's own (instructions_to_jcz), not just in its counts.
    The Lean proofs of the unoptimized formulas rest on this model.

How it works
    1. Takes every gate kind of the Lean model on several qubit orders (so control and target are never
       confused) with generic angles, plus the whole transpiled circuit of each listed instance.
    2. Writes each as a Lean `G` line and runs Lean's `mbqc_counts` executable, which prints gatesToJcz.
    3. Compares Lean's stream with Graphix's instructions_to_jcz stream, token by token (global phases, which
       change no count, are dropped).

Parameters
    instances   list of {method, n, k}: whole circuits to compare besides the single gates

Passes when
    Every stream is identical.

Fails when
    Any stream differs; the first case and the first differing token are recorded.

Grants
    tested (faithfulness) for the Lean gate model.

Example
    - test: differential/lean_gate_streams
      params: {instances: [{method: trotter2, n: 2, k: 1}, {method: qsvt, n: 2, k: 3}]}
"""

from __future__ import annotations

from checks._framework import Result
from checks._shared.lean import LeanUnavailable, run_lines

from ._streams import circuit_instructions, gate_token, jcz_tokens, single_gates

PARAMS = {
    "instances": {"type": "array", "items": {"type": "object", "required": ["method", "n", "k"],
                                             "properties": {"method": {"enum": ["trotter2", "qsvt", "gqsp"]},
                                                            "n": {"type": "integer"}, "k": {"type": "integer"}}}},
}
REQUIRED = []


def run(node, params, ctx):
    cases = single_gates()
    pts = [(i["method"], i["n"], i["k"]) for i in params.get("instances", [])]
    cases += [(f"{m} n={n} k={k}", circuit_instructions(m, n, k)) for m, n, k in pts]
    graphix = [jcz_tokens(ins) for _, ins in cases]
    try:
        lean = run_lines(ctx, ["G " + " ".join(gate_token(i) for i in ins) for _, ins in cases])
    except LeanUnavailable as e:
        return Result("error", summary=str(e))
    rows, bad = [], []
    for (name, ins), gx, lx in zip(cases, graphix, lean):
        lx = lx.split()
        rows.append({"case": name, "gates": len(ins), "tokens": len(gx), "agree": gx == lx})
        if gx != lx:
            first = next((i for i, (u, v) in enumerate(zip(gx, lx)) if u != v), min(len(gx), len(lx)))
            rows[-1] |= {"first_difference": first, "graphix": gx[first:first + 6], "lean": lx[first:first + 6]}
            bad.append(rows[-1])
    ev = {"rows": rows}
    if bad:
        b = bad[0]
        return Result("fail", summary=f"{len(bad)} of {len(rows)} J/CZ streams differ (first: {b['case']} at "
                                      f"token {b['first_difference']})", evidence=ev)
    return Result("pass", summary=f"Lean's gate decompositions reproduce Graphix's J/CZ stream token for token on "
                                  f"{len(rows) - len(pts)} single gates and {len(pts)} whole circuits", evidence=ev)
