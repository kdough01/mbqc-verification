# Verifying the Hamiltonian-simulation slide

This example checks the slide *Hamiltonian simulation: explicit costs and trade-offs* (`docs/img/hamsim_slide.png`).
It rebuilds everything the slide talks about, runs it, and tests each claim. Every claim is a node under
`dag/nodes/hamsim/`. `dagtool status` and the theorem browser (`dagtool render`) show where each one stands.

## Files

| File | What it does |
| --- | --- |
| `src/mbqc_verify/hamsim/circuits.py` | The circuits: Hamiltonian, block encoding, Trotter, QSVT, GQSP |
| `src/mbqc_verify/hamsim/qsp_angles.py` | Classical pre-processing: required degree and rotation angles; every routine checks its own output |
| `src/mbqc_verify/hamsim/analysis.py` | Repetitions for accuracy ε, post-selected operators, MBQC resource counts |
| `src/mbqc_verify/hamsim/slide.py` | The slide's formulas, as data |
| `src/mbqc_verify/compile/qiskit_to_mbqc.py` | Qiskit circuit → Graphix pattern, resource counts, equivalence check |
| `verification/truth/numerical/` | Layer A accuracy; equal-accuracy comparison |
| `verification/truth/translation/` | Compiled pattern equals its circuit, per instance |
| `verification/truth/scaling/` | Layer B formulas against compiled counts |
| `verification/truth/symbolic/`, `verification/truth/refuter/` | Layer C: positivity certificate; counterexample search |
| `lean/MBQC/Results/HamSim/` | Lean proofs of the Layer C claims and of the optimized QSVT vertex formula |
| `experiments/hamsim/run_all.py` | The full printed report; writes `results/hamsim_results.json` |
| `experiments/hamsim/plot_results.py` | Six figures from the results file into `figures/` |

## The result has three layers, checked differently

| Layer | Claim | Comes from | Checked by | DAG nodes |
| --- | --- | --- | --- | --- |
| **A. Accuracy** | "This many repetitions gives error ≤ ε" | Known circuit-model results | Build the circuit, simulate it, compare with the exact e^{−iHt} | `hamsim.A.*` |
| **B. Cost formulas** | "N, E, M = (per-repetition cost) × repetitions + setup" | The MBQC compilation | Compile over a grid of (n, repetitions), count, test the formula on held-out points; Lean for one formula | `hamsim.B.*` |
| **C. Consequences** | Big-O, and "d ≥ g ⇒ GQSP is cheaper" | Algebra on layer B | Positivity certificate (sympy), Lean proof, counterexample search | `hamsim.C.*` |

"Repetitions" means Trotter steps r, the QSVT degree D, or the GQSP degree d.

## Findings

**Layer A: accuracy holds everywhere tested** (empirical).
- All 48 cases are within ε: four methods (Trotter orders 1 and 2, QSVT, GQSP), n = 2 and 3, t = 0.5 and 2,
  ε = 10⁻², 10⁻³, 10⁻⁵.
- The repetition counts come from the theory: Jacobi–Anger truncation for QSVT/GQSP, commutator bounds for Trotter.
  Both enter the DAG as `assume.*` nodes. The bounds are safe but loose: Trotter errors land at 0.25–0.9 ε, QSVT
  errors at 10⁻²–10⁻⁴ ε, and GQSP errors near 0.1 ε.
- Compiled MBQC patterns match their circuits exactly on random input states (`hamsim.compiled_patterns_match`,
  bounded).

**Layer B: the cost formulas are exact, and one is now proved modulo named assumptions.**
- Unoptimized patterns give exact bilinear formulas for N, E and M for all three methods, on held-out points too. Lean's
  independent model of Graphix's J-∧z construction reproduces every one of those counts (differential check).
- Optimized patterns give exact formulas for N and M but **not for E**. Removing Pauli measurements rewires edges
  depending on the graph's details. The scaling check now proves this on the grid: the unique bilinear formula through
  the four corner points misses other points.
- **Our optimized QSVT costs exactly 36n − 18 vertices per degree, the slide's coefficient**, from an independent
  implementation. The setup term differs: 92n − 20 for us, 14n + 23 on the slide. In Lean, N = (36n − 18)D + 92n − 20
  for *all* n ≥ 2 and odd D ≥ 3 follows from the interpolation lemma, given four corner counts and affinity in each
  argument (`assume.hamsim.qsvt_opt_N`).
- **Our GQSP doesn't match.** Ours costs 80n − 40 per degree, the slide's 12n − 6. Each of our GQSP degrees uses two
  *controlled* block-encoding calls, and controlling SELECT costs a Toffoli per term. The slide's GQSP per degree costs
  exactly one *uncontrolled* call in our compiler: 12n − 6 = (36n − 18)/3. **How it avoids that control overhead is the
  main open question to ask the authors.**
- **Optimization trades vertices for memory.** It cuts vertices 3–8× but raises peak live qubits from about 10–22 to
  55–991, so the optimized QSVT/GQSP patterns can't be simulated to check them.

**Layer C: the slide's algebra is right; its conclusion depends on the compiler.**
- The slide's claim (d ≥ g ⇒ QSVT uses more vertices, CZs and measurements, for all n ≥ 2) is **proved in Lean** from
  its formulas, by the same positivity certificate sympy finds.
- With our formulas the same claim is **refuted** (counterexamples recorded in the evidence), except optimized E,
  which has no formula and holds on every grid pair compared.
- That comparison pairs our QSVT D with our GQSP d, which count different things; the convention check flags it. At
  equal accuracy (the comparison that doesn't depend on degree conventions), second-order Trotter is cheapest at low
  precision and QSVT at high precision, and our GQSP is never cheapest. This holds with both the unoptimized and the
  optimized formulas, for n = 4 to 64.

## How each method is built (summary of `circuits.py`)

**Block encoding (shared by QSVT and GQSP).** There is one ancilla per Hamiltonian term (3n − 1 of them), and they
always hold a "one-hot" state: exactly one is |1⟩. PREP spreads amplitude √(c_k/α) over the ancillas using two-qubit
Givens rotations, which never leave the one-hot subspace. SELECT applies one controlled Pauli per term. Then
U = PREP† · SELECT · PREP has H/α in its |e₀⟩ block. The reflection about the "good" ancilla state, which both
algorithms need at every step, is then just a Z on ancilla 0, so the per-call cost is linear in n.

**Trotter.** Split H into its X part (A) and its Z/ZZ part (B). Each part's terms commute, so each layer is exact. The
second-order version merges neighbouring half-steps.

**QSVT.** QSVT makes polynomials of one parity only, so it builds cos(Ht) (D − 1 calls) and sin(Ht) (D calls) on two
branches of an `lcu` qubit and combines them into (cos − i sin)/2. A `sig` qubit takes the real part of each polynomial.
One round of oblivious amplitude amplification turns the 1/2 into ≈ 1, at the price of running everything three times
(3D calls).

**GQSP.** Works on the walk operator W = Z_{a0}·U, whose eigenvalues e^{±iω} satisfy cos ω = −λ/α, so e^{−iHt} is a
Laurent polynomial in W (powers −d…d). Alternating controlled-W with anti-controlled-W† produces it with 2d calls.
Each call is a *controlled* block encoding: only SELECT is controlled, which costs one Toffoli per term.

## Error budget

Each method truncates its series so the truncation error is ≤ 0.1ε, and scales its polynomial by β = 1 − 0.1ε,
because angle finding needs |P| < 1. Layer A checks the total numerically.

## What is ours and what is the slide's

Accuracy (Layer A) is about the algorithms, so our checks apply to the slide directly. Cost formulas (Layer B) are
about **a compiler**: our constants come from our circuits and our Graphix pipeline, not the slide's, so they are not
expected to match. What should match is the *form*: per-repetition cost linear in n, total bilinear in
(n, repetitions).

The "degree" conventions also differ (`mbqc_verify.conventions.Degree`): our D is the number of block-encoding calls in
one QSVT sequence, our d is the Laurent degree of the GQSP polynomial (2d calls), and the slide does not define its
d and g relative to either.
