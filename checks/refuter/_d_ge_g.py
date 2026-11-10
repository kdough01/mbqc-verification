"""
_d_ge_g.py — the claim the two qsvt_exceeds_gqsp tests search: for all n ≥ 2 and degrees D ≥ d (QSVT's D
odd), QSVT's count exceeds GQSP's. Shared result shapes.
"""

from __future__ import annotations

from checks._framework import Result


def counterexample(q: str, n, D, d, vq, vg, searched: int) -> Result:
    ce = {"n": n, "D": D, "d": d, "qsvt": str(vq) if not isinstance(vq, int) else vq,
          "gqsp": str(vg) if not isinstance(vg, int) else vg}
    return Result("fail", "refuted", f"counterexample n={n}, D={D}, d={d}",
                  summary=f"QSVT {q} = {vq} <= GQSP {q} = {vg} at n={n}, D={D}, d={d}",
                  evidence={"counterexample": ce, "searched": searched})
