"""
numerical/equal_accuracy — which method needs the fewest vertices at the same accuracy ε.

What it checks
    Statements about the cheapest method at equal accuracy: that a method is never the cheapest, or that a
    given method is the cheapest at a given ε. This comparison does not depend on how each method counts
    "degree", only on the vertex formulas of the Layer B nodes it names, so it inherits their status.

How it works
    1. Reads each named node's scaling formula (its scaling/bilinear_formula coefficients).
    2. For n in {4, 16, 64}, t in {1, 10} and ε in {1e-2, 1e-4, 1e-8}, takes each method's repetitions for
       accuracy ε and evaluates its formula (mbqc_verify.hamsim.analysis.cost_at_equal_accuracy).
    3. Ranks the methods by cost and evaluates every expectation on every case, for every formula set.

Parameters
    formulas    {set name: {method: node id}}, e.g. {unoptimized: {qsvt: hamsim.B.qsvt.N.unopt, ...}}
    expect      {never_cheapest: [method, ...], cheapest_at_eps: {eps: method}}

Passes when
    Every expectation holds on every case of every formula set.

Fails when
    Any expectation fails; the first failure is the summary.

Grants
    empirical on the cases listed.

Example
    - test: numerical/equal_accuracy
      params:
        formulas: {unoptimized: {qsvt: hamsim.B.qsvt.N.unopt, gqsp: hamsim.B.gqsp.N.unopt}}
        expect: {never_cheapest: [trotter2]}
"""

from __future__ import annotations

from fractions import Fraction

from checks._framework import Result

from ._equal_accuracy import EPSILONS, NS, TS, ranking

PARAMS = {
    "formulas": {"type": "object", "additionalProperties": {"type": "object", "additionalProperties": {"type": "string"}}},
    "expect": {"type": "object", "properties": {"never_cheapest": {"type": "array", "items": {"type": "string"}},
                                                "cheapest_at_eps": {"type": "object"}}, "additionalProperties": False},
}
REQUIRED = ["formulas"]


def _coef(dag, node_id):
    spec = next(c for c in dag.nodes[node_id].checks if c.test == "scaling/bilinear_formula")
    return [float(Fraction(str(c))) for c in spec.params["coef"]]


def run(node, params, ctx):
    expect = params.get("expect", {})
    results, failures = {}, []
    for tag, by_method in params["formulas"].items():
        rows = ranking({method: _coef(ctx.dag, node_id) for method, node_id in by_method.items()})
        results[tag] = rows
        for m in expect.get("never_cheapest", []):
            hits = [r for r in rows if r["best"] == m]
            if hits:
                failures.append(f"{tag}: {m} is cheapest at n={hits[0]['n']}, t={hits[0]['t']}, eps={hits[0]['eps']}")
        for eps, m in expect.get("cheapest_at_eps", {}).items():
            for r in rows:
                if abs(r["eps"] - float(eps)) < 1e-15 and r["best"] != m:
                    failures.append(f"{tag}: at eps={eps}, n={r['n']}, t={r['t']} the cheapest is {r['best']}, not {m}")
    domain = f"n in {list(NS)}, t in {list(TS)}, eps in {list(EPSILONS)}"
    ev = {"rows": results, "failures": failures}
    if failures:
        return Result("fail", "refuted", domain, summary=failures[0], evidence=ev)
    return Result("pass", "empirical", domain,
                  summary=f"all predicates hold on {sum(len(v) for v in results.values())} cases", evidence=ev)
