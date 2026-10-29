import MBQC.Defs.JCZ

/-!
# Transfer, resource part (DAG node `transfer.gate_to_mbqc_counts`)

For the J-∧z construction Graphix uses: the pattern of a J/CZ stream has
width + #J vertices and #J measurements, and at most #J + #CZ edges, with
equality unless a CZ cancels an existing edge. The semantic half of the
transfer theorem (the pattern implements the circuit) is not formalized here.
-/

namespace MBQC.Transfer
open MBQC.Defs

theorem toggle_length_le (e : Nat × Nat) (es : List (Nat × Nat)) :
    (toggle e es).length ≤ es.length + 1 := by
  unfold toggle
  split
  · have := List.length_erase_le (l := es) (a := e); omega
  · simp

@[simp] theorem countJ_nil : countJ [] = 0 := rfl
@[simp] theorem countCZ_nil : countCZ [] = 0 := rfl
@[simp] theorem countJ_J (q : Nat) (rest : List Instr) : countJ (.J q :: rest) = countJ rest + 1 := by
  simp [countJ, List.filter_cons, Instr.isJ]
@[simp] theorem countCZ_J (q : Nat) (rest : List Instr) : countCZ (.J q :: rest) = countCZ rest := by
  simp [countCZ, List.filter_cons, Instr.isCZ]
@[simp] theorem countJ_CZ (a b : Nat) (rest : List Instr) : countJ (.CZ a b :: rest) = countJ rest := by
  simp [countJ, List.filter_cons, Instr.isJ]
@[simp] theorem countCZ_CZ (a b : Nat) (rest : List Instr) :
    countCZ (.CZ a b :: rest) = countCZ rest + 1 := by
  simp [countCZ, List.filter_cons, Instr.isCZ]

theorem foldl_counts (prog : List Instr) (g : JczGraph) :
    (prog.foldl JczGraph.step g).next = g.next + countJ prog ∧
    (prog.foldl JczGraph.step g).measured = g.measured + countJ prog ∧
    (prog.foldl JczGraph.step g).edges.length ≤ g.edges.length + countJ prog + countCZ prog := by
  induction prog generalizing g with
  | nil => simp
  | cons i rest ih =>
    obtain ⟨h1, h2, h3⟩ := ih (JczGraph.step g i)
    cases i with
    | J q =>
      simp only [List.foldl_cons, JczGraph.step, List.length_cons] at h1 h2 h3 ⊢
      simp only [countJ_J, countCZ_J]
      exact ⟨by omega, by omega, by omega⟩
    | CZ a b =>
      have ht := toggle_length_le (edgeKey (g.current.getD a 0) (g.current.getD b 0)) g.edges
      simp only [List.foldl_cons, JczGraph.step] at h1 h2 h3 ⊢
      simp only [countJ_CZ, countCZ_CZ]
      exact ⟨by omega, by omega, by omega⟩

/-- Vertices, measurements and edges of the pattern Graphix builds from a J/CZ stream. -/
theorem compile_counts (width : Nat) (prog : List Instr) :
    (compileJcz width prog).numVertices = width + countJ prog ∧
    (compileJcz width prog).numMeasurements = countJ prog ∧
    (compileJcz width prog).numEdges ≤ countJ prog + countCZ prog := by
  obtain ⟨h1, h2, h3⟩ := foldl_counts prog (JczGraph.init width)
  simp only [compileJcz, JczGraph.numVertices, JczGraph.numMeasurements, JczGraph.numEdges]
  simp only [JczGraph.init, List.length_nil] at h1 h2 h3 ⊢
  exact ⟨by omega, by omega, by omega⟩

end MBQC.Transfer
