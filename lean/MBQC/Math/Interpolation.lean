/-!
# Bilinear interpolation (DAG node `lemma.bilinear_interpolation`)

If f(i, j) has a constant step in j for every i, and a constant step in i for
every j, then f is bilinear and its four corner values determine it:

  f(i, j) = f00 + j (f01 − f00) + i (f10 − f00) + i j (f11 − f10 − f01 + f00).

This turns "the fit is exact on held-out points" into a proof, given the two
structural facts (design doc, idea 3).
-/

set_option grind.warning false

namespace MBQC.Math

theorem bilinear_interpolation (f : Nat → Nat → Int)
    (hk : ∀ i j, f i (j+1) - f i j = f i 1 - f i 0)
    (hn : ∀ i j, f (i+1) j - f i j = f 1 j - f 0 j) (i j : Nat) :
    f i j = f 0 0 + j*(f 0 1 - f 0 0) + i*(f 1 0 - f 0 0) + i*j*(f 1 1 - f 1 0 - f 0 1 + f 0 0) := by
  have row : ∀ i j, f i j = f i 0 + j*(f i 1 - f i 0) := by
    intro i j
    induction j with
    | zero => simp
    | succ j ih => have := hk i j; push_cast; grind
  have col : ∀ i j, f i j = f 0 j + i*(f 1 j - f 0 j) := by
    intro i j
    induction i with
    | zero => simp
    | succ i ih => have := hn i j; push_cast; grind
  rw [row i j, col i 0, col i 1]
  grind

/-- The hypotheses can be met (f = 0). -/
theorem bilinear_interpolation_nonvacuous :
    ∃ f : Nat → Nat → Int, (∀ i j, f i (j+1) - f i j = f i 1 - f i 0) ∧
      (∀ i j, f (i+1) j - f i j = f 1 j - f 0 j) :=
  ⟨fun _ _ => 0, by simp, by simp⟩

end MBQC.Math
