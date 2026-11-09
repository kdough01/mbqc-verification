/-!
# Assumptions about the Graphix-optimized Hamiltonian-simulation patterns

Same shape as `QsvtOptN` (lean/MBQC/Assumptions/HamSim.lean): a count of the
Graphix-optimized pattern (standardized, Pauli measurements removed) that Lean
cannot compute enters as an opaque function with three kinds of axioms: affine
in the repetition parameter, affine in n, and its four corner values. One
namespace per DAG assumption node `assume.hamsim.<method>_opt_<N|M>`. Evidence:
each node's scaling check, exact on the whole grid including held-out points.
Generated from the nodes' formulas (tests/test_hamsim_lean.py checks they agree).
-/

namespace MBQC.Assumptions.HamSim.Trotter2OptN

/-- N(n, r) of the Graphix-optimized second-order Trotter pattern, as Graphix 0.4.1 counts it. -/
opaque count : Nat → Nat → Int

/-- Affine in r: each extra Trotter step adds the same amount. -/
axiom affine_k : ∀ n j, count n (j+1+1) - count n (j+1) = count n 2 - count n 1

/-- Affine in n: each extra data qubit adds the same amount, for every value of the parameter. -/
axiom affine_n : ∀ n r, 2 ≤ n → count (n+1) r - count n r = count 3 r - count 2 r

/-- The four corner counts, from compiling the circuits. -/
axiom at_2_1 : count 2 1 = 11
axiom at_2_2 : count 2 2 = 16
axiom at_3_1 : count 3 1 = 17
axiom at_3_2 : count 3 2 = 25

end MBQC.Assumptions.HamSim.Trotter2OptN

namespace MBQC.Assumptions.HamSim.Trotter2OptM

/-- M(n, r) of the Graphix-optimized second-order Trotter pattern, as Graphix 0.4.1 counts it. -/
opaque count : Nat → Nat → Int

/-- Affine in r: each extra Trotter step adds the same amount. -/
axiom affine_k : ∀ n j, count n (j+1+1) - count n (j+1) = count n 2 - count n 1

/-- Affine in n: each extra data qubit adds the same amount, for every value of the parameter. -/
axiom affine_n : ∀ n r, 2 ≤ n → count (n+1) r - count n r = count 3 r - count 2 r

/-- The four corner counts, from compiling the circuits. -/
axiom at_2_1 : count 2 1 = 9
axiom at_2_2 : count 2 2 = 14
axiom at_3_1 : count 3 1 = 14
axiom at_3_2 : count 3 2 = 22

end MBQC.Assumptions.HamSim.Trotter2OptM

namespace MBQC.Assumptions.HamSim.GqspOptN

/-- N(n, d) of the Graphix-optimized GQSP pattern, as Graphix 0.4.1 counts it. -/
opaque count : Nat → Nat → Int

/-- Affine in d: each extra degree adds the same amount. -/
axiom affine_k : ∀ n j, count n (j+1+1) - count n (j+1) = count n 2 - count n 1

/-- Affine in n: each extra data qubit adds the same amount, for every value of the parameter. -/
axiom affine_n : ∀ n d, 2 ≤ n → count (n+1) d - count n d = count 3 d - count 2 d

/-- The four corner counts, from compiling the circuits. -/
axiom at_2_1 : count 2 1 = 138
axiom at_2_2 : count 2 2 = 258
axiom at_3_1 : count 3 1 = 226
axiom at_3_2 : count 3 2 = 426

end MBQC.Assumptions.HamSim.GqspOptN

namespace MBQC.Assumptions.HamSim.GqspOptM

/-- M(n, d) of the Graphix-optimized GQSP pattern, as Graphix 0.4.1 counts it. -/
opaque count : Nat → Nat → Int

/-- Affine in d: each extra degree adds the same amount. -/
axiom affine_k : ∀ n j, count n (j+1+1) - count n (j+1) = count n 2 - count n 1

/-- Affine in n: each extra data qubit adds the same amount, for every value of the parameter. -/
axiom affine_n : ∀ n d, 2 ≤ n → count (n+1) d - count n d = count 3 d - count 2 d

/-- The four corner counts, from compiling the circuits. -/
axiom at_2_1 : count 2 1 = 130
axiom at_2_2 : count 2 2 = 250
axiom at_3_1 : count 3 1 = 214
axiom at_3_2 : count 3 2 = 414

end MBQC.Assumptions.HamSim.GqspOptM

namespace MBQC.Assumptions.HamSim.QsvtOptM

/-- M(n, D) of the Graphix-optimized QSVT pattern, as Graphix 0.4.1 counts it. -/
opaque count : Nat → Nat → Int

/-- Affine in D: each extra pair of degrees adds the same amount. -/
axiom affine_k : ∀ n j, count n (2*(j+1)+3) - count n (2*j+3) = count n 5 - count n 3

/-- Affine in n: each extra data qubit adds the same amount, for every value of the parameter. -/
axiom affine_n : ∀ n D, 2 ≤ n → count (n+1) D - count n D = count 3 D - count 2 D

/-- The four corner counts, from compiling the circuits. -/
axiom at_2_3 : count 2 3 = 317
axiom at_2_5 : count 2 5 = 425
axiom at_3_3 : count 3 3 = 513
axiom at_3_5 : count 3 5 = 693

end MBQC.Assumptions.HamSim.QsvtOptM
