/-!
# Graphix's J-∧z construction (vetted vocabulary)

Graphix 0.4.1 compiles a circuit by decomposing every gate into J(α) and CZ
instructions (`graphix.transpiler.instructions_to_jcz`) and then building an
open graph (`Circuit.transpile_to_causalflow`):

* `J q`: add a new vertex, join it to qubit `q`'s current vertex, measure the old
  vertex, and make the new one current for `q`;
* `CZ a b`: toggle the edge between the current vertices of `a` and `b`
  (Graphix removes the edge if it exists, otherwise adds it).

This file reimplements that construction independently, so its counts can be
compared with Graphix's (`verification/faithfulness/differential`). The angle
of J does not affect any count and is omitted.
-/

namespace MBQC.Defs

inductive Instr where
  | J (target : Nat)
  | CZ (a b : Nat)
  deriving Repr, DecidableEq

/-- The open graph under construction. -/
structure JczGraph where
  /-- number of vertices so far (vertex ids are 0 .. next-1) -/
  next : Nat
  /-- current vertex of each circuit qubit -/
  current : List Nat
  /-- undirected edges, each stored as (min, max) -/
  edges : List (Nat × Nat)
  /-- measured vertices so far -/
  measured : Nat

def edgeKey (a b : Nat) : Nat × Nat := if a ≤ b then (a, b) else (b, a)

def toggle (e : Nat × Nat) (es : List (Nat × Nat)) : List (Nat × Nat) :=
  if e ∈ es then es.erase e else e :: es

def JczGraph.init (width : Nat) : JczGraph :=
  { next := width, current := List.range width, edges := [], measured := 0 }

def JczGraph.step (g : JczGraph) : Instr → JczGraph
  | .J q =>
    { next := g.next + 1
      current := g.current.set q g.next
      edges := edgeKey (g.current.getD q 0) g.next :: g.edges
      measured := g.measured + 1 }
  | .CZ a b =>
    { g with edges := toggle (edgeKey (g.current.getD a 0) (g.current.getD b 0)) g.edges }

/-- The graph Graphix builds for a circuit of `width` qubits with J/CZ stream `prog`. -/
def compileJcz (width : Nat) (prog : List Instr) : JczGraph :=
  prog.foldl JczGraph.step (JczGraph.init width)

def JczGraph.numVertices (g : JczGraph) : Nat := g.next
def JczGraph.numEdges (g : JczGraph) : Nat := g.edges.length
def JczGraph.numMeasurements (g : JczGraph) : Nat := g.measured

def Instr.isJ : Instr → Bool | .J _ => true | _ => false
def Instr.isCZ : Instr → Bool | .CZ .. => true | _ => false
def countJ (prog : List Instr) : Nat := (prog.filter Instr.isJ).length
def countCZ (prog : List Instr) : Nat := (prog.filter Instr.isCZ).length

end MBQC.Defs
