"""
gridsynth.py — Ross–Selinger single-qubit synthesis (pygridsynth): Clifford+T circuits for Rz(theta) to precision eps.

    rz(args)  args: angles (list of radians, as numbers or strings), epsilon. For every angle: the T count, the
              length, and the operator-norm error of the synthesized circuit, recomputed by pygridsynth at the
              requested precision (so a result is certified, not trusted). Returns the mean and maximum T count,
              the maximum error, and 3 log2(1/eps) for comparison with the Ross–Selinger bound.
"""

from __future__ import annotations

import math
import warnings


def versions() -> dict:
    from importlib.metadata import version
    return {"pygridsynth": version("pygridsynth"), "mpmath": version("mpmath")}


def rz(args: dict) -> dict:
    import mpmath
    import pygridsynth
    eps = str(args["epsilon"])
    angles = [str(a) for a in args["angles"]]
    rows = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        for a in angles:
            gates = pygridsynth.gridsynth_gates(theta=mpmath.mpf(a), epsilon=mpmath.mpf(eps))
            err = float(pygridsynth.error(mpmath.mpf(a), gates, epsilon=mpmath.mpf(eps)))
            rows.append({"theta": a, "t_count": gates.count("T"), "length": len(gates), "error": err})
    t = [r["t_count"] for r in rows]
    return {"epsilon": float(eps), "angles": len(rows), "rows": rows,
            "mean_t_count": sum(t) / len(t), "max_t_count": max(t), "min_t_count": min(t),
            "max_error": max(r["error"] for r in rows), "all_within_epsilon": all(r["error"] <= float(eps) for r in rows),
            "three_log2_inv_eps": 3 * math.log2(1 / float(eps))}
