"""
check.py — numerical: simulate and compare with the exact answer on a stated domain.

Node params (`which` picks the experiment):
    which: accuracy,        method: trotter1 | trotter2 | qsvt | gqsp
        Every case has error <= eps. A case above eps refutes the claim.
    which: trotter_circuit, tol: float
        The Trotter circuit equals the product formula to within tol.
    which: equal_accuracy,  formulas: {unoptimized: {method: node id}, optimized: {...}},
                            expect: {never_cheapest: [..], cheapest_at_eps: {eps: method}}
        Predicates about the cheapest method at equal accuracy, for every formula set.
Grants at most `empirical`.
"""

from __future__ import annotations

from verification.base import Check, CheckResult, register

from .equal_accuracy import EPSILONS, NS, TS, ranking
from .hamsim_accuracy import accuracy_domain, accuracy_rows, check_trotter_circuit_matches_formula


def _domain(d: dict) -> str:
    return f"n in {list(d['ns'])}, t in {list(d['ts'])}, eps in {list(d['epsilons'])}"


@register
class NumericalCheck(Check):
    kind = "numerical"

    def run(self, node, params, ctx):
        which = params["which"]
        if which == "accuracy":
            return self._accuracy(params, ctx)
        if which == "trotter_circuit":
            worst = check_trotter_circuit_matches_formula()
            tol = float(params.get("tol", 1e-10))
            ok = worst <= tol
            return CheckResult("pass" if ok else "fail", "empirical" if ok else "refuted",
                               "n in [2, 3], r in [1, 2, 5], order 1 and 2, t = 0.7",
                               summary=f"max |circuit - product formula| = {worst:.1e} (tol {tol:.0e})",
                               evidence={"max_deviation": worst, "tol": tol})
        if which == "equal_accuracy":
            return self._equal_accuracy(node, params, ctx)
        raise ValueError(f"unknown numerical experiment {which!r}")

    def _accuracy(self, params, ctx):
        method = params["method"]
        rows = [r for r in accuracy_rows(ctx.quick, ctx.cache) if r["method"] == method]
        domain = _domain(accuracy_domain(ctx.quick))
        worst = max(rows, key=lambda r: r["err"] / r["eps"])
        ev = {"rows": rows, "worst_ratio": worst["err"] / worst["eps"]}
        bad = [r for r in rows if not r["ok"]]
        if bad:
            b = bad[0]
            return CheckResult("fail", "refuted", f"counterexample n={b['n']}, t={b['t']}, eps={b['eps']}",
                               summary=f"{len(bad)} of {len(rows)} cases exceed eps", evidence=ev)
        return CheckResult("pass", "empirical", domain,
                           summary=f"{len(rows)}/{len(rows)} cases within eps; worst error/eps = "
                                   f"{ev['worst_ratio']:.2g}", evidence=ev)

    def _equal_accuracy(self, node, params, ctx):
        expect = params.get("expect", {})
        results, failures = {}, []
        for tag, by_method in params["formulas"].items():
            formulas = {}
            for method, node_id in by_method.items():
                spec = next(c for c in ctx.dag.nodes[node_id].checks if c.kind == "scaling")
                formulas[method] = [float(eval_fraction(c)) for c in spec.params["coef"]]
            rows = ranking(formulas)
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
            return CheckResult("fail", "refuted", domain, summary=failures[0], evidence=ev)
        return CheckResult("pass", "empirical", domain,
                           summary=f"all predicates hold on {sum(len(v) for v in results.values())} cases",
                           evidence=ev)


def eval_fraction(x) -> float:
    from fractions import Fraction
    return float(Fraction(str(x)))
