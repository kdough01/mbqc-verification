"""
tool/qualtran_cost — Qualtran's independent count of T, Toffoli, rotation and qubit costs for a bloq agrees with the claim.

What it checks
    That a claimed gate or qubit count for a standard subroutine agrees with Qualtran's own cost model for the
    corresponding bloq.

How it works
    1. Builds the bloq (a class under qualtran.bloqs only) with the given constructor arguments.
    2. Computes Qualtran's QECGatesCost (t, toffoli, cswap, and_bloq, clifford, rotation, measurement, and
       total_t_count with Qualtran's own conversions) and QubitCount.
    3. Compares the value at `path` with the claim.
    Expected values come from the node, a frozen file already in the repository, or a held-out value only CI
    can read (checks/_shared/compare.py, checks/_shared/heldout.py); a proposal never supplies a number at
    run time. The tool is pinned in tools/requirements.txt and its versions are recorded in the evidence.

Parameters
    args        {bloq: "qualtran.bloqs.<module>.<Class>", kwargs: {constructor arguments}}
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
    - test: tool/qualtran_cost
      name: tcount
      params: {args: {bloq: qualtran.bloqs.arithmetic.Add, kwargs: {bitsize: 8}}, path: toffoli, expect: 7,
               op: eq, domain: "8-bit adder"}
"""

from __future__ import annotations

from mbqc_verify.tools import qualtran_cost

from ._run import tool_result

PARAMS = {
    "args": {"type": "object", "required": ["bloq"], "additionalProperties": False, "properties": {"bloq": {"type": "string"}, "kwargs": {"type": "object"}}},
    "path": {"type": "string"},
    "expect": {"oneOf": [{"type": "number"}, {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}, {"type": "object", "required": ["heldout"], "properties": {"heldout": {"type": "string"}}, "additionalProperties": False}, {"type": "object", "required": ["path"], "properties": {"results": {"type": "string"}, "path": {"type": "string"}}, "additionalProperties": False}]},
    "op": {"enum": ["approx", "eq", "ge", "le", "within"]},
    "rel_tol": {"type": "number"},
    "domain": {"type": "string"},
}
REQUIRED = ["args", "path", "expect"]


def run(node, params, ctx):
    return tool_result("qualtran.cost", qualtran_cost.cost, qualtran_cost.versions, params, ctx)
