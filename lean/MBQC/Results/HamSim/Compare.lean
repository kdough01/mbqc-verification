import MBQC.Results.HamSim.Unopt
import MBQC.Results.HamSim.Opt
import MBQC.Results.HamSim.QSVT

/-!
# Layer C: comparing QSVT and GQSP (DAG nodes `hamsim.C.ours.d_ge_g.*` and `hamsim.C.big_o`)

`*_disproof`: the slide's conclusion "for all n ≥ 2 and D ≥ d, QSVT costs more than
GQSP", restated with our compiler's counts, is false: Lean evaluates both Layer B
formulas at one instance where QSVT costs less. The DAG nodes record this as a
refutation (lean check with `refutes: true`), modulo the Layer B assumptions.

`big_o_unopt`: if both degrees are at most c·(1 + X) (X standing for
α|t| + log(1/ε), as the Jacobi–Anger truncation gives), every unoptimized count
of both methods is at most 800·n·c·(1 + X): the same Big-O, different prefactors.
-/

set_option grind.warning false

namespace MBQC.Results.HamSim
open MBQC.Defs MBQC.Assumptions.HamSim

/-- `hamsim.C.ours.d_ge_g.N.unopt` is false: at n = 2, D = 5, d = 5 QSVT has fewer vertices. -/
theorem qsvt_gqsp_vertices_unopt_disproof :
    ¬ ∀ n D d : Nat, 2 ≤ n → 3 ≤ D → D % 2 = 1 → 1 ≤ d → d ≤ D →
      (compileJcz (4*n) (gatesToJcz (GqspUnoptGates.circuit n d))).numVertices < (compileJcz (4*n+1) (gatesToJcz (QsvtUnoptGates.circuit n D))).numVertices := by
  intro h
  have h1 := h 2 5 5 (by decide) (by decide) (by decide) (by decide) (by decide)
  have q := qsvt_vertices_unopt 2 5 (by decide) (by decide) (by decide)
  have g := gqsp_vertices_unopt 2 5 (by decide) (by decide)
  push_cast at q g h1
  omega

/-- `hamsim.C.ours.d_ge_g.M.unopt` is false: at n = 2, D = 5, d = 5 QSVT has fewer measurements. -/
theorem qsvt_gqsp_measurements_unopt_disproof :
    ¬ ∀ n D d : Nat, 2 ≤ n → 3 ≤ D → D % 2 = 1 → 1 ≤ d → d ≤ D →
      (compileJcz (4*n) (gatesToJcz (GqspUnoptGates.circuit n d))).numMeasurements < (compileJcz (4*n+1) (gatesToJcz (QsvtUnoptGates.circuit n D))).numMeasurements := by
  intro h
  have h1 := h 2 5 5 (by decide) (by decide) (by decide) (by decide) (by decide)
  have q := qsvt_measurements_unopt 2 5 (by decide) (by decide) (by decide)
  have g := gqsp_measurements_unopt 2 5 (by decide) (by decide)
  push_cast at q g h1
  omega

/-- `hamsim.C.ours.d_ge_g.E.unopt` is false: at n = 2, D = 5, d = 5 QSVT has fewer edges. -/
theorem qsvt_gqsp_edges_unopt_disproof :
    ¬ ∀ n D d : Nat, 2 ≤ n → 3 ≤ D → D % 2 = 1 → 1 ≤ d → d ≤ D →
      (compileJcz (4*n) (gatesToJcz (GqspUnoptGates.circuit n d))).numEdges < (compileJcz (4*n+1) (gatesToJcz (QsvtUnoptGates.circuit n D))).numEdges := by
  intro h
  have h1 := h 2 5 5 (by decide) (by decide) (by decide) (by decide) (by decide)
  have q := qsvt_edges_unopt 2 5 (by decide) (by decide) (by decide)
  have g := gqsp_edges_unopt 2 5 (by decide) (by decide)
  push_cast at q g h1
  omega

/-- `hamsim.C.ours.d_ge_g.N.opt` is false: at n = 2, D = 3, d = 3 QSVT has fewer vertices. -/
theorem qsvt_gqsp_vertices_opt_disproof :
    ¬ ∀ n D d : Nat, 2 ≤ n → 3 ≤ D → D % 2 = 1 → 1 ≤ d → d ≤ D →
      GqspOptN.count n d < QsvtOptN.count n D := by
  intro h
  have h1 := h 2 3 3 (by decide) (by decide) (by decide) (by decide) (by decide)
  have q := qsvt_vertices_opt 2 3 (by decide) (by decide) (by decide)
  have g := gqsp_vertices_opt 2 3 (by decide) (by decide)
  push_cast at q g h1
  omega

/-- `hamsim.C.ours.d_ge_g.M.opt` is false: at n = 2, D = 3, d = 3 QSVT has fewer measurements. -/
theorem qsvt_gqsp_measurements_opt_disproof :
    ¬ ∀ n D d : Nat, 2 ≤ n → 3 ≤ D → D % 2 = 1 → 1 ≤ d → d ≤ D →
      GqspOptM.count n d < QsvtOptM.count n D := by
  intro h
  have h1 := h 2 3 3 (by decide) (by decide) (by decide) (by decide) (by decide)
  have q := qsvt_measurements_opt 2 3 (by decide) (by decide) (by decide)
  have g := gqsp_measurements_opt 2 3 (by decide) (by decide)
  push_cast at q g h1
  omega

/-- `hamsim.C.big_o`: with both degrees at most c·(1 + X), every unoptimized count is at most 800·n·c·(1 + X). -/
theorem big_o_unopt (c X n D d : Nat) (hn : 2 ≤ n) (hD : 3 ≤ D) (hodd : D % 2 = 1) (hd : 1 ≤ d)
    (hDc : D ≤ c * (1 + X)) (hdc : d ≤ c * (1 + X)) :
    ((compileJcz (4*n+1) (gatesToJcz (QsvtUnoptGates.circuit n D))).numVertices : Int) ≤ 800 * ((n * (c * (1 + X)) : Nat) : Int) ∧
    ((compileJcz (4*n+1) (gatesToJcz (QsvtUnoptGates.circuit n D))).numMeasurements : Int) ≤ 800 * ((n * (c * (1 + X)) : Nat) : Int) ∧
    ((compileJcz (4*n+1) (gatesToJcz (QsvtUnoptGates.circuit n D))).numEdges : Int) ≤ 800 * ((n * (c * (1 + X)) : Nat) : Int) ∧
    ((compileJcz (4*n) (gatesToJcz (GqspUnoptGates.circuit n d))).numVertices : Int) ≤ 800 * ((n * (c * (1 + X)) : Nat) : Int) ∧
    ((compileJcz (4*n) (gatesToJcz (GqspUnoptGates.circuit n d))).numMeasurements : Int) ≤ 800 * ((n * (c * (1 + X)) : Nat) : Int) ∧
    ((compileJcz (4*n) (gatesToJcz (GqspUnoptGates.circuit n d))).numEdges : Int) ≤ 800 * ((n * (c * (1 + X)) : Nat) : Int) := by
  generalize hK : c * (1 + X) = K at *
  have hnD : n * D ≤ n * K := Nat.mul_le_mul_left n hDc
  have hnd : n * d ≤ n * K := Nat.mul_le_mul_left n hdc
  have hnK : n ≤ n * K := Nat.le_mul_of_pos_right n (by omega)
  have eD : ∀ a b : Int, (a * (n : Int) - b) * D = a * ((n * D : Nat) : Int) - b * D := by intro a b; push_cast; grind
  have ed : ∀ a b : Int, (a * (n : Int) - b) * d = a * ((n * d : Nat) : Int) - b * d := by intro a b; push_cast; grind
  refine ⟨?_, ?_, ?_, ?_, ?_, ?_⟩
  · rw [qsvt_vertices_unopt n D (by omega) (by omega) (by omega)]
    rw [eD]
    omega
  · rw [qsvt_measurements_unopt n D (by omega) (by omega) (by omega)]
    rw [eD]
    omega
  · rw [qsvt_edges_unopt n D (by omega) (by omega) (by omega)]
    rw [eD]
    omega
  · rw [gqsp_vertices_unopt n d (by omega) (by omega)]
    rw [ed]
    omega
  · rw [gqsp_measurements_unopt n d (by omega) (by omega)]
    rw [ed]
    omega
  · rw [gqsp_edges_unopt n d (by omega) (by omega)]
    rw [ed]
    omega

theorem big_o_unopt_nonvacuous : ∃ c X n D d : Nat, 2 ≤ n ∧ 3 ≤ D ∧ D % 2 = 1 ∧ 1 ≤ d ∧ D ≤ c * (1 + X) ∧ d ≤ c * (1 + X) :=
  ⟨3, 0, 2, 3, 1, by decide⟩

end MBQC.Results.HamSim
