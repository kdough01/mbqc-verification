"""
tool/azure_re_logical_counts — The Azure Quantum Resource Estimator, from the same logical counts, gives the claimed physical cost.

What it checks
    That a claimed physical-qubit count or runtime agrees with a second, independently built estimate from
    the same logical counts a paper's table rests on (the estimator runs locally through the qdk package; no
    Azure account).

How it works
    1. Gives the estimator the logical counts and its own parameters (qubit model, QEC scheme, error budget).
    2. Reports physical qubits, runtime (ns), code distance, T factories, logical qubits and the counts used.
    3. Compares the value at `path` with the claim.
    Expected values come from the node, a frozen file already in the repository, or a held-out value only CI
    can read (checks/_shared/compare.py, checks/_shared/heldout.py); a proposal never supplies a number at
    run time. The tool is pinned in tools/requirements.txt and its versions are recorded in the evidence.

Parameters
    args        {counts: {numQubits, tCount, rotationCount, rotationDepth, cczCount, measurementCount},
                 params: the estimator's parameters, e.g. {qubitParams: {name: qubit_gate_ns_e3},
                 qecScheme: {name: surface_code}, errorBudget: 0.001}}
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
    - test: tool/azure_re_logical_counts
      params: {args: {counts: {numQubits: 100, tCount: 1000000}, params: {errorBudget: 0.001}},
               path: physical_qubits, expect: [100000, 1000000], op: within, domain: "100 logical qubits"}
"""

from __future__ import annotations

from mbqc_verify.tools import azure_re

from ._run import tool_result

PARAMS = {
    "args": {"type": "object", "required": ["counts"], "additionalProperties": False, "properties": {"counts": {"type": "object"}, "params": {"type": "object"}}},
    "path": {"type": "string"},
    "expect": {"oneOf": [{"type": "number"}, {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}, {"type": "object", "required": ["heldout"], "properties": {"heldout": {"type": "string"}}, "additionalProperties": False}, {"type": "object", "required": ["path"], "properties": {"results": {"type": "string"}, "path": {"type": "string"}}, "additionalProperties": False}]},
    "op": {"enum": ["approx", "eq", "ge", "le", "within"]},
    "rel_tol": {"type": "number"},
    "domain": {"type": "string"},
}
REQUIRED = ["args", "path", "expect"]


def run(node, params, ctx):
    return tool_result("azure_re.logical_counts", azure_re.logical_counts, azure_re.versions, params, ctx)
