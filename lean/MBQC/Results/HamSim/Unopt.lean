import MBQC.Transfer.Gates
import MBQC.Assumptions.HamSimGates

/-!
# Layer B: unoptimized pattern counts from the circuits (DAG nodes `hamsim.B.<method>.<N|M|E>.unopt`)

For each method the pattern Graphix builds gate by gate is `compileJcz width
(gatesToJcz circuit)`. `compile_counts` and `compile_edges` turn #J and #CZ into
N, M and E; `countJ_gates` and `countCZ_gates` turn those into gate counts by
Graphix's per-gate costs; the gate-count assumptions finish the formulas.
-/

set_option grind.warning false

namespace MBQC.Results.HamSim
open MBQC.Defs MBQC.Transfer MBQC.Assumptions.HamSim

/-- `hamsim.B.trotter2.N.unopt`: N = (10*n - 6)*r + 3*n. -/
theorem trotter2_vertices_unopt (n r : Nat) (hn : 2 ≤ n) (hr : 1 ≤ r) :
    ((compileJcz (n) (gatesToJcz (Trotter2UnoptGates.circuit n r))).numVertices : Int) = (10*(n : Int) - 6)*r + 3*n := by
  rw [(compile_counts _ _).1, countJ_gates]
  push_cast
  rw [Trotter2UnoptGates.count_cnot n r hn hr, Trotter2UnoptGates.count_rzz n r hn hr, Trotter2UnoptGates.count_ccx n r hn hr, Trotter2UnoptGates.count_h n r hn hr, Trotter2UnoptGates.count_x n r hn hr, Trotter2UnoptGates.count_rx n r hn hr, Trotter2UnoptGates.count_ry n r hn hr, Trotter2UnoptGates.count_rz n r hn hr, Trotter2UnoptGates.count_u n r hn hr]
  grind

/-- `hamsim.B.trotter2.M.unopt`: M = (10*n - 6)*r + 2*n. -/
theorem trotter2_measurements_unopt (n r : Nat) (hn : 2 ≤ n) (hr : 1 ≤ r) :
    ((compileJcz (n) (gatesToJcz (Trotter2UnoptGates.circuit n r))).numMeasurements : Int) = (10*(n : Int) - 6)*r + 2*n := by
  rw [(compile_counts _ _).2.1, countJ_gates]
  push_cast
  rw [Trotter2UnoptGates.count_cnot n r hn hr, Trotter2UnoptGates.count_rzz n r hn hr, Trotter2UnoptGates.count_ccx n r hn hr, Trotter2UnoptGates.count_h n r hn hr, Trotter2UnoptGates.count_x n r hn hr, Trotter2UnoptGates.count_rx n r hn hr, Trotter2UnoptGates.count_ry n r hn hr, Trotter2UnoptGates.count_rz n r hn hr, Trotter2UnoptGates.count_u n r hn hr]
  grind

/-- `hamsim.B.trotter2.E.unopt`: E = (12*n - 8)*r + 2*n. -/
theorem trotter2_edges_unopt (n r : Nat) (hn : 2 ≤ n) (hr : 1 ≤ r) :
    ((compileJcz (n) (gatesToJcz (Trotter2UnoptGates.circuit n r))).numEdges : Int) = (12*(n : Int) - 8)*r + 2*n := by
  rw [compile_edges _ _ (Trotter2UnoptGates.no_cancel n r hn hr), countJ_gates, countCZ_gates]
  push_cast
  rw [Trotter2UnoptGates.count_cnot n r hn hr, Trotter2UnoptGates.count_rzz n r hn hr, Trotter2UnoptGates.count_ccx n r hn hr, Trotter2UnoptGates.count_h n r hn hr, Trotter2UnoptGates.count_x n r hn hr, Trotter2UnoptGates.count_rx n r hn hr, Trotter2UnoptGates.count_ry n r hn hr, Trotter2UnoptGates.count_rz n r hn hr, Trotter2UnoptGates.count_u n r hn hr, Trotter2UnoptGates.count_cz n r hn hr]
  grind

theorem trotter2_unopt_nonvacuous : ∃ n r : Nat, 2 ≤ n ∧ 1 ≤ r := ⟨2, 1, by omega, by omega⟩

/-- `hamsim.B.qsvt.N.unopt`: N = (294*n - 144)*D + 362*n - 30. -/
theorem qsvt_vertices_unopt (n D : Nat) (hn : 2 ≤ n) (hD : 3 ≤ D) (hodd : D % 2 = 1) :
    ((compileJcz (4*n+1) (gatesToJcz (QsvtUnoptGates.circuit n D))).numVertices : Int) = (294*(n : Int) - 144)*D + 362*n - 30 := by
  rw [(compile_counts _ _).1, countJ_gates]
  push_cast
  rw [QsvtUnoptGates.count_cnot n D hn hD hodd, QsvtUnoptGates.count_rzz n D hn hD hodd, QsvtUnoptGates.count_ccx n D hn hD hodd, QsvtUnoptGates.count_h n D hn hD hodd, QsvtUnoptGates.count_x n D hn hD hodd, QsvtUnoptGates.count_rx n D hn hD hodd, QsvtUnoptGates.count_ry n D hn hD hodd, QsvtUnoptGates.count_rz n D hn hD hodd, QsvtUnoptGates.count_u n D hn hD hodd]
  grind

/-- `hamsim.B.qsvt.M.unopt`: M = (294*n - 144)*D + 358*n - 31. -/
theorem qsvt_measurements_unopt (n D : Nat) (hn : 2 ≤ n) (hD : 3 ≤ D) (hodd : D % 2 = 1) :
    ((compileJcz (4*n+1) (gatesToJcz (QsvtUnoptGates.circuit n D))).numMeasurements : Int) = (294*(n : Int) - 144)*D + 358*n - 31 := by
  rw [(compile_counts _ _).2.1, countJ_gates]
  push_cast
  rw [QsvtUnoptGates.count_cnot n D hn hD hodd, QsvtUnoptGates.count_rzz n D hn hD hodd, QsvtUnoptGates.count_ccx n D hn hD hodd, QsvtUnoptGates.count_h n D hn hD hodd, QsvtUnoptGates.count_x n D hn hD hodd, QsvtUnoptGates.count_rx n D hn hD hodd, QsvtUnoptGates.count_ry n D hn hD hodd, QsvtUnoptGates.count_rz n D hn hD hodd, QsvtUnoptGates.count_u n D hn hD hodd]
  grind

/-- `hamsim.B.qsvt.E.unopt`: E = (378*n - 180)*D + 418*n - 31. -/
theorem qsvt_edges_unopt (n D : Nat) (hn : 2 ≤ n) (hD : 3 ≤ D) (hodd : D % 2 = 1) :
    ((compileJcz (4*n+1) (gatesToJcz (QsvtUnoptGates.circuit n D))).numEdges : Int) = (378*(n : Int) - 180)*D + 418*n - 31 := by
  rw [compile_edges _ _ (QsvtUnoptGates.no_cancel n D hn hD hodd), countJ_gates, countCZ_gates]
  push_cast
  rw [QsvtUnoptGates.count_cnot n D hn hD hodd, QsvtUnoptGates.count_rzz n D hn hD hodd, QsvtUnoptGates.count_ccx n D hn hD hodd, QsvtUnoptGates.count_h n D hn hD hodd, QsvtUnoptGates.count_x n D hn hD hodd, QsvtUnoptGates.count_rx n D hn hD hodd, QsvtUnoptGates.count_ry n D hn hD hodd, QsvtUnoptGates.count_rz n D hn hD hodd, QsvtUnoptGates.count_u n D hn hD hodd, QsvtUnoptGates.count_cz n D hn hD hodd]
  grind

theorem qsvt_unopt_nonvacuous : ∃ n D : Nat, 2 ≤ n ∧ 3 ≤ D ∧ D % 2 = 1 := ⟨2, 3, by omega, by omega, by decide⟩

/-- `hamsim.B.gqsp.N.unopt`: N = (436*n - 244)*d + 4*n + 10. -/
theorem gqsp_vertices_unopt (n d : Nat) (hn : 2 ≤ n) (hd : 1 ≤ d) :
    ((compileJcz (4*n) (gatesToJcz (GqspUnoptGates.circuit n d))).numVertices : Int) = (436*(n : Int) - 244)*d + 4*n + 10 := by
  rw [(compile_counts _ _).1, countJ_gates]
  push_cast
  rw [GqspUnoptGates.count_cnot n d hn hd, GqspUnoptGates.count_rzz n d hn hd, GqspUnoptGates.count_ccx n d hn hd, GqspUnoptGates.count_h n d hn hd, GqspUnoptGates.count_x n d hn hd, GqspUnoptGates.count_rx n d hn hd, GqspUnoptGates.count_ry n d hn hd, GqspUnoptGates.count_rz n d hn hd, GqspUnoptGates.count_u n d hn hd]
  grind

/-- `hamsim.B.gqsp.M.unopt`: M = (436*n - 244)*d + 10. -/
theorem gqsp_measurements_unopt (n d : Nat) (hn : 2 ≤ n) (hd : 1 ≤ d) :
    ((compileJcz (4*n) (gatesToJcz (GqspUnoptGates.circuit n d))).numMeasurements : Int) = (436*(n : Int) - 244)*d + 10 := by
  rw [(compile_counts _ _).2.1, countJ_gates]
  push_cast
  rw [GqspUnoptGates.count_cnot n d hn hd, GqspUnoptGates.count_rzz n d hn hd, GqspUnoptGates.count_ccx n d hn hd, GqspUnoptGates.count_h n d hn hd, GqspUnoptGates.count_x n d hn hd, GqspUnoptGates.count_rx n d hn hd, GqspUnoptGates.count_ry n d hn hd, GqspUnoptGates.count_rz n d hn hd, GqspUnoptGates.count_u n d hn hd]
  grind

/-- `hamsim.B.gqsp.E.unopt`: E = (532*n - 300)*d + 12. -/
theorem gqsp_edges_unopt (n d : Nat) (hn : 2 ≤ n) (hd : 1 ≤ d) :
    ((compileJcz (4*n) (gatesToJcz (GqspUnoptGates.circuit n d))).numEdges : Int) = (532*(n : Int) - 300)*d + 12 := by
  rw [compile_edges _ _ (GqspUnoptGates.no_cancel n d hn hd), countJ_gates, countCZ_gates]
  push_cast
  rw [GqspUnoptGates.count_cnot n d hn hd, GqspUnoptGates.count_rzz n d hn hd, GqspUnoptGates.count_ccx n d hn hd, GqspUnoptGates.count_h n d hn hd, GqspUnoptGates.count_x n d hn hd, GqspUnoptGates.count_rx n d hn hd, GqspUnoptGates.count_ry n d hn hd, GqspUnoptGates.count_rz n d hn hd, GqspUnoptGates.count_u n d hn hd, GqspUnoptGates.count_cz n d hn hd]
  grind

theorem gqsp_unopt_nonvacuous : ∃ n d : Nat, 2 ≤ n ∧ 1 ≤ d := ⟨2, 1, by omega, by omega⟩

end MBQC.Results.HamSim
