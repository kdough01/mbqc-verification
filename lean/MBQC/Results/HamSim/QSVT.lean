import MBQC.Math.Interpolation
import MBQC.Assumptions.HamSim

/-!
# Layer B: optimized QSVT vertex count (DAG node `hamsim.B.qsvt.N.opt`)

N(n, D) = (36n − 18)D + 92n − 20 for all n ≥ 2 and odd D ≥ 3, from the
interpolation lemma and the `QsvtOptN` assumptions (affine in each argument,
four corner counts). `#print axioms` lists exactly those assumptions.
-/

set_option grind.warning false

namespace MBQC.Results.HamSim
open MBQC.Assumptions.HamSim

theorem qsvt_vertices_opt (n D : Nat) (hn : 2 ≤ n) (hD : 3 ≤ D) (hodd : D % 2 = 1) :
    QsvtOptN.count n D = (36*(n : Int) - 18)*D + 92*n - 20 := by
  let f : Nat → Nat → Int := fun i j => QsvtOptN.count (i+2) (2*j+3)
  have hk : ∀ i j, f i (j+1) - f i j = f i 1 - f i 0 := fun i j => QsvtOptN.affine_D (i+2) j
  have hn' : ∀ i j, f (i+1) j - f i j = f 1 j - f 0 j := by
    intro i j
    have := QsvtOptN.affine_n (i+2) (2*j+3) (by omega)
    simpa [f, Nat.add_right_comm i 1 2] using this
  obtain ⟨i, rfl⟩ : ∃ i, n = i + 2 := ⟨n - 2, by omega⟩
  obtain ⟨j, rfl⟩ : ∃ j, D = 2*j + 3 := ⟨(D - 3) / 2, by omega⟩
  have h := MBQC.Math.bilinear_interpolation f hk hn' i j
  have c00 : f 0 0 = 326 := QsvtOptN.at_2_3
  have c01 : f 0 1 = 434 := QsvtOptN.at_2_5
  have c10 : f 1 0 = 526 := QsvtOptN.at_3_3
  have c11 : f 1 1 = 706 := QsvtOptN.at_3_5
  show f i j = _
  rw [h, c00, c01, c10, c11]
  push_cast
  grind

theorem qsvt_vertices_opt_nonvacuous : ∃ n D : Nat, 2 ≤ n ∧ 3 ≤ D ∧ D % 2 = 1 := ⟨2, 3, by decide⟩

end MBQC.Results.HamSim
