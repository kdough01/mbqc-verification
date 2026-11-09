"""
check.py — tool: a pinned external tool computes a value in CI, and it is compared with a frozen claim.

Node params:
    tool:     surface_code.memory | surface_code.fit | gridsynth.rz | qualtran.cost | azure_re.logical_counts |
              azure_re.qsharp
    args:     the tool's arguments (see each adapter in this folder)
    path:     dotted path to the value in the tool's output, e.g. "per_round" or "rows.0.t_count"
    expect:   a number | {results: FILE, path: P} (a frozen file, e.g. a transcribed table) | {heldout: ID}
    op:       approx (default; |value/expect - 1| <= rel_tol) | eq | ge | le | within (expect is [low, high])
    rel_tol:  default 0.01
    domain:   what the comparison covers

Tools are pinned in requirements.txt; their versions are recorded in the evidence. Agreement grants `empirical`
on the domain; disagreement refutes the claim there. A held-out expectation without the key is a skip, and its
evidence records neither the expected value nor the deviation.
"""

from __future__ import annotations

import json
import math

from verification.base import Check, CheckResult, register
from verification.truth.heldout.heldout import HeldOutUnavailable
from verification.truth.heldout.heldout import value as heldout_value

from . import azure_re, gridsynth, qualtran_cost, surface_code

TOOLS = {
    "surface_code.memory": (surface_code.memory, surface_code.versions),
    "surface_code.fit": (surface_code.fit, surface_code.versions),
    "gridsynth.rz": (gridsynth.rz, gridsynth.versions),
    "qualtran.cost": (qualtran_cost.cost, qualtran_cost.versions),
    "azure_re.logical_counts": (azure_re.logical_counts, azure_re.versions),
    "azure_re.qsharp": (None, azure_re.versions),
}


def get(data, path: str):
    for part in path.split("."):
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


def run_tool(name: str, args: dict, ctx=None) -> dict:
    """Run one tool (cached per dagtool run): its output plus the versions of what computed it."""
    if name not in TOOLS:
        raise ValueError(f"unknown tool {name!r}; one of {sorted(TOOLS)}")
    key = ("tool", name, json.dumps(args, sort_keys=True))
    cache = ctx.cache if ctx is not None else {}
    if key not in cache:
        fn, ver = TOOLS[name]
        out = azure_re.qsharp(args, ctx.root) if name == "azure_re.qsharp" else fn(args)
        cache[key] = {**out, "versions": ver()}
    return cache[key]


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


def expected(params: dict, root) -> tuple[object, str, bool]:
    """(expected value, where it came from, held out?) — never a number the proposer supplies at run time."""
    exp = params.get("expect")
    if isinstance(exp, dict) and "heldout" in exp:
        return heldout_value(root, str(exp["heldout"])), "held out", True
    if isinstance(exp, dict):
        data = json.loads((root / exp["results"]).read_text(encoding="utf-8"))
        return float(get(data, exp["path"])), f"{exp['results']}:{exp['path']}", False
    if isinstance(exp, list):
        return [float(x) for x in exp], "the claim", False
    return float(exp), "the claim", False


@register
class ToolCheck(Check):
    kind = "tool"

    def run(self, node, params, ctx):
        name, path = params.get("tool"), params.get("path")
        if not name or not path:
            return CheckResult("error", summary="tool needs params `tool` and `path`")
        op = params.get("op", "approx")
        tol = float(params.get("rel_tol", 0.01))
        try:
            expect, expect_from, held = expected(params, ctx.root)
        except HeldOutUnavailable as e:
            return CheckResult("skip", summary=str(e))
        except (KeyError, IndexError, TypeError, ValueError, OSError) as e:
            return CheckResult("error", summary=f"cannot read the expected value: {type(e).__name__}: {e}")
        try:
            out = run_tool(name, params.get("args") or {}, ctx)
            value = float(get(out, path))
        except (KeyError, IndexError, TypeError, ValueError) as e:
            return CheckResult("error", summary=f"{name}: {type(e).__name__}: {e}")
        try:
            ok, how = compare(value, expect, op, tol)
        except (ValueError, TypeError) as e:
            return CheckResult("error", summary=str(e))
        domain = params.get("domain") or f"{name} {json.dumps(params.get('args') or {}, sort_keys=True)}"
        ev = {"tool": name, "args": params.get("args") or {}, "path": path, "value": value, "op": op,
              "rel_tol": tol if op == "approx" else None, "versions": out["versions"],
              "expect": None if held else expect, "expect_from": expect_from}
        if held:
            summary = f"{name} {path} = {value:g}: {'matches' if ok else 'does not match'} the held-out value"
        else:
            shown = f"[{expect[0]:g}, {expect[1]:g}]" if isinstance(expect, list) else f"{expect:g}"
            summary = f"{name} {path} = {value:g} vs {shown} ({expect_from}): {how}"
        if ok:
            return CheckResult("pass", "empirical", domain, summary=summary, evidence=ev)
        return CheckResult("fail", "refuted", domain, summary=summary, evidence=ev)
