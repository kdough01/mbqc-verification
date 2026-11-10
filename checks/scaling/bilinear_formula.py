"""
scaling/bilinear_formula — a resource formula reproduces every compiled count, held-out points included.

What it checks
    That one count of the compiled MBQC pattern (N vertices, E edges or M measurements) equals
    (a n + b) k + c n + e at every point of the method's scaling grid. n is the number of data qubits and k
    the method's repetition parameter (Trotter steps r, QSVT degree D, GQSP degree d).

How it works
    1. For each (n, k) of the method's grid (checks/_shared/grids.py: training points plus held-out points
       never used to find the formula), builds the circuit with a fixed seed (1000 n + k).
    2. Compiles it with the chosen compiler (src/mbqc_verify/compilers/). Graphix runs here; a compiler that
       needs its own environment (Cabaliser) is read from its record in experiments/compilers/results/.
    3. Compares each count with the formula exactly, with rational arithmetic and no tolerance.
    The evidence keeps every count and a least-squares fit, so a near miss shows what the data says.

Parameters
    method      trotter2 | qsvt | gqsp
    compiler    graphix | graphix_opt | cabaliser (default graphix)
    quantity    N | E | M
    coef        [a, b, c, e], numbers or fraction strings such as "3/2"

Passes when
    The formula is exact on every training and held-out point.

Fails when
    Any count differs. The first mismatch is recorded as the counterexample, with the count and the formula's
    value. A formula can hold in theory with a constant this grid does not show; a failure says the formula as
    written is wrong at that point, not that the asymptotics are.

Grants
    empirical on the grid (the counts come from running the compiler). A Lean proof of the same formula is
    what makes it hold for every n and k.

Cost
    Seconds for Graphix unoptimized and for recorded compilers; minutes for Graphix-optimized QSVT (the
    counts are cached for the rest of the run).

Example
    - test: scaling/bilinear_formula
      params: {method: trotter2, compiler: graphix, quantity: N, coef: [10, -6, 3, 0]}
"""

from __future__ import annotations

from checks._shared.grids import compiler_counts

from ._compare import evidence, formula_result

PARAMS = {
    "method": {"enum": ["trotter2", "qsvt", "gqsp"]},
    "compiler": {"enum": ["graphix", "graphix_opt", "cabaliser"]},
    "quantity": {"enum": ["N", "E", "M"]},
    "coef": {"type": "array", "minItems": 4, "maxItems": 4, "items": {"type": ["integer", "number", "string"]}},
}
REQUIRED = ["method", "quantity", "coef"]


def run(node, params, ctx):
    method, q, compiler = params["method"], params["quantity"], params.get("compiler", "graphix")
    data = compiler_counts(compiler, method, ctx.quick, ctx.cache)
    ev = evidence(method, q, data, ctx.quick, compiler=compiler, optimize=compiler == "graphix_opt")
    return formula_result(method, q, params["coef"], data, ctx.quick, ev)
