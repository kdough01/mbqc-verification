"""
_run.py — run one pinned external tool (cached per dagtool run) and compare its output with the claim.

Every tool test is the same comparison around a different adapter (src/mbqc_verify/tools/): run the tool
with the node's args, read the value at `path` in its output, read the expectation, compare with `op`.
The tools are pinned in tools/requirements.txt, and their versions are recorded in the evidence.
"""

from __future__ import annotations

import json

from checks._framework import Result
from checks._shared.compare import compare, get
from checks._shared.heldout import HeldOutUnavailable
from checks._shared.heldout import value as heldout_value

ADAPTERS = {   # tool name -> (module under mbqc_verify.tools, function); the test is tool/<name with . -> _>
    "surface_code.memory": ("surface_code", "memory"), "surface_code.fit": ("surface_code", "fit"),
    "gridsynth.rz": ("gridsynth", "rz"), "qualtran.cost": ("qualtran_cost", "cost"),
    "azure_re.logical_counts": ("azure_re", "logical_counts"), "azure_re.qsharp": ("azure_re", "qsharp"),
}


def adapter(name: str, root):
    """(function of args, versions function) for a tool name, for `dagtool tool` and the tests."""
    import importlib
    if name not in ADAPTERS:
        raise ValueError(f"unknown tool {name!r}; one of {sorted(ADAPTERS)}")
    mod_name, fn_name = ADAPTERS[name]
    mod = importlib.import_module(f"mbqc_verify.tools.{mod_name}")
    fn = getattr(mod, fn_name)
    return (lambda args: fn(args, root)) if name == "azure_re.qsharp" else fn, mod.versions


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


def run_tool(name: str, fn, versions, args: dict, ctx) -> dict:
    """The tool's output plus the versions of what computed it, cached for the run."""
    key = ("tool", name, json.dumps(args, sort_keys=True))
    if key not in ctx.cache:
        ctx.cache[key] = {**fn(args), "versions": versions()}
    return ctx.cache[key]


def tool_result(name: str, fn, versions, params: dict, ctx) -> Result:
    path, op, tol = params["path"], params.get("op", "approx"), float(params.get("rel_tol", 0.01))
    try:
        expect, expect_from, held = expected(params, ctx.root)
    except HeldOutUnavailable as e:
        return Result("skip", summary=str(e))
    except (KeyError, IndexError, TypeError, ValueError, OSError) as e:
        return Result("error", summary=f"cannot read the expected value: {type(e).__name__}: {e}")
    args = params.get("args") or {}
    try:
        out = run_tool(name, fn, versions, args, ctx)
        value = float(get(out, path))
    except (KeyError, IndexError, TypeError, ValueError) as e:
        return Result("error", summary=f"{name}: {type(e).__name__}: {e}")
    try:
        ok, how = compare(value, expect, op, tol)
    except (ValueError, TypeError) as e:
        return Result("error", summary=str(e))
    domain = params.get("domain") or f"{name} {json.dumps(args, sort_keys=True)}"
    ev = {"tool": name, "args": args, "path": path, "value": value, "op": op,
          "rel_tol": tol if op == "approx" else None, "versions": out["versions"],
          "expect": None if held else expect, "expect_from": expect_from}
    if held:
        summary = f"{name} {path} = {value:g}: {'matches' if ok else 'does not match'} the held-out value"
    else:
        shown = f"[{expect[0]:g}, {expect[1]:g}]" if isinstance(expect, list) else f"{expect:g}"
        summary = f"{name} {path} = {value:g} vs {shown} ({expect_from}): {how}"
    return Result("pass" if ok else "fail", "empirical" if ok else "refuted", domain, summary=summary, evidence=ev)
