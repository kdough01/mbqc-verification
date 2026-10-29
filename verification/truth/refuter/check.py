"""
check.py — refuter: search for a counterexample to "QSVT costs more than GQSP".

Moved here from ham_sim.py our_claim_holds(). The claim: for all n >= 2 and
degrees D >= d (QSVT degree D odd), QSVT's count exceeds GQSP's.

Node params:
    quantity: N | E | M
    source:   formula | counts
      formula: qsvt / gqsp name the Layer B nodes whose scaling `coef` to use;
               search n in [2, n_max], d in [1, k_max], odd D in [d, k_max]
      counts:  optimize: bool; search the compiled counts on both grids
               (for quantities with no closed form)
    n_max, k_max: search bounds (default 50, 41)

A counterexample refutes the claim. Finding none records what was searched,
as `empirical` evidence on that domain.
"""

from __future__ import annotations

from fractions import Fraction

from mbqc_verify.hamsim.analysis import evaluate
from verification.base import Check, CheckResult, register
from verification.truth.scaling.grids import counts


def _coef(dag, node_id):
    spec = next(c for c in dag.nodes[node_id].checks if c.kind == "scaling")
    return [Fraction(str(c)) for c in spec.params["coef"]]


@register
class RefuterCheck(Check):
    kind = "refuter"

    def run(self, node, params, ctx):
        q = params["quantity"]
        if params.get("source", "formula") == "formula":
            fq, fg = _coef(ctx.dag, params["qsvt"]), _coef(ctx.dag, params["gqsp"])
            n_max, k_max = int(params.get("n_max", 50)), int(params.get("k_max", 41))
            domain = f"n in [2, {n_max}], d in [1, {k_max}], odd D in [d, {k_max}]"
            searched = 0
            for nn in range(2, n_max + 1):
                for dd in range(1, k_max + 1):
                    for DD in range(dd if dd % 2 else dd + 1, k_max + 1, 2):
                        searched += 1
                        vq, vg = evaluate(fq, nn, DD), evaluate(fg, nn, dd)
                        if not vq > vg:
                            ce = {"n": nn, "D": DD, "d": dd, "qsvt": str(vq), "gqsp": str(vg)}
                            return CheckResult("fail", "refuted", f"counterexample n={nn}, D={DD}, d={dd}",
                                               summary=f"QSVT {q} = {vq} <= GQSP {q} = {vg} at n={nn}, D={DD}, d={dd}",
                                               evidence={"counterexample": ce, "searched": searched})
            return CheckResult("pass", "empirical", domain, summary=f"no counterexample in {searched} cases",
                               evidence={"searched": searched})

        opt = bool(params["optimize"])
        cq, cg = counts("qsvt", opt, ctx.quick, ctx.cache), counts("gqsp", opt, ctx.quick, ctx.cache)
        searched = 0
        for (nq, D), rq in sorted(cq.items()):
            for (ng, dd), rg in sorted(cg.items()):
                if nq != ng or D < dd:
                    continue
                searched += 1
                if not rq[q] > rg[q]:
                    ce = {"n": nq, "D": D, "d": dd, "qsvt": rq[q], "gqsp": rg[q]}
                    return CheckResult("fail", "refuted", f"counterexample n={nq}, D={D}, d={dd}",
                                       summary=f"QSVT {q} = {rq[q]} <= GQSP {q} = {rg[q]} at n={nq}, D={D}, d={dd}",
                                       evidence={"counterexample": ce, "searched": searched})
        return CheckResult("pass", "empirical", "compiled counts on the Layer B grids",
                           summary=f"no counterexample in {searched} grid pairs", evidence={"searched": searched})
