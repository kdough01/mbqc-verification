import MBQC.Math.Interpolation
import MBQC.Assumptions.HamSimOpt

/-!
# Layer B: Graphix-optimized counts (DAG nodes `hamsim.B.<method>.<N|M>.opt`)

Each formula follows from the interpolation lemma and its node's assumptions
(affine in each argument, four corner counts), as `qsvt_vertices_opt` does.
-/

set_option grind.warning false

namespace MBQC.Results.HamSim
open MBQC.Assumptions.HamSim

/-- `hamsim.B.trotter2.N.opt`: N = (3*n - 1)*r + 3*n. -/
theorem trotter2_vertices_opt (n r : Nat) (hn : 2 ≤ n) (hr : 1 ≤ r) :
    Trotter2OptN.count n r = (3*(n : Int) - 1)*r + 3*n := by
  let f : Nat → Nat → Int := fun i j => Trotter2OptN.count (i+2) (j+1)
  have hk : ∀ i j, f i (j+1) - f i j = f i 1 - f i 0 := fun i j => Trotter2OptN.affine_k (i+2) j
  have hn' : ∀ i j, f (i+1) j - f i j = f 1 j - f 0 j := by
    intro i j
    have := Trotter2OptN.affine_n (i+2) (j+1) (by omega)
    simpa [f, Nat.add_right_comm i 1 2] using this
  obtain ⟨i, rfl⟩ : ∃ i, n = i + 2 := ⟨n - 2, by omega⟩
  obtain ⟨j, rfl⟩ : ∃ j, r = j + 1 := ⟨r - 1, by omega⟩
  have h := MBQC.Math.bilinear_interpolation f hk hn' i j
  have c00 : f 0 0 = 11 := Trotter2OptN.at_2_1
  have c01 : f 0 1 = 16 := Trotter2OptN.at_2_2
  have c10 : f 1 0 = 17 := Trotter2OptN.at_3_1
  have c11 : f 1 1 = 25 := Trotter2OptN.at_3_2
  show f i j = _
  rw [h, c00, c01, c10, c11]
  push_cast
  grind

theorem trotter2_vertices_opt_nonvacuous : ∃ n r : Nat, 2 ≤ n ∧ 1 ≤ r := ⟨2, 1, by decide⟩

/-- `hamsim.B.trotter2.M.opt`: M = (3*n - 1)*r + 2*n. -/
theorem trotter2_measurements_opt (n r : Nat) (hn : 2 ≤ n) (hr : 1 ≤ r) :
    Trotter2OptM.count n r = (3*(n : Int) - 1)*r + 2*n := by
  let f : Nat → Nat → Int := fun i j => Trotter2OptM.count (i+2) (j+1)
  have hk : ∀ i j, f i (j+1) - f i j = f i 1 - f i 0 := fun i j => Trotter2OptM.affine_k (i+2) j
  have hn' : ∀ i j, f (i+1) j - f i j = f 1 j - f 0 j := by
    intro i j
    have := Trotter2OptM.affine_n (i+2) (j+1) (by omega)
    simpa [f, Nat.add_right_comm i 1 2] using this
  obtain ⟨i, rfl⟩ : ∃ i, n = i + 2 := ⟨n - 2, by omega⟩
  obtain ⟨j, rfl⟩ : ∃ j, r = j + 1 := ⟨r - 1, by omega⟩
  have h := MBQC.Math.bilinear_interpolation f hk hn' i j
  have c00 : f 0 0 = 9 := Trotter2OptM.at_2_1
  have c01 : f 0 1 = 14 := Trotter2OptM.at_2_2
  have c10 : f 1 0 = 14 := Trotter2OptM.at_3_1
  have c11 : f 1 1 = 22 := Trotter2OptM.at_3_2
  show f i j = _
  rw [h, c00, c01, c10, c11]
  push_cast
  grind

theorem trotter2_measurements_opt_nonvacuous : ∃ n r : Nat, 2 ≤ n ∧ 1 ≤ r := ⟨2, 1, by decide⟩

/-- `hamsim.B.gqsp.N.opt`: N = (80*n - 40)*d + 8*n + 2. -/
theorem gqsp_vertices_opt (n d : Nat) (hn : 2 ≤ n) (hd : 1 ≤ d) :
    GqspOptN.count n d = (80*(n : Int) - 40)*d + 8*n + 2 := by
  let f : Nat → Nat → Int := fun i j => GqspOptN.count (i+2) (j+1)
  have hk : ∀ i j, f i (j+1) - f i j = f i 1 - f i 0 := fun i j => GqspOptN.affine_k (i+2) j
  have hn' : ∀ i j, f (i+1) j - f i j = f 1 j - f 0 j := by
    intro i j
    have := GqspOptN.affine_n (i+2) (j+1) (by omega)
    simpa [f, Nat.add_right_comm i 1 2] using this
  obtain ⟨i, rfl⟩ : ∃ i, n = i + 2 := ⟨n - 2, by omega⟩
  obtain ⟨j, rfl⟩ : ∃ j, d = j + 1 := ⟨d - 1, by omega⟩
  have h := MBQC.Math.bilinear_interpolation f hk hn' i j
  have c00 : f 0 0 = 138 := GqspOptN.at_2_1
  have c01 : f 0 1 = 258 := GqspOptN.at_2_2
  have c10 : f 1 0 = 226 := GqspOptN.at_3_1
  have c11 : f 1 1 = 426 := GqspOptN.at_3_2
  show f i j = _
  rw [h, c00, c01, c10, c11]
  push_cast
  grind

theorem gqsp_vertices_opt_nonvacuous : ∃ n d : Nat, 2 ≤ n ∧ 1 ≤ d := ⟨2, 1, by decide⟩

/-- `hamsim.B.gqsp.M.opt`: M = (80*n - 40)*d + 4*n + 2. -/
theorem gqsp_measurements_opt (n d : Nat) (hn : 2 ≤ n) (hd : 1 ≤ d) :
    GqspOptM.count n d = (80*(n : Int) - 40)*d + 4*n + 2 := by
  let f : Nat → Nat → Int := fun i j => GqspOptM.count (i+2) (j+1)
  have hk : ∀ i j, f i (j+1) - f i j = f i 1 - f i 0 := fun i j => GqspOptM.affine_k (i+2) j
  have hn' : ∀ i j, f (i+1) j - f i j = f 1 j - f 0 j := by
    intro i j
    have := GqspOptM.affine_n (i+2) (j+1) (by omega)
    simpa [f, Nat.add_right_comm i 1 2] using this
  obtain ⟨i, rfl⟩ : ∃ i, n = i + 2 := ⟨n - 2, by omega⟩
  obtain ⟨j, rfl⟩ : ∃ j, d = j + 1 := ⟨d - 1, by omega⟩
  have h := MBQC.Math.bilinear_interpolation f hk hn' i j
  have c00 : f 0 0 = 130 := GqspOptM.at_2_1
  have c01 : f 0 1 = 250 := GqspOptM.at_2_2
  have c10 : f 1 0 = 214 := GqspOptM.at_3_1
  have c11 : f 1 1 = 414 := GqspOptM.at_3_2
  show f i j = _
  rw [h, c00, c01, c10, c11]
  push_cast
  grind

theorem gqsp_measurements_opt_nonvacuous : ∃ n d : Nat, 2 ≤ n ∧ 1 ≤ d := ⟨2, 1, by decide⟩

/-- `hamsim.B.qsvt.M.opt`: M = (36*n - 18)*D + 88*n - 21. -/
theorem qsvt_measurements_opt (n D : Nat) (hn : 2 ≤ n) (hD : 3 ≤ D) (hodd : D % 2 = 1) :
    QsvtOptM.count n D = (36*(n : Int) - 18)*D + 88*n - 21 := by
  let f : Nat → Nat → Int := fun i j => QsvtOptM.count (i+2) (2*j+3)
  have hk : ∀ i j, f i (j+1) - f i j = f i 1 - f i 0 := fun i j => QsvtOptM.affine_k (i+2) j
  have hn' : ∀ i j, f (i+1) j - f i j = f 1 j - f 0 j := by
    intro i j
    have := QsvtOptM.affine_n (i+2) (2*j+3) (by omega)
    simpa [f, Nat.add_right_comm i 1 2] using this
  obtain ⟨i, rfl⟩ : ∃ i, n = i + 2 := ⟨n - 2, by omega⟩
  obtain ⟨j, rfl⟩ : ∃ j, D = 2*j + 3 := ⟨(D - 3) / 2, by omega⟩
  have h := MBQC.Math.bilinear_interpolation f hk hn' i j
  have c00 : f 0 0 = 317 := QsvtOptM.at_2_3
  have c01 : f 0 1 = 425 := QsvtOptM.at_2_5
  have c10 : f 1 0 = 513 := QsvtOptM.at_3_3
  have c11 : f 1 1 = 693 := QsvtOptM.at_3_5
  show f i j = _
  rw [h, c00, c01, c10, c11]
  push_cast
  grind

theorem qsvt_measurements_opt_nonvacuous : ∃ n D : Nat, 2 ≤ n ∧ 3 ≤ D ∧ D % 2 = 1 := ⟨2, 3, by decide⟩

end MBQC.Results.HamSim
