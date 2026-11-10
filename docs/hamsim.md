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
| `src/mbqc_verify/compilers/graphix.py` | Qiskit circuit → Graphix pattern, resource counts, equivalence check |
| `src/mbqc_verify/compilers/__init__.py` | One interface for every compiler compared (Graphix unoptimized, Graphix-optimized, Cabaliser, …) |
| `src/mbqc_verify/compilers/cabaliser.py`, `experiments/compilers/run.py` | Cabaliser in the pinned RRE environment; records its counts and translation runs |
| `checks/numerical/` | Layer A accuracy; equal-accuracy comparison |
| `checks/translation/` | Compiled pattern (or Cabaliser graph) equals its circuit, per instance |
| `checks/scaling/` | Layer B formulas, gate counts, widths and no-cancel against compiled circuits |
| `checks/differential/` | Lean's models of Graphix against Graphix itself |
| `checks/symbolic/`, `checks/refuter/`, `checks/lean/disproof.py` | Layer C: positivity certificate; counterexample search; disproofs in Lean |
| `lean/MBQC/Results/HamSim/` | Lean proofs: the slide's Layer C claims, all 9 unoptimized and 6 Graphix-optimized formulas (modulo named assumptions), the disproofs of the slide's claim with our formulas, and the Big-O bound |
| `lean/MBQC/Defs/GraphixGates.lean`, `lean/MBQC/Assumptions/HamSim*.lean` | Graphix's per-gate J/CZ decompositions; what Lean takes on trust about the transpiled circuits and optimized patterns |
| `experiments/hamsim/run_all.py` | The full printed report; writes `results/hamsim_results.json` |
| `experiments/hamsim/plot_results.py` | Six figures from the results file into `figures/` |

## The result has three layers, checked differently

| Layer | Claim | Comes from | Checked by | DAG nodes |
| --- | --- | --- | --- | --- |
| **A. Accuracy** | "This many repetitions gives error ≤ ε" | Known circuit-model results | Build the circuit, simulate it, compare with the exact e^{−iHt} | `hamsim.A.*` |
| **B. Cost formulas** | "N, E, M = (per-repetition cost) × repetitions + setup" | The MBQC compilation | Lean, from the circuits' gate counts (unoptimized) or four corners and affinity (optimized); the same formulas compiled over a grid, tested on held-out points, per compiler | `hamsim.B.*` |
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

**Layer B: the cost formulas are exact, and every one with a formula is proved in Lean modulo named assumptions.**
- Unoptimized patterns give exact bilinear formulas for N, E and M for all three methods, on held-out points too. Lean's
  independent model of Graphix's J-∧z construction reproduces every one of those counts (differential check).
- **All nine unoptimized formulas are proved in Lean** for all n and repetitions (`MBQC.Results.HamSim.*_unopt`). Lean
  models Graphix's per-gate J/CZ decomposition (`def.graphix_gates`; token-for-token equal to Graphix's on every gate
  kind and on whole circuits) and proves how gate counts become N, M and E (`transfer.gate_counts`). What it takes on
  trust is what Qiskit's transpiler outputs: exact bilinear counts of each gate kind and that no CZ cancels an edge
  (`assume.hamsim.<method>_unopt_gates`), each checked by counting the real circuits on the grid.
- Graphix-optimized patterns give exact formulas for N and M but **not for E**. Removing Pauli measurements rewires edges
  depending on the graph's details. The scaling check now proves this on the grid: the unique bilinear formula through
  the four corner points misses other points.
- **Our optimized QSVT costs exactly 36n − 18 vertices per degree, the slide's coefficient**, from an independent
  implementation. The setup term differs: 92n − 20 for us, 14n + 23 on the slide. In Lean, N = (36n − 18)D + 92n − 20
  for *all* n ≥ 2 and odd D ≥ 3 follows from the interpolation lemma, given four corner counts and affinity in each
  argument (`assume.hamsim.qsvt_opt_N`). The same argument now proves the other four Graphix-optimized formulas
  (Trotter N and M, GQSP N and M, QSVT M).
- **Other compilers.** Each formula is a claim about one compiler (the `compiler` convention), and variants test it on
  others (`hamsim.B.<method>.<N|M|E>.cabaliser`). With Cabaliser, N and M follow the Graphix-optimized formulas exactly for
  Trotter and QSVT, and for GQSP with exactly one more vertex; Cabaliser's Trotter E is bilinear, (4n − 2)r + 2n, where
  Graphix-optimized E is not; QSVT and GQSP E have no formula under either. Cabaliser's compiled graphs reproduce
  their circuits on every input for the Trotter instances small enough to simulate (`hamsim.B.cabaliser_graphs_match`).
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
  which has no formula and holds on every grid pair compared. Lean **disproves** it too, from the Layer B formulas:
  at n = 2, D = d = 5 (unoptimized) and n = 2, D = d = 3 (optimized), QSVT costs less.
- **Same Big-O** (`hamsim.C.big_o`, Lean): if both degrees are at most c(1 + X), every unoptimized count of QSVT and
  GQSP is at most 800 · n · c(1 + X). That the degree needed is O(1 + α|t| + log(1/ε)) is the Jacobi–Anger part,
  which enters as that hypothesis.
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
