"""
equal_accuracy.py — Layer C: which method needs the fewest vertices at the same eps?

This comparison does not depend on how each method counts "degree". It uses the
vertex formulas of the Layer B nodes it names, so it inherits their status.
"""

from __future__ import annotations

from mbqc_verify.hamsim.analysis import cost_at_equal_accuracy

NS, TS, EPSILONS = (4, 16, 64), (1.0, 10.0), (1e-2, 1e-4, 1e-8)


def ranking(formulas: dict) -> list[dict]:
    return cost_at_equal_accuracy(formulas, ns=NS, ts=TS, epsilons=EPSILONS)
