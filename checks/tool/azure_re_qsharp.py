"""
tool/azure_re_qsharp — The Azure Quantum Resource Estimator, run on a Q# program, gives the claimed physical cost.

What it checks
    That a claimed physical-qubit count or runtime for a program agrees with the Azure Quantum Resource
    Estimator's estimate of the same program written in Q#.

How it works
    1. Compiles the Q# file in the repository and estimates its entry point with the estimator's parameters.
    2. Reports physical qubits, runtime (ns), code distance, T factories and logical counts.
    3. Compares the value at `path` with the claim.
    Expected values come from the node, a frozen file already in the repository, or a held-out value only CI
    can read (checks/_shared/compare.py, checks/_shared/heldout.py); a proposal never supplies a number at
    run time. The tool is pinned in tools/requirements.txt and its versions are recorded in the evidence.

Parameters
    args        {file: a .qs file in the repository, entry (default "Main()"), params: the estimator's parameters}
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
    - test: tool/azure_re_qsharp
      params: {args: {file: experiments/qsharp/adder.qs, entry: "Main()"}, path: physical_qubits,
               expect: [1000, 100000], op: within, domain: "adder.qs"}
"""

from __future__ import annotations

from mbqc_verify.tools import azure_re

from ._run import tool_result

PARAMS = {
    "args": {"type": "object", "required": ["file"], "additionalProperties": False, "properties": {"file": {"type": "string"}, "entry": {"type": "string"}, "params": {"type": "object"}}},
    "path": {"type": "string"},
    "expect": {"oneOf": [{"type": "number"}, {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}, {"type": "object", "required": ["heldout"], "properties": {"heldout": {"type": "string"}}, "additionalProperties": False}, {"type": "object", "required": ["path"], "properties": {"results": {"type": "string"}, "path": {"type": "string"}}, "additionalProperties": False}]},
    "op": {"enum": ["approx", "eq", "ge", "le", "within"]},
    "rel_tol": {"type": "number"},
    "domain": {"type": "string"},
}
REQUIRED = ["args", "path", "expect"]


def run(node, params, ctx):
    return tool_result("azure_re.qsharp", lambda args: azure_re.qsharp(args, ctx.root), azure_re.versions, params, ctx)
