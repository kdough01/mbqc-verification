/-!
# Assumptions about the compiled Hamiltonian-simulation patterns

Lean cannot run Qiskit or Graphix, so facts about their output enter as
explicit axioms. Each block is one DAG assumption node; `#print axioms` on any
theorem that uses them lists them, so the trust boundary stays visible.

`QsvtOptN` (DAG node `assume.hamsim.qsvt_opt_N`): the vertex count of the
optimized QSVT pattern (Pauli measurements removed) for n data qubits and QSVT
degree D (odd). Evidence: exact on every grid point incl. held-out ones
(verification/truth/scaling), and the per-degree blocks of the circuit are
concatenated copies, which is why the count is affine in D.
-/

namespace MBQC.Assumptions.HamSim.QsvtOptN

/-- N(n, D) of the optimized QSVT pattern, as Graphix 0.4.1 counts it. -/
opaque count : Nat → Nat → Int

/-- Affine in the degree: each extra pair of degrees (D → D + 2) adds the same number of vertices. -/
axiom affine_D : ∀ n j, count n (2*(j+1)+3) - count n (2*j+3) = count n 5 - count n 3

/-- Affine in n: each extra data qubit adds the same number of vertices, for every degree. -/
axiom affine_n : ∀ n D, 2 ≤ n → count (n+1) D - count n D = count 3 D - count 2 D

/-- The four corner counts, from compiling the circuits. -/
axiom at_2_3 : count 2 3 = 326
axiom at_2_5 : count 2 5 = 434
axiom at_3_3 : count 3 3 = 526
axiom at_3_5 : count 3 5 = 706

end MBQC.Assumptions.HamSim.QsvtOptN
