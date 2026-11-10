"""
reproduction/recorded_value — a value recorded by a pinned pipeline agrees with the claimed value.

What it checks
    That a number a heavy experiment produced (for example experiments/rre: the paper's own pipeline, pinned)
    matches what the claim says. The experiment runs outside `dagtool run`, on CI or a larger machine, and
    commits its results as JSON with provenance; this test reads one value and compares it, so the verdict is
    computed here and goes stale whenever the results file changes (list it under the node's code:).

How it works
    1. Reads the value at `path` in the `results` file.
    2. Reads the expectation: a number, another recorded value ({results?, path}, same file by default), or a
       held-out value ({heldout: ID}) that only CI can read (checks/_shared/heldout.py).
    3. Compares them with `op` (checks/_shared/compare.py).

Parameters
    results     repo-relative JSON file the experiment wrote
    path        dotted path to the value, e.g. "quantities.phys_qubits.ours" ("a.0.b" indexes lists)
    expect      a number | {results?, path} | {heldout: ID}
    op          approx (default; |value/expect − 1| ≤ rel_tol) | eq | ge | le
    rel_tol     default 0.01
    domain      what the comparison covers, e.g. "FH 2x2, config_paper_v3.yaml"

Passes when
    The comparison holds.

Fails when
    It does not: for a reported number, "refuted" reads as "not reproduced by this pipeline and
    configuration", and the summary says by how much. A missing results file is a skip (the experiment has
    not been run yet); a held-out expectation without the key is a skip outside CI.

Grants
    empirical on the domain, or refuted. With a held-out expectation, the evidence records neither the
    expected value nor how far the result is from it.

Example
    - test: reproduction/recorded_value
      name: reproduction-n-logical
      params:
        results: experiments/rre/results/calibrated/table2_qft_N-500.json
        path: quantities.n_logical.ours
        expect: {path: quantities.n_logical.paper}
        op: approx
        rel_tol: 0.01
        domain: QFT N-500, RRE 0.26.33, config_calibrated.yaml
"""

from __future__ import annotations

import json

from checks._framework import Result
from checks._shared.compare import compare, get
from checks._shared.heldout import HeldOutUnavailable
from checks._shared.heldout import value as heldout_value

PARAMS = {
    "results": {"type": "string"},
    "path": {"type": "string"},
    "expect": {"oneOf": [{"type": "number"}, {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}, {"type": "object", "required": ["heldout"], "properties": {"heldout": {"type": "string"}}, "additionalProperties": False}, {"type": "object", "required": ["path"], "properties": {"results": {"type": "string"}, "path": {"type": "string"}}, "additionalProperties": False}]},
    "op": {"enum": ["approx", "eq", "ge", "le"]},
    "rel_tol": {"type": "number"},
    "domain": {"type": "string"},
}
REQUIRED = ["results", "path", "expect"]


def run(node, params, ctx):
    res_path, path = params["results"], params["path"]
    f = ctx.dag.root / res_path
    if not f.exists():
        return Result("skip", summary=f"no results yet: {res_path} (run the experiment that writes it)")
    data = json.loads(f.read_text(encoding="utf-8"))
    held = False
    try:
        value = float(get(data, path))
        exp = params.get("expect")
        if isinstance(exp, dict) and "heldout" in exp:
            expect, expect_from, held = heldout_value(ctx.dag.root, str(exp["heldout"])), "held out", True
        elif isinstance(exp, dict):
            other = data if not exp.get("results") else json.loads((ctx.dag.root / exp["results"]).read_text(encoding="utf-8"))
            expect, expect_from = float(get(other, exp["path"])), f"{exp.get('results', res_path)}:{exp['path']}"
        else:
            expect, expect_from = float(exp), "the claim"
    except HeldOutUnavailable as e:
        return Result("skip", summary=str(e))
    except (KeyError, IndexError, TypeError, ValueError) as e:
        return Result("error", summary=f"cannot read the values: {type(e).__name__}: {e}")
    op, tol = params.get("op", "approx"), float(params.get("rel_tol", 0.01))
    ok, how = compare(value, expect, op, tol)
    domain = params.get("domain") or res_path
    ev = {"results": res_path, "path": path, "value": value, "expect": expect, "expect_from": expect_from,
          "op": op, "rel_tol": tol if op == "approx" else None,
          "provenance": data.get("provenance") if isinstance(data, dict) else None}
    summary = f"{path} = {value:g} vs {expect:g} ({expect_from}): {how}"
    if held:   # never the held-out value, nor how far from it
        ev.update(expect=None)
        summary = f"{path} = {value:g}: {'matches' if ok else 'does not match'} the held-out value"
    if ok:
        return Result("pass", "empirical", domain, summary="reproduced: " + summary, evidence=ev)
    return Result("fail", "refuted", domain, summary="not reproduced: " + summary, evidence=ev)
