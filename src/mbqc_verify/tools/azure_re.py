"""
azure_re.py — the Azure Quantum Resource Estimator, run locally through the `qdk` package (no Azure account).

    logical_counts(args)  args: counts ({numQubits, tCount, rotationCount, rotationDepth, cczCount,
                          measurementCount}), params (the estimator's own parameters, e.g. {"qubitParams":
                          {"name": "qubit_gate_ns_e3"}, "qecScheme": {"name": "surface_code"},
                          "errorBudget": 0.001}). A second, independently built estimate of physical qubits and
                          runtime from the same logical counts a paper's table rests on.
    qsharp(args)          args: file (a .q# / .qs file in the repository), entry (e.g. "Main()"), params.
                          Estimates a Q# program.
Returns physical qubits, runtime (ns), code distance, T factories, logical qubits and the logical counts used.
"""

from __future__ import annotations

import warnings
from pathlib import Path


def versions() -> dict:
    from importlib.metadata import version
    return {"qdk": version("qdk")}


def _summary(result) -> dict:
    r = dict(result)
    pc, lq = r["physicalCounts"], r["logicalQubit"]
    return {"physical_qubits": pc["physicalQubits"], "runtime_ns": pc["runtime"], "rqops": pc.get("rqops"),
            "code_distance": lq["codeDistance"], "logical_qubits": pc["breakdown"]["algorithmicLogicalQubits"],
            "t_factories": pc["breakdown"].get("numTfactories"), "logical_counts": r.get("logicalCounts"),
            "job_params": r.get("jobParams")}


def logical_counts(args: dict) -> dict:
    from qdk.estimator import LogicalCounts
    counts = {"numQubits": 0, "tCount": 0, "rotationCount": 0, "rotationDepth": 0, "cczCount": 0,
              "measurementCount": 0, **(args.get("counts") or {})}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return _summary(LogicalCounts(counts).estimate(args.get("params") or None))


def qsharp(args: dict, root: Path) -> dict:
    src = (root / args["file"]).resolve()
    if root.resolve() not in src.parents or src.suffix not in (".qs",):
        raise ValueError("qsharp needs a .qs file inside the repository")
    from qdk import qsharp as q
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        q.init()
        q.eval(src.read_text(encoding="utf-8"))
        return _summary(q.estimate(str(args.get("entry", "Main()")), params=args.get("params") or None))
