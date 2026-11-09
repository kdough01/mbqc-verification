"""
check.py — reproduction: does a recorded run agree with the claim?

Heavy experiments (for example experiments/rre: the paper's own pipeline, pinned) run outside `dagtool run`,
on CI or a larger machine, and commit their results as JSON with provenance. This check reads one value from such
a file and compares it with what the claim says, so the verdict is computed here and goes stale whenever the
results file changes (list the file under the node's `code:`).

Node params:
    results:  repo-relative JSON file
    path:     dotted path to the value, e.g. "quantities.phys_qubits.ours" ("a.0.b" indexes lists)
    expect:   a number, or {results?, path} naming another recorded value (same file by default), or
              {heldout: ID}, a sealed value read only in CI (verification/truth/heldout)
    op:       approx (default, |value/expect - 1| <= rel_tol) | eq | ge | le
    rel_tol:  default 0.01
    domain:   what the comparison covers, e.g. "FH 2x2, config_paper_v3.yaml"

Agreement grants `empirical` on that domain. Disagreement refutes the claim on that domain: for a reported
number, "refuted" reads as "not reproduced by this pipeline and configuration", and the summary says by how
much. A missing results file is a skip, not a failure (the experiment has not been run yet).
"""

from __future__ import annotations

import json
import math

from verification.base import Check, CheckResult, register
from verification.truth.heldout.heldout import HeldOutUnavailable
from verification.truth.heldout.heldout import value as heldout_value


def _get(data, path: str):
    for part in path.split("."):
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


def _num(v):
    if isinstance(v, bool):
        return float(v)
    return float(v)


@register
class ReproductionCheck(Check):
    kind = "reproduction"

    def run(self, node, params, ctx):
        res_path = params.get("results")
        path = params.get("path")
        if not res_path or not path:
            return CheckResult("error", summary="reproduction needs params `results` and `path`")
        f = ctx.dag.root / res_path
        if not f.exists():
            return CheckResult("skip", summary=f"no results yet: {res_path} (run the experiment that writes it)")
        data = json.loads(f.read_text(encoding="utf-8"))
        held = False
        try:
            value = _num(_get(data, path))
            exp = params.get("expect")
            if isinstance(exp, dict) and "heldout" in exp:
                expect, expect_from, held = heldout_value(ctx.dag.root, str(exp["heldout"])), "held out", True
            elif isinstance(exp, dict):
                other = data if not exp.get("results") else json.loads((ctx.dag.root / exp["results"]).read_text(encoding="utf-8"))
                expect, expect_from = _num(_get(other, exp["path"])), f"{exp.get('results', res_path)}:{exp['path']}"
            else:
                expect, expect_from = _num(exp), "the claim"
        except HeldOutUnavailable as e:
            return CheckResult("skip", summary=str(e))
        except (KeyError, IndexError, TypeError, ValueError) as e:
            return CheckResult("error", summary=f"cannot read the values: {type(e).__name__}: {e}")
        op = params.get("op", "approx")
        tol = float(params.get("rel_tol", 0.01))
        if op == "approx":
            ok = math.isclose(value, expect, rel_tol=tol, abs_tol=0.0) if expect else value == 0
            rel = (value / expect - 1) if expect else None
            how = f"within {tol:.0%}" if ok else f"off by {rel:+.1%}" if rel is not None else "differs"
        elif op == "eq":
            ok, how = value == expect, "equal" if value == expect else "not equal"
        elif op == "ge":
            ok, how = value >= expect, "≥" if value >= expect else "<"
        elif op == "le":
            ok, how = value <= expect, "≤" if value <= expect else ">"
        else:
            return CheckResult("error", summary=f"unknown op {op!r}")
        domain = params.get("domain") or res_path
        ev = {"results": res_path, "path": path, "value": value, "expect": expect, "expect_from": expect_from,
              "op": op, "rel_tol": tol if op == "approx" else None,
              "provenance": data.get("provenance") if isinstance(data, dict) else None}
        summary = f"{path} = {value:g} vs {expect:g} ({expect_from}): {how}"
        if held:   # never the held-out value, nor how far from it
            ev.update(expect=None, rel_tol=ev["rel_tol"])
            summary = f"{path} = {value:g}: {'matches' if ok else 'does not match'} the held-out value"
        if ok:
            return CheckResult("pass", "empirical", domain, summary="reproduced: " + summary, evidence=ev)
        return CheckResult("fail", "refuted", domain, summary="not reproduced: " + summary, evidence=ev)
