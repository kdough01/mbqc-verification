"""
tool/gridsynth_rz — Ross–Selinger synthesis gives the claimed T count for Rz rotations at precision ε.

What it checks
    That a claimed T count (or length, or error) of Clifford+T circuits for single-qubit Rz(θ) rotations at
    precision ε agrees with the Ross–Selinger algorithm (pygridsynth).

How it works
    1. Synthesizes each angle at precision ε with pygridsynth.
    2. Recomputes each circuit's operator-norm error at the requested precision, so a result is certified, not
       trusted.
    3. Reports the mean and maximum T count, the maximum error and 3 log2(1/ε) (the Ross–Selinger bound) and
       compares the value at `path` with the claim.
    Expected values come from the node, a frozen file already in the repository, or a held-out value only CI
    can read (checks/_shared/compare.py, checks/_shared/heldout.py); a proposal never supplies a number at
    run time. The tool is pinned in tools/requirements.txt and its versions are recorded in the evidence.

Parameters
    args        {angles: [θ, ...] (radians, numbers or strings such as "pi/7"), epsilon}
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
    - test: tool/gridsynth_rz
      params: {args: {angles: ["0.3", "1.1"], epsilon: "1e-10"}, path: max_t_count, expect: 110, op: le,
               domain: "two angles, eps = 1e-10"}
"""

from __future__ import annotations

from mbqc_verify.tools import gridsynth

from ._run import tool_result

PARAMS = {
    "args": {"type": "object", "required": ["angles", "epsilon"], "additionalProperties": False, "properties": {"angles": {"type": "array", "items": {"type": ["number", "string"]}}, "epsilon": {"type": ["number", "string"]}}},
    "path": {"type": "string"},
    "expect": {"oneOf": [{"type": "number"}, {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}, {"type": "object", "required": ["heldout"], "properties": {"heldout": {"type": "string"}}, "additionalProperties": False}, {"type": "object", "required": ["path"], "properties": {"results": {"type": "string"}, "path": {"type": "string"}}, "additionalProperties": False}]},
    "op": {"enum": ["approx", "eq", "ge", "le", "within"]},
    "rel_tol": {"type": "number"},
    "domain": {"type": "string"},
}
REQUIRED = ["args", "path", "expect"]


def run(node, params, ctx):
    return tool_result("gridsynth.rz", gridsynth.rz, gridsynth.versions, params, ctx)
