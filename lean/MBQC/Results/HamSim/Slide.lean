import MBQC.Defs.HamSimSlide

/-!
# Layer C: the slide's claim "d ≥ g ⇒ QSVT uses more" (DAG nodes `hamsim.C.slide.d_ge_g.*`)

Pure algebra on the slide's formulas, for n ≥ 2 and odd d ≥ g ≥ 3. Each proof
writes the difference as a sum of products of nonnegative factors (the same
positivity certificate verification/truth/symbolic finds with sympy), proves
that identity with `grind`, and closes the linear rest with `omega`.
-/

set_option grind.warning false

namespace MBQC.Results.HamSim
open MBQC.Defs.HamSim

theorem slide_d_ge_g_N (n d g : Int) (hn : 2 ≤ n) (hg : 3 ≤ g) (_hgo : g % 2 = 1) (hd : g ≤ d)
    (_hdo : d % 2 = 1) : slideNG n g < slideNQ n d := by
  have e : slideNQ n d - slideNG n g = (36*n - 18)*(d - g) + (24*n - 12)*(g - 3) + (54*n - 2) := by
    unfold slideNQ slideNG; grind
  have h1 : 0 ≤ (36*n - 18)*(d - g) := Int.mul_nonneg (by omega) (by omega)
  have h2 : 0 ≤ (24*n - 12)*(g - 3) := Int.mul_nonneg (by omega) (by omega)
  omega

theorem slide_d_ge_g_M (n d g : Int) (hn : 2 ≤ n) (hg : 3 ≤ g) (hgo : g % 2 = 1) (hd : g ≤ d)
    (hdo : d % 2 = 1) : slideMG n g < slideMQ n d := by
  have := slide_d_ge_g_N n d g hn hg hgo hd hdo
  unfold slideMG slideMQ; omega

theorem chi_cases (g : Int) : chi g = 0 ∨ chi g = 1 := by
  unfold chi; split <;> simp

theorem eta_nonneg (g : Int) : 0 ≤ eta g := by
  unfold eta; split <;> simp

theorem slide_d_ge_g_E (n d g : Int) (hn : 2 ≤ n) (hg : 3 ≤ g) (_hgo : g % 2 = 1) (hd : g ≤ d)
    (_hdo : d % 2 = 1) : slideEG n g < slideEQ n d := by
  have e : slideEQ n d - slideEG n g
      = (168*n - 102)*(d - g) + (44*n + 14)*(g - 3) + (55*n + 267 + chi g * (n - 3) + eta g) := by
    unfold slideEQ slideEG; grind
  have h1 : 0 ≤ (168*n - 102)*(d - g) := Int.mul_nonneg (by omega) (by omega)
  have h2 : 0 ≤ (44*n + 14)*(g - 3) := Int.mul_nonneg (by omega) (by omega)
  have h3 := eta_nonneg g
  rcases chi_cases g with hc | hc <;> rw [hc] at e <;> omega

/-- The hypotheses of the three theorems can be met. -/
theorem slide_d_ge_g_nonvacuous :
    ∃ n d g : Int, 2 ≤ n ∧ 3 ≤ g ∧ g % 2 = 1 ∧ g ≤ d ∧ d % 2 = 1 :=
  ⟨2, 3, 3, by decide⟩

end MBQC.Results.HamSim
