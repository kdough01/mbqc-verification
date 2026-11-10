"""
finite/exhaustive — a predicate holds at every point of a stated finite domain.

What it checks
    That a claim, stated as a predicate, holds on every point of a finite domain: every combination of the
    variables' values, not a sample.

How it works
    1. Loads the predicate FILE.py:FUNCTION (checks/_shared/predicates.py); the file must be listed under the
       node's code:, so a change to it makes the evidence stale.
    2. Enumerates the domain in lexicographic order (ranges are inclusive integers).
    3. Calls the predicate at every point and stops at the first failure.

Parameters
    predicate   FILE.py:FUNCTION, called with one keyword per variable; returns a bool or (bool, detail)
    domain      {VAR: {range: [LOW, HIGH]} | {values: [...]}, ...}
    max_points  the largest domain allowed (default 1,000,000)

Passes when
    The predicate holds at every point.

Fails when
    It fails at some point (refuted); the first failure in lexicographic order is recorded.

Grants
    bounded: a proof on exactly that domain.

Example
    - test: finite/exhaustive
      name: small-n
      params:
        predicate: dag/predicates/paper.p_abc.theorem_1.py:holds
        domain: {n: {range: [2, 40]}, k: {values: [1, 3, 5]}}
"""

from __future__ import annotations

import itertools

from checks._framework import Result
from checks._shared.predicates import call, load_predicate

PARAMS = {
    "predicate": {"type": "string"},
    "domain": {"type": "object", "minProperties": 1, "additionalProperties": {"type": "object"}},
    "max_points": {"type": "integer", "minimum": 1},
}
REQUIRED = ["predicate", "domain"]


def axis(name: str, spec) -> list:
    if isinstance(spec, dict) and "range" in spec:
        lo, hi = (int(x) for x in spec["range"])
        return list(range(lo, hi + 1))
    if isinstance(spec, dict) and "values" in spec:
        return list(spec["values"])
    raise ValueError(f"domain.{name} must be {{range: [low, high]}} or {{values: [...]}}")


def describe(domain: dict) -> str:
    return ", ".join(f"{k} in [{v['range'][0]}, {v['range'][1]}]" if "range" in v else f"{k} in {list(v['values'])}"
                     for k, v in domain.items())


def run(node, params, ctx):
    domain = params["domain"]
    try:
        pred = load_predicate(node, params["predicate"], ctx.root)
        axes = {k: axis(k, v) for k, v in domain.items()}
    except (ValueError, AttributeError, OSError) as e:
        return Result("error", summary=f"finite/exhaustive: {e}")
    size = 1
    for v in axes.values():
        size *= len(v)
    cap = int(params.get("max_points", 1_000_000))
    if size > cap:
        return Result("error", summary=f"the domain has {size} points, more than max_points = {cap}")
    names, dom = list(axes), describe(domain)
    for values in itertools.product(*axes.values()):
        point = dict(zip(names, values))
        ok, detail = call(pred, point)
        if not ok:
            return Result("fail", "refuted", f"counterexample {point}", summary=f"fails at {point}",
                          evidence={"counterexample": point, "detail": detail, "checked_before": size, "domain": dom})
    return Result("pass", "bounded", dom, summary=f"holds at all {size} points of {dom}",
                  evidence={"points": size, "domain": dom})
