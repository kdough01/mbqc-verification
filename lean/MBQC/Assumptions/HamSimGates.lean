import MBQC.Defs.GraphixGates

/-!
# Assumptions about the transpiled Hamiltonian-simulation circuits (gate counts)

Lean cannot run Qiskit, so what Qiskit's transpiler (level 1) produces enters as
axioms about an opaque `circuit n k : List Gate` per method: how many gates of
each kind it has, as an exact bilinear function of n and the repetition
parameter k, and that no CZ of its J/CZ stream cancels an edge. One namespace
per DAG assumption node (`assume.hamsim.<method>_unopt_gates`); `#print axioms`
lists them on every theorem that uses them.

Evidence: the scaling checks on those nodes count each gate kind of the real
transpiled circuits on the whole grid, held-out points included, and check
that no CZ cancels. The coefficients here are generated from those counts
(tests/test_hamsim_lean.py checks that both agree).
-/

namespace MBQC.Assumptions.HamSim.Trotter2UnoptGates
open MBQC.Defs

/-- The second-order Trotter circuit for n data qubits and parameter r, after Qiskit's transpiler, as Graphix gates. -/
opaque circuit : Nat → Nat → List Gate

axiom count_cnot : ∀ n r : Nat, 2 ≤ n → 1 ≤ r →
    (countKind .cnot (circuit n r) : Int) = 0
axiom count_cz : ∀ n r : Nat, 2 ≤ n → 1 ≤ r →
    (countKind .cz (circuit n r) : Int) = 0
axiom count_rzz : ∀ n r : Nat, 2 ≤ n → 1 ≤ r →
    (countKind .rzz (circuit n r) : Int) = 1*(n : Int)*r - 1*r
axiom count_ccx : ∀ n r : Nat, 2 ≤ n → 1 ≤ r →
    (countKind .ccx (circuit n r) : Int) = 0
axiom count_h : ∀ n r : Nat, 2 ≤ n → 1 ≤ r →
    (countKind .h (circuit n r) : Int) = 0
axiom count_x : ∀ n r : Nat, 2 ≤ n → 1 ≤ r →
    (countKind .x (circuit n r) : Int) = 0
axiom count_rx : ∀ n r : Nat, 2 ≤ n → 1 ≤ r →
    (countKind .rx (circuit n r) : Int) = 1*(n : Int)
axiom count_ry : ∀ n r : Nat, 2 ≤ n → 1 ≤ r →
    (countKind .ry (circuit n r) : Int) = 0
axiom count_rz : ∀ n r : Nat, 2 ≤ n → 1 ≤ r →
    (countKind .rz (circuit n r) : Int) = 0
axiom count_u : ∀ n r : Nat, 2 ≤ n → 1 ≤ r →
    (countKind .u (circuit n r) : Int) = 1*(n : Int)*r

/-- No CZ of the stream cancels an edge (so E = #J + #CZ). -/
axiom no_cancel : ∀ n r : Nat, 2 ≤ n → 1 ≤ r → NoCancel (n) (gatesToJcz (circuit n r))

end MBQC.Assumptions.HamSim.Trotter2UnoptGates

namespace MBQC.Assumptions.HamSim.QsvtUnoptGates
open MBQC.Defs

/-- The QSVT circuit for n data qubits and parameter D, after Qiskit's transpiler, as Graphix gates. -/
opaque circuit : Nat → Nat → List Gate

axiom count_cnot : ∀ n D : Nat, 2 ≤ n → 3 ≤ D → D % 2 = 1 →
    (countKind .cnot (circuit n D) : Int) = 75*(n : Int)*D - 36*D - 3*n + 12
axiom count_cz : ∀ n D : Nat, 2 ≤ n → 3 ≤ D → D % 2 = 1 →
    (countKind .cz (circuit n D) : Int) = 9*(n : Int)*D - 6*D - 9*n + 6
axiom count_rzz : ∀ n D : Nat, 2 ≤ n → 3 ≤ D → D % 2 = 1 →
    (countKind .rzz (circuit n D) : Int) = 3*D + 3
axiom count_ccx : ∀ n D : Nat, 2 ≤ n → 3 ≤ D → D % 2 = 1 →
    (countKind .ccx (circuit n D) : Int) = 12*(n : Int) - 4
axiom count_h : ∀ n D : Nat, 2 ≤ n → 3 ≤ D → D % 2 = 1 →
    (countKind .h (circuit n D) : Int) = 4*(n : Int) + 3
axiom count_x : ∀ n D : Nat, 2 ≤ n → 3 ≤ D → D % 2 = 1 →
    (countKind .x (circuit n D) : Int) = 1
axiom count_rx : ∀ n D : Nat, 2 ≤ n → 3 ≤ D → D % 2 = 1 →
    (countKind .rx (circuit n D) : Int) = 0
axiom count_ry : ∀ n D : Nat, 2 ≤ n → 3 ≤ D → D % 2 = 1 →
    (countKind .ry (circuit n D) : Int) = 36*(n : Int)*D - 24*D
axiom count_rz : ∀ n D : Nat, 2 ≤ n → 3 ≤ D → D % 2 = 1 →
    (countKind .rz (circuit n D) : Int) = 3*D + 3
axiom count_u : ∀ n D : Nat, 2 ≤ n → 3 ≤ D → D % 2 = 1 →
    (countKind .u (circuit n D) : Int) = 9

/-- No CZ of the stream cancels an edge (so E = #J + #CZ). -/
axiom no_cancel : ∀ n D : Nat, 2 ≤ n → 3 ≤ D → D % 2 = 1 → NoCancel (4*n+1) (gatesToJcz (circuit n D))

end MBQC.Assumptions.HamSim.QsvtUnoptGates

namespace MBQC.Assumptions.HamSim.GqspUnoptGates
open MBQC.Defs

/-- The GQSP circuit for n data qubits and parameter d, after Qiskit's transpiler, as Graphix gates. -/
opaque circuit : Nat → Nat → List Gate

axiom count_cnot : ∀ n d : Nat, 2 ≤ n → 1 ≤ d →
    (countKind .cnot (circuit n d) : Int) = 48*(n : Int)*d - 34*d + 2
axiom count_cz : ∀ n d : Nat, 2 ≤ n → 1 ≤ d →
    (countKind .cz (circuit n d) : Int) = 2*d
axiom count_rzz : ∀ n d : Nat, 2 ≤ n → 1 ≤ d →
    (countKind .rzz (circuit n d) : Int) = 0
axiom count_ccx : ∀ n d : Nat, 2 ≤ n → 1 ≤ d →
    (countKind .ccx (circuit n d) : Int) = 8*(n : Int)*d - 4*d
axiom count_h : ∀ n d : Nat, 2 ≤ n → 1 ≤ d →
    (countKind .h (circuit n d) : Int) = 4*(n : Int)*d
axiom count_x : ∀ n d : Nat, 2 ≤ n → 1 ≤ d →
    (countKind .x (circuit n d) : Int) = 1
axiom count_rx : ∀ n d : Nat, 2 ≤ n → 1 ≤ d →
    (countKind .rx (circuit n d) : Int) = 0
axiom count_ry : ∀ n d : Nat, 2 ≤ n → 1 ≤ d →
    (countKind .ry (circuit n d) : Int) = 24*(n : Int)*d - 16*d
axiom count_rz : ∀ n d : Nat, 2 ≤ n → 1 ≤ d →
    (countKind .rz (circuit n d) : Int) = 0
axiom count_u : ∀ n d : Nat, 2 ≤ n → 1 ≤ d →
    (countKind .u (circuit n d) : Int) = 2*d + 1

/-- No CZ of the stream cancels an edge (so E = #J + #CZ). -/
axiom no_cancel : ∀ n d : Nat, 2 ≤ n → 1 ≤ d → NoCancel (4*n) (gatesToJcz (circuit n d))

end MBQC.Assumptions.HamSim.GqspUnoptGates
