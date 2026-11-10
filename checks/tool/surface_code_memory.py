"""
tool/surface_code_memory — Stim + PyMatching estimate the logical error rate of one rotated surface-code memory experiment.

What it checks
    That a claimed logical error rate (per shot or per round) of the rotated surface code at one distance and
    physical error rate agrees with a simulation by pinned, independent tools.

How it works
    1. Builds Stim's rotated surface-code memory circuit with circuit-level depolarizing noise, every noise
       parameter = p (after Clifford gates, after reset, before measurement, before each round on data
       qubits), and samples it with a seeded sampler.
    2. Decodes with minimum-weight perfect matching (PyMatching).
    3. Reports the shot error rate, the per-round rate (sinter.shot_error_rate_to_piece_error_rate) and a
       likelihood interval (sinter.fit_binomial), and compares the value at `path` with the claim.
    Expected values come from the node, a frozen file already in the repository, or a held-out value only CI
    can read (checks/_shared/compare.py, checks/_shared/heldout.py); a proposal never supplies a number at
    run time. The tool is pinned in tools/requirements.txt and its versions are recorded in the evidence.

Parameters
    args        {distance, p, rounds (default distance), shots (default 10000), seed (default 0), basis (z | x)}
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
    - test: tool/surface_code_memory
      params: {args: {distance: 5, p: 0.001, shots: 100000}, path: per_round, expect: [1.0e-7, 1.0e-5],
               op: within, domain: "d = 5, p = 1e-3"}
"""

from __future__ import annotations

from mbqc_verify.tools import surface_code

from ._run import tool_result

PARAMS = {
    "args": {"type": "object", "required": ["distance", "p"], "additionalProperties": False, "properties": {"distance": {"type": "integer"}, "p": {"type": "number"}, "rounds": {"type": "integer"}, "shots": {"type": "integer"}, "seed": {"type": "integer"}, "basis": {"enum": ["z", "x"]}}},
    "path": {"type": "string"},
    "expect": {"oneOf": [{"type": "number"}, {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}, {"type": "object", "required": ["heldout"], "properties": {"heldout": {"type": "string"}}, "additionalProperties": False}, {"type": "object", "required": ["path"], "properties": {"results": {"type": "string"}, "path": {"type": "string"}}, "additionalProperties": False}]},
    "op": {"enum": ["approx", "eq", "ge", "le", "within"]},
    "rel_tol": {"type": "number"},
    "domain": {"type": "string"},
}
REQUIRED = ["args", "path", "expect"]


def run(node, params, ctx):
    return tool_result("surface_code.memory", surface_code.memory, surface_code.versions, params, ctx)
