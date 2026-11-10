"""
tool/surface_code_fit — A threshold-model fit to surface-code simulations agrees with a claimed κ or p_th.

What it checks
    That a claimed logical-error model per_round = κ (p / p_th)^((d + 1) / 2) (the form of Saadatmand et al.
    Eq. (1)) agrees with a fit to Stim + PyMatching simulations on a grid of distances and error rates.

How it works
    1. Runs surface_code_memory's experiment at every distance and physical error rate of the grid.
    2. Fits per_round = κ (p / p_th)^((d + 1) / 2) by least squares in log space.
    3. Compares the fitted value at `path` (kappa, p_th, or a grid point) with the claim.
    Expected values come from the node, a frozen file already in the repository, or a held-out value only CI
    can read (checks/_shared/compare.py, checks/_shared/heldout.py); a proposal never supplies a number at
    run time. The tool is pinned in tools/requirements.txt and its versions are recorded in the evidence.

Parameters
    args        {distances: [d, ...], ps: [p, ...], shots (default 10000), seed (default 0), rounds, basis}
    path        dotted path to the value in the tool's output
    expect      a number | [low, high] (op: within) | {results: FILE, path: P} | {heldout: ID}
    op          approx (default; |value/expect − 1| ≤ rel_tol) | eq | ge | le | within
    rel_tol     default 0.01
    domain      what the comparison covers

Passes when
    The tool's value compares with the expectation as `op` says.

Fails when
    It does not (refuted on the domain). A tool error or an unreadable expectation is an error; a held-out
    expectation without the key is a skip outside CI.

Grants
    empirical on the domain, or refuted. With a held-out expectation, the evidence records neither the
    expected value nor the deviation.

Example
    - test: tool/surface_code_fit
      params: {args: {distances: [3, 5, 7], ps: [0.002, 0.004]}, path: p_th, expect: 0.01, op: approx,
               rel_tol: 0.3, domain: "d in 3..7"}
"""

from __future__ import annotations

from mbqc_verify.tools import surface_code

from ._run import tool_result

PARAMS = {
    "args": {"type": "object", "required": ["distances", "ps"], "additionalProperties": False, "properties": {"distances": {"type": "array", "items": {"type": "integer"}}, "ps": {"type": "array", "items": {"type": "number"}}, "shots": {"type": "integer"}, "seed": {"type": "integer"}, "rounds": {"type": "integer"}, "basis": {"enum": ["z", "x"]}}},
    "path": {"type": "string"},
    "expect": {"oneOf": [{"type": "number"}, {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}, {"type": "object", "required": ["heldout"], "properties": {"heldout": {"type": "string"}}, "additionalProperties": False}, {"type": "object", "required": ["path"], "properties": {"results": {"type": "string"}, "path": {"type": "string"}}, "additionalProperties": False}]},
    "op": {"enum": ["approx", "eq", "ge", "le", "within"]},
    "rel_tol": {"type": "number"},
    "domain": {"type": "string"},
}
REQUIRED = ["args", "path", "expect"]


def run(node, params, ctx):
    return tool_result("surface_code.fit", surface_code.fit, surface_code.versions, params, ctx)
