"""
compare.py — compare a computed value with an expected one, the way reproduction and tool tests do.

    get(data, "a.0.b")            a value by dotted path (numbers index lists)
    compare(value, expect, op, rel_tol)   op: approx (|value/expect − 1| ≤ rel_tol) | eq | ge | le |
                                  within (expect is [low, high]) -> (ok, how it compares, in words)

Expected values never come from a proposer at run time: they are a number in the node, a value in a frozen
file already in the repository, or a held-out value (checks/_shared/heldout.py) that only CI can read.
"""

from __future__ import annotations

import math


def get(data, path: str):
    for part in path.split("."):
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


def compare(value: float, expect, op: str, rel_tol: float) -> tuple[bool, str]:
    if op == "approx":
        ok = math.isclose(value, expect, rel_tol=rel_tol, abs_tol=0.0) if expect else value == 0
        rel = (value / expect - 1) if expect else None
        return ok, (f"within {rel_tol:.0%}" if ok else f"off by {rel:+.1%}" if rel is not None else "differs")
    if op == "eq":
        return value == expect, "equal" if value == expect else "not equal"
    if op == "ge":
        return value >= expect, "≥" if value >= expect else "<"
    if op == "le":
        return value <= expect, "≤" if value <= expect else ">"
    if op == "within":
        lo, hi = expect
        return lo <= value <= hi, "inside" if lo <= value <= hi else "outside"
    raise ValueError(f"unknown op {op!r}")

