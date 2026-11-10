"""
refuter/hypothesis — Hypothesis generates instances of a predicate and shrinks any failure to a minimal one.

What it checks
    A claim stated as a predicate that should always hold (any claim, not only the Hamiltonian-simulation
    ones): proposals use this to search their own claims for counterexamples.

How it works
    1. Loads the predicate FILE.py:FUNCTION (checks/_shared/predicates.py); the file must be listed under the
       node's code:, so a change to it makes the evidence stale.
    2. Builds a Hypothesis strategy per variable and generates up to max_examples instances, boundary values
       included.
    3. On a failure, Hypothesis shrinks it to a minimal counterexample. Runs derandomized with the example
       database off, so the same inputs give the same evidence.

Parameters
    predicate     FILE.py:FUNCTION, called with one keyword per variable; returns a bool or (bool, detail)
    strategy      {VAR: {integers: [LOW, HIGH]} | {floats: [LOW, HIGH]} | {values: [...]} | {booleans: true}}
    max_examples  how many instances to generate (default 500)

Passes when
    No generated instance fails.

Fails when
    Some instance fails (refuted); the shrunk counterexample and the predicate's detail are recorded.

Grants
    empirical on what was generated, or refuted.

Example
    - test: refuter/hypothesis
      name: random-n
      params:
        predicate: dag/predicates/paper.p_abc.theorem_1.py:holds
        strategy: {n: {integers: [2, 200]}}
        max_examples: 1000
"""

from __future__ import annotations

from checks._framework import Result
from checks._shared.predicates import call, load_predicate

PARAMS = {
    "predicate": {"type": "string"},
    "strategy": {"type": "object", "minProperties": 1, "additionalProperties": {"type": "object"}},
    "max_examples": {"type": "integer", "minimum": 1},
}
REQUIRED = ["predicate", "strategy"]


def _strategies(spec: dict):
    from hypothesis import strategies as st
    out = {}
    for k, v in spec.items():
        if "integers" in v:
            out[k] = st.integers(*[int(x) for x in v["integers"]])
        elif "floats" in v:
            out[k] = st.floats(*[float(x) for x in v["floats"]], allow_nan=False, allow_infinity=False)
        elif "values" in v:
            out[k] = st.sampled_from(list(v["values"]))
        elif "booleans" in v:
            out[k] = st.booleans()
        else:
            raise ValueError(f"strategy.{k}: integers | floats | values | booleans")
    return out


def run(node, params, ctx):
    from hypothesis import HealthCheck, Phase, find, settings
    from hypothesis import strategies as st
    from hypothesis.errors import NoSuchExample
    try:
        pred = load_predicate(node, params["predicate"], ctx.root)
        strat = _strategies(params["strategy"])
    except (ValueError, AttributeError, OSError) as e:
        return Result("error", summary=f"refuter/hypothesis: {e}")
    n = int(params.get("max_examples", 500))
    tried = {"n": 0}

    def fails(point):
        tried["n"] += 1
        return not call(pred, point)[0]
    cfg = settings(max_examples=n, derandomize=True, database=None, deadline=None,
                   phases=[Phase.generate, Phase.shrink], suppress_health_check=list(HealthCheck))
    domain = ", ".join(f"{k} ~ {v}" for k, v in params["strategy"].items())
    try:
        ce = find(st.fixed_dictionaries(strat), fails, settings=cfg)
    except NoSuchExample:
        return Result("pass", "empirical", f"Hypothesis, {n} examples: {domain}",
                      summary=f"no counterexample in {tried['n']} generated instances (Hypothesis)",
                      evidence={"tried": tried["n"], "max_examples": n, "strategy": params["strategy"]})
    ok, detail = call(pred, ce)
    return Result("fail", "refuted", f"counterexample {ce}", summary=f"fails at {ce} (shrunk by Hypothesis)",
                  evidence={"counterexample": ce, "detail": detail, "tried": tried["n"]})
