"""
numerical/hamsim_accuracy — the repetitions the theory gives reach accuracy ε, checked against e^{-iHt}.

What it checks
    That for a Hamiltonian-simulation method, the number of repetitions the imported error bound gives
    (Trotter steps, QSVT or GQSP degree) really produces an approximation within ε of the exact evolution
    e^{-iHt}, in spectral norm, on every case of the domain.

How it works
    1. For each n, builds a random Ising chain (seed n) and its exact e^{-iHt} with scipy's expm.
    2. For each t and ε, takes the repetitions the bound gives and builds the method's operator: the Trotter
       product formula, or the post-selected block of the QSVT/GQSP circuit.
    3. Measures the spectral-norm error against the exact evolution and compares it with ε.
    Domain: n in {2, 3}, t in {0.5, 2.0}, ε in {1e-2, 1e-3, 1e-5} (quick runs: n = 2, ε in {1e-2, 1e-4}).

Parameters
    method      trotter1 | trotter2 | qsvt | gqsp

Passes when
    Every case has error ≤ ε.

Fails when
    Any case exceeds ε; it is recorded as the counterexample (n, t, ε).

Grants
    empirical on the domain.

Example
    - test: numerical/hamsim_accuracy
      params: {method: qsvt}
"""

from __future__ import annotations

from checks._framework import Result

from ._accuracy import accuracy_domain, accuracy_rows

PARAMS = {"method": {"enum": ["trotter1", "trotter2", "qsvt", "gqsp"]}}
REQUIRED = ["method"]


def _domain(d: dict) -> str:
    return f"n in {list(d['ns'])}, t in {list(d['ts'])}, eps in {list(d['epsilons'])}"


def run(node, params, ctx):
    method = params["method"]
    rows = [r for r in accuracy_rows(ctx.quick, ctx.cache) if r["method"] == method]
    domain = _domain(accuracy_domain(ctx.quick))
    worst = max(rows, key=lambda r: r["err"] / r["eps"])
    ev = {"rows": rows, "worst_ratio": worst["err"] / worst["eps"]}
    bad = [r for r in rows if not r["ok"]]
    if bad:
        b = bad[0]
        return Result("fail", "refuted", f"counterexample n={b['n']}, t={b['t']}, eps={b['eps']}",
                      summary=f"{len(bad)} of {len(rows)} cases exceed eps", evidence=ev)
    return Result("pass", "empirical", domain,
                  summary=f"{len(rows)}/{len(rows)} cases within eps; worst error/eps = {ev['worst_ratio']:.2g}", evidence=ev)
