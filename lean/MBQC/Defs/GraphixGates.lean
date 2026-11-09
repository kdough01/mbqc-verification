import MBQC.Defs.JCZ

/-!
# Graphix's gate-by-gate J/CZ decomposition (vetted vocabulary)

Graphix 0.4.1 turns each gate of a circuit into J(α) and CZ instructions
(`graphix.transpiler.instructions_to_jcz`); `compileJcz` (JCZ.lean) then builds
the pattern from the stream. `Gate.jcz` reimplements the decomposition for the
gates the Hamiltonian-simulation circuits use after Qiskit's transpiler, without
the angles (they do not change any count). The differential check compares it
with Graphix's instruction for instruction (`gates: true`).

`NoCancel` says no CZ of a stream removes an edge (the toggle in `compileJcz`
only adds); then E = #J + #CZ (Transfer/Gates.lean).
-/

namespace MBQC.Defs

inductive GateKind where
  | cnot | cz | rzz | ccx | h | x | rx | ry | rz | u
  deriving Repr, DecidableEq

inductive Gate where
  | cnot (c t : Nat)
  | cz (a b : Nat)
  | rzz (a b : Nat)
  | ccx (a b c : Nat)
  | h (q : Nat)
  | x (q : Nat)
  | rx (q : Nat)
  | ry (q : Nat)
  | rz (q : Nat)
  | u (q : Nat)
  deriving Repr, DecidableEq

def Gate.kind : Gate → GateKind
  | .cnot .. => .cnot | .cz .. => .cz | .rzz .. => .rzz | .ccx .. => .ccx | .h _ => .h
  | .x _ => .x | .rx _ => .rx | .ry _ => .ry | .rz _ => .rz | .u _ => .u

/-- Graphix 0.4.1 `instructions_to_jcz`, angles and global phases dropped. -/
def Gate.jcz : Gate → List Instr
  | .cnot c t => [.J t, .CZ c t, .J t]
  | .cz a b => [.CZ a b]
  | .rzz a b => [.J b, .CZ a b, .J b, .J b, .J b, .J b, .CZ a b, .J b]
  | .ccx a b c =>
    [.J c, .J c, .CZ b c, .J c, .J c, .J c, .J c, .CZ a c, .J c, .J c, .J c, .J c, .CZ b c, .J c, .J c, .J c,
     .J c, .CZ a c, .J c, .J b, .J b, .J c, .J c, .J b, .CZ a b, .J b, .J c, .J b, .J b, .J b, .CZ a b, .J b,
     .J a, .J a, .J b, .J b]
  | .h q => [.J q]
  | .x q => [.J q, .J q]
  | .rx q => [.J q, .J q]
  | .ry q => [.J q, .J q, .J q, .J q]
  | .rz q => [.J q, .J q]
  | .u q => [.J q, .J q, .J q, .J q]

/-- The J/CZ stream of a circuit given as a list of gates. -/
def gatesToJcz (gs : List Gate) : List Instr := gs.flatMap Gate.jcz

/-- How many gates of a kind a circuit has. -/
def countKind (k : GateKind) (gs : List Gate) : Nat := (gs.filter (fun g => g.kind = k)).length

/-- Starting from `g`, no CZ of `prog` toggles off an edge that is already there. -/
def noCancelFrom : JczGraph → List Instr → Prop
  | _, [] => True
  | g, .J q :: rest => noCancelFrom (g.step (.J q)) rest
  | g, .CZ a b :: rest =>
    edgeKey (g.current.getD a 0) (g.current.getD b 0) ∉ g.edges ∧ noCancelFrom (g.step (.CZ a b)) rest

/-- No CZ of the stream cancels an edge when compiled on `width` qubits. -/
def NoCancel (width : Nat) (prog : List Instr) : Prop := noCancelFrom (JczGraph.init width) prog

end MBQC.Defs
