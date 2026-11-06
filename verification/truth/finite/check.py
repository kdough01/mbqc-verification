"""
check.py — finite: a predicate holds on every point of a stated finite domain (exhaustive, not sampled).

Node params:
    predicate: FILE.py:FUNCTION   a function in the repository (FILE must be listed under the node's `code:`, so a
                                  change to it makes the evidence stale). Called with one keyword argument per
                                  domain variable; returns a bool, or (bool, detail).
    domain:    {VAR: {range: [LOW, HIGH]} | {values: [...]}, ...}   ranges are inclusive integers
    max_points: default 1,000,000

Holding everywhere grants `bounded` on exactly that domain; one failing point refutes the claim there (the
first failure in lexicographic order is recorded).
"""

from __future__ import annotations

import importlib.util
import itertools
import sys
from pathlib import Path

from verification.base import Check, CheckResult, register


def load_predicate(node, spec: str, root: Path):
    """The predicate named FILE.py:FUNCTION, from a file the node lists under `code:`."""
    if ":" not in str(spec):
        raise ValueError("predicate must be FILE.py:FUNCTION")
    file, fn = str(spec).rsplit(":", 1)
    if file not in node.code:
        raise ValueError(f"{file} must be listed under the node's code: (so changes to it re-run the check)")
    path = (root / file).resolve()
    if root.resolve() not in path.parents or path.suffix != ".py" or not path.exists():
        raise ValueError(f"{file} is not a Python file in the repository")
    name = "_predicate_" + "_".join(Path(file).with_suffix("").parts)
    mod_spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(mod_spec)
    sys.modules[name] = mod
    mod_spec.loader.exec_module(mod)
    return getattr(mod, fn)


def call(pred, point: dict) -> tuple[bool, object]:
    r = pred(**point)
    return (bool(r[0]), r[1]) if isinstance(r, tuple) else (bool(r), None)


def axis(name: str, spec) -> list:
    if isinstance(spec, dict) and "range" in spec:
        lo, hi = (int(x) for x in spec["range"])
        return list(range(lo, hi + 1))
    if isinstance(spec, dict) and "values" in spec:
        return list(spec["values"])
    raise ValueError(f"domain.{name} must be {{range: [low, high]}} or {{values: [...]}}")


def describe(domain: dict) -> str:
    parts = []
    for k, v in domain.items():
        parts.append(f"{k} in [{v['range'][0]}, {v['range'][1]}]" if "range" in v else f"{k} in {list(v['values'])}")
    return ", ".join(parts)


@register
class FiniteCheck(Check):
    kind = "finite"

    def run(self, node, params, ctx):
        domain = params.get("domain") or {}
        try:
            pred = load_predicate(node, params.get("predicate", ""), ctx.root)
            axes = {k: axis(k, v) for k, v in domain.items()}
        except (ValueError, AttributeError, OSError) as e:
            return CheckResult("error", summary=f"finite: {e}")
        if not axes:
            return CheckResult("error", summary="finite needs a non-empty domain")
        size = 1
        for v in axes.values():
            size *= len(v)
        cap = int(params.get("max_points", 1_000_000))
        if size > cap:
            return CheckResult("error", summary=f"the domain has {size} points, more than max_points = {cap}")
        names = list(axes)
        dom = describe(domain)
        for values in itertools.product(*axes.values()):
            point = dict(zip(names, values))
            ok, detail = call(pred, point)
            if not ok:
                return CheckResult("fail", "refuted", f"counterexample {point}",
                                   summary=f"fails at {point}", evidence={"counterexample": point, "detail": detail,
                                                                          "checked_before": size, "domain": dom})
        return CheckResult("pass", "bounded", dom, summary=f"holds at all {size} points of {dom}",
                           evidence={"points": size, "domain": dom})
