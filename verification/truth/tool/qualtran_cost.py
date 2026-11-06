"""
qualtran_cost.py — Qualtran: an independent count of T, Toffoli, rotation, Clifford and qubit costs for a bloq.

    cost(args)  args: bloq ("qualtran.bloqs.<module>.<Class>", only names under qualtran.bloqs), kwargs for its
                constructor. Returns Qualtran's QECGatesCost (t, toffoli, cswap, and_bloq, clifford, rotation,
                measurement, total_t_count with Qualtran's own conversions) and QubitCount.
"""

from __future__ import annotations

import importlib


def versions() -> dict:
    from importlib.metadata import version
    return {"qualtran": version("qualtran"), "cirq-core": version("cirq-core")}


def cost(args: dict) -> dict:
    name = str(args["bloq"])
    if not name.startswith("qualtran.bloqs.") or "__" in name:
        raise ValueError("bloq must name a class under qualtran.bloqs")
    module, cls = name.rsplit(".", 1)
    bloq = getattr(importlib.import_module(module), cls)(**(args.get("kwargs") or {}))
    from qualtran.resource_counting import QECGatesCost, QubitCount, get_cost_value
    gates = get_cost_value(bloq, QECGatesCost())
    out = {k: int(v) for k, v in gates.asdict().items()}
    for k in ("t", "toffoli", "cswap", "and_bloq", "clifford", "rotation", "measurement"):
        out.setdefault(k, 0)
    out["total_t_count"] = int(gates.total_t_count())
    out["qubits"] = int(get_cost_value(bloq, QubitCount()))
    out["bloq"] = str(bloq)
    return out
