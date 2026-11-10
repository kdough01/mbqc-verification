"""
mutation/scaling_coefficients — every ±1 change to a scaling formula's coefficients is rejected.

What it checks
    That the node's scaling test can tell its formula from a nearby wrong one. If a formula still "passes"
    after a coefficient changes, the test behind it is too weak to tell the difference, and the statement's
    evidence means less than it seems. This catches vacuous tests and over-loose statements early.

How it works
    1. Takes the node's first formula scaling test (scaling/bilinear_formula, gate_counts or circuit_width)
       and the same counts it compares against.
    2. Makes 8 mutants: each of the four coefficients a, b, c, e shifted by +1 and by −1.
    3. Re-runs the exact comparison for each mutant.

Parameters
    (none)

Passes when
    Every mutant misses at least one count.

Fails when
    A mutant matches every count (it survived): the grid cannot distinguish the formula from it.

Grants
    tested (faithfulness). A skip if the unmutated formula already fails.

Example
    - test: mutation/scaling_coefficients
"""

from __future__ import annotations

from fractions import Fraction

from checks._framework import Result
from checks._shared.grids import compiler_counts, gate_counts, mismatches
from checks.scaling._compare import FORMULA_TESTS

PARAMS = {}
REQUIRED = []
NAMES = ("a (n*k)", "b (k)", "c (n)", "e (const)")


def _spec(node):
    return next((c for c in node.checks if c.test in FORMULA_TESTS), None)


def applies_to(node):
    return _spec(node) is not None


def _data(spec, ctx):
    p = spec.params
    if spec.test == "scaling/bilinear_formula":
        return p["quantity"], compiler_counts(p.get("compiler", "graphix"), p["method"], ctx.quick, ctx.cache)
    q = f"gate:{p['gate']}" if spec.test == "scaling/gate_counts" else "width"
    return q, gate_counts(p["method"], ctx.quick, ctx.cache)


def _shift(c, delta):
    v = Fraction(str(c)) + delta
    return int(v) if v.denominator == 1 else str(v)


def run(node, params, ctx):
    spec = _spec(node)
    q, data = _data(spec, ctx)
    coef = spec.params["coef"]
    if mismatches([str(c) for c in coef], data, q):
        return Result("skip", summary="the unmutated formula already fails; nothing to compare")
    rows, survivors = [], []
    for i in range(4):
        for delta in (1, -1):
            mutant = list(coef)
            mutant[i] = _shift(mutant[i], delta)
            miss = mismatches(mutant, data, q)
            rows.append({"mutant": f"{NAMES[i]} {'+' if delta > 0 else '-'}1", "coef": [str(c) for c in mutant],
                         "rejected": bool(miss), "first_mismatch": miss[0] if miss else None})
            if not miss:
                survivors.append(rows[-1]["mutant"])
    if survivors:
        return Result("fail", summary=f"{len(survivors)} mutant(s) survived: {', '.join(survivors)}",
                      evidence={"mutants": rows})
    return Result("pass", summary=f"all {len(rows)} coefficient mutants rejected", evidence={"mutants": rows})
