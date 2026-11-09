import MBQC.Defs.GraphixGates
import MBQC.Transfer.Counts

/-!
# Gate counts to pattern counts (DAG node `transfer.gate_counts`)

For a circuit given as Graphix gates: #J and #CZ of its J/CZ stream are the sums
of each gate kind's cost times how many gates of that kind it has, and when no
CZ cancels an edge the pattern has exactly #J + #CZ edges. With
`compile_counts` this turns gate counts into N, M and E.
-/

namespace MBQC.Transfer
open MBQC.Defs

theorem countJ_append (a b : List Instr) : countJ (a ++ b) = countJ a + countJ b := by
  simp [countJ, List.filter_append]

theorem countCZ_append (a b : List Instr) : countCZ (a ++ b) = countCZ a + countCZ b := by
  simp [countCZ, List.filter_append]

private theorem countKind_cons (k : GateKind) (g : Gate) (gs : List Gate) :
    countKind k (g :: gs) = countKind k gs + (if g.kind = k then 1 else 0) := by
  unfold countKind
  by_cases h : g.kind = k <;> simp [List.filter_cons, h]

/-- #J of a gate list's stream, by gate kind (Graphix's per-gate costs). -/
theorem countJ_gates (gs : List Gate) :
    countJ (gatesToJcz gs) =
      2 * countKind .cnot gs + 6 * countKind .rzz gs + 30 * countKind .ccx gs + countKind .h gs
      + 2 * countKind .x gs + 2 * countKind .rx gs + 4 * countKind .ry gs + 2 * countKind .rz gs
      + 4 * countKind .u gs := by
  induction gs with
  | nil => simp [gatesToJcz, countKind]
  | cons g gs ih =>
    simp only [gatesToJcz, List.flatMap_cons, countJ_append] at ih ⊢
    simp only [countKind_cons]
    cases g <;> simp [Gate.jcz, Gate.kind, countJ, Instr.isJ] at ih ⊢ <;> omega

/-- #CZ of a gate list's stream, by gate kind. -/
theorem countCZ_gates (gs : List Gate) :
    countCZ (gatesToJcz gs) =
      countKind .cnot gs + countKind .cz gs + 2 * countKind .rzz gs + 6 * countKind .ccx gs := by
  induction gs with
  | nil => simp [gatesToJcz, countKind]
  | cons g gs ih =>
    simp only [gatesToJcz, List.flatMap_cons, countCZ_append] at ih ⊢
    simp only [countKind_cons]
    cases g <;> simp [Gate.jcz, Gate.kind, countCZ, Instr.isCZ] at ih ⊢ <;> omega

theorem edges_of_noCancel (prog : List Instr) (g : JczGraph) (h : noCancelFrom g prog) :
    (prog.foldl JczGraph.step g).edges.length = g.edges.length + countJ prog + countCZ prog := by
  induction prog generalizing g with
  | nil => simp
  | cons i rest ih =>
    cases i with
    | J q =>
      have := ih _ h
      simp only [List.foldl_cons, countJ_J, countCZ_J] at this ⊢
      rw [this]; simp [JczGraph.step]; omega
    | CZ a b =>
      obtain ⟨hn, hr⟩ := h
      have := ih _ hr
      simp only [List.foldl_cons, countJ_CZ, countCZ_CZ] at this ⊢
      have hstep : (g.step (.CZ a b)).edges.length = g.edges.length + 1 := by
        simp only [JczGraph.step, toggle, if_neg hn, List.length_cons]
      omega

/-- With no cancelling CZ, the pattern has exactly #J + #CZ edges. -/
theorem compile_edges (width : Nat) (prog : List Instr) (h : NoCancel width prog) :
    (compileJcz width prog).numEdges = countJ prog + countCZ prog := by
  have := edges_of_noCancel prog (JczGraph.init width) h
  simp only [compileJcz, JczGraph.numEdges]
  rw [this]; simp [JczGraph.init]

/-- The node's statement in one piece: gate counts give #J and #CZ, and with no cancelling CZ, #J + #CZ edges. -/
theorem gate_counts (width : Nat) (gs : List Gate) :
    countJ (gatesToJcz gs) = 2*countKind .cnot gs + 6*countKind .rzz gs + 30*countKind .ccx gs + countKind .h gs
      + 2*countKind .x gs + 2*countKind .rx gs + 4*countKind .ry gs + 2*countKind .rz gs + 4*countKind .u gs ∧
    countCZ (gatesToJcz gs) = countKind .cnot gs + countKind .cz gs + 2*countKind .rzz gs + 6*countKind .ccx gs ∧
    (NoCancel width (gatesToJcz gs) →
      (compileJcz width (gatesToJcz gs)).numEdges = countJ (gatesToJcz gs) + countCZ (gatesToJcz gs)) :=
  ⟨countJ_gates gs, countCZ_gates gs, compile_edges width _⟩

end MBQC.Transfer
