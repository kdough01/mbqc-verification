/-!
# Measurement patterns (vetted vocabulary)

A pattern in the measurement calculus (Danos, Kashefi & Panangaden 2007): a
command sequence over qubits with designated inputs and outputs. This file
fixes the *syntax* and the resource counts N, E, M (DAG nodes `def.pattern`,
`def.resource_counts`). The semantics (the map a pattern implements) is not
formalized yet.
-/

namespace MBQC.Defs

/-- Measurement plane. -/
inductive Plane where
  | XY | YZ | XZ
  deriving Repr, DecidableEq

/-- One command. Angles are in units of π (the Graphix convention). -/
inductive Cmd where
  /-- prepare qubit `i` in |+⟩ -/
  | N (i : Nat)
  /-- CZ between qubits `i` and `j` -/
  | E (i j : Nat)
  /-- measure `i` in `plane` at `angle`·π, with X- and Z-signal domains -/
  | M (i : Nat) (plane : Plane) (angle : Float) (sDomain tDomain : List Nat)
  /-- Pauli X on `i`, conditioned on the parity of the outcomes in `domain` -/
  | X (i : Nat) (domain : List Nat)
  /-- Pauli Z on `i`, conditioned on the parity of the outcomes in `domain` -/
  | Z (i : Nat) (domain : List Nat)

def Cmd.isN : Cmd → Bool | .N _ => true | _ => false
def Cmd.isE : Cmd → Bool | .E _ _ => true | _ => false
def Cmd.isM : Cmd → Bool | .M .. => true | _ => false

/-- A pattern: inputs, outputs, and its commands in execution order. -/
structure Pattern where
  inputs : List Nat
  outputs : List Nat
  cmds : List Cmd

/-- N(P): vertices of the pattern's graph = inputs + prepared qubits. -/
def numVertices (P : Pattern) : Nat := P.inputs.length + (P.cmds.filter Cmd.isN).length

/-- E(P): number of CZ (E) commands. -/
def numEdges (P : Pattern) : Nat := (P.cmds.filter Cmd.isE).length

/-- M(P): number of measurements. -/
def numMeasurements (P : Pattern) : Nat := (P.cmds.filter Cmd.isM).length

/-- Sequential composition `P2 ∘ P1`: run `P1`, then `P2` on its outputs.
Well formed when `P2.inputs = P1.outputs` (same qubit names) and `P2` prepares
only fresh qubits. -/
def Pattern.seq (P1 P2 : Pattern) : Pattern :=
  { inputs := P1.inputs, outputs := P2.outputs, cmds := P1.cmds ++ P2.cmds }

end MBQC.Defs
