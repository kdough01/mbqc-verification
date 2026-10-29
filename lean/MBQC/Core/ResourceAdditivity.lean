import MBQC.Defs.Pattern

/-!
# Core lemma: resource counts add under composition (DAG node `core.resource_additivity`)

N(P2 ∘ P1) = N(P1) + N(P2) − |O1|, E and M add. Stated with the |O1| moved to
the left so it lives in ℕ without truncated subtraction.
-/

namespace MBQC.Core
open MBQC.Defs

theorem resource_additivity (P1 P2 : Pattern) (h : P2.inputs = P1.outputs) :
    numVertices (P1.seq P2) + P1.outputs.length = numVertices P1 + numVertices P2 ∧
    numEdges (P1.seq P2) = numEdges P1 + numEdges P2 ∧
    numMeasurements (P1.seq P2) = numMeasurements P1 + numMeasurements P2 := by
  simp only [numVertices, numEdges, numMeasurements, Pattern.seq, List.filter_append,
    List.length_append, h]
  refine ⟨by omega, ?_, ?_⟩ <;> first | trivial | rfl | omega

/-- The hypotheses of `resource_additivity` can be met. -/
theorem resource_additivity_nonvacuous :
    ∃ P1 P2 : Pattern, P2.inputs = P1.outputs :=
  ⟨⟨[], [], []⟩, ⟨[], [], []⟩, rfl⟩

end MBQC.Core
