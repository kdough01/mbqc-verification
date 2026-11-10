import MBQC
import Lean

/-!
Inspect declarations for the Lean checks (checks/lean, checks/_shared/lean.py and friends).

    MBQC_INSPECT=<request file> lake env lean scripts/Inspect.lean

Request lines: `decl <Name>` to inspect a declaration, `stop <Prefix>` to name a
DAG node's declarations (a name or namespace), `same <A> <B>` to compare two proofs of one
statement (lean_proof check), `iff <A> <B> <P>` to check that P proves stmt(A) ↔ stmt(B) without using
the proofs of A or B (equivalence check). For each `decl`, prints one JSON
line with: kind, module, axioms (`#print axioms`), the constants its statement
uses with their modules (vocabulary check), the `stop` prefixes its proof
reaches through MBQC code (edge extraction), its Prop hypotheses, and, for an
`∃ …, A ∧ B` statement, its conjuncts (non-vacuity check). For each `same`, prints whether B's
statement is syntactically A's, whether it is definitionally equal to A's, and whether the two proof terms
are identical. For each `iff`, prints whether P's type is exactly `type(A) ↔ type(B)` (and whether it is
definitionally), P's axioms, and which of A, B its proof reaches through MBQC code.
-/

open Lean Meta Elab Command

def moduleOf (env : Environment) (n : Name) : String :=
  match env.getModuleIdxFor? n with
  | some idx => (env.header.moduleNames[idx.toNat]!).toString
  | none => ""

def usedBy (ci : ConstantInfo) : Array Name :=
  ci.type.getUsedConstants ++ ((ci.value? (allowOpaque := true)).map Expr.getUsedConstants |>.getD #[])

partial def walk (env : Environment) (stops : List Name) (todo : List Name) (seen found : NameSet) : NameSet :=
  match todo with
  | [] => found
  | n :: rest =>
    if seen.contains n then walk env stops rest seen found
    else
      let seen := seen.insert n
      match stops.find? (·.isPrefixOf n) with
      | some p => walk env stops rest seen (found.insert p)
      | none =>
        if !(moduleOf env n).startsWith "MBQC" then walk env stops rest seen found
        else match env.find? n with
          | some ci => walk env stops ((usedBy ci).toList ++ rest) seen found
          | none => walk env stops rest seen found

partial def splitAnd (e : Expr) : List Expr :=
  if e.isAppOfArity ``And 2 then splitAnd e.appFn!.appArg! ++ splitAnd e.appArg! else [e]

partial def openExists (e : Expr) (k : Expr → MetaM (List String)) : MetaM (List String) := do
  if e.isAppOfArity ``Exists 2 then
    match e.appArg! with
    | .lam n t b _ => withLocalDeclD n t fun x => openExists (b.instantiate1 x) k
    | _ => k e
  else k e

def kindOf : ConstantInfo → String
  | .thmInfo _ => "theorem" | .defnInfo _ => "def" | .axiomInfo _ => "axiom"
  | .opaqueInfo _ => "opaque" | .inductInfo _ => "inductive" | .ctorInfo _ => "constructor"
  | .recInfo _ => "recursor" | .quotInfo _ => "quot"

def inspectOne (stops : List Name) (n : Name) : CommandElabM Json := do
  let env ← getEnv
  let some ci := env.find? n | return Json.mkObj [("name", toJson n.toString), ("missing", toJson true)]
  let axioms ← collectAxioms n
  let typeConsts := ci.type.getUsedConstants.map fun c =>
    Json.mkObj [("name", toJson c.toString), ("module", toJson (moduleOf env c))]
  -- a declaration does not depend on its own node
  let own := stops.filter (·.isPrefixOf n)
  let deps := walk env (stops.filter (fun p => !own.contains p)) (usedBy ci).toList {} {}
  let (hyps, conj) ← liftTermElabM do
    let hyps ← forallTelescopeReducing ci.type fun xs _ => do
      let mut out : List String := []
      for x in xs do
        let t ← inferType x
        if ← isProp t then out := out ++ [toString (← ppExpr t)]
      return out
    let conj ← openExists ci.type fun body => (splitAnd body).mapM fun e => do return toString (← ppExpr e)
    return (hyps, conj)
  return Json.mkObj [
    ("name", toJson n.toString), ("kind", toJson (kindOf ci)), ("module", toJson (moduleOf env n)),
    ("axioms", toJson (axioms.map Name.toString)), ("type_consts", Json.arr typeConsts),
    ("node_deps", toJson (deps.toList.map Name.toString)),
    ("hypotheses", toJson hyps), ("conjuncts", toJson conj)]

/-- Is `b` a proof of the statement `a` proves? Universe parameters are matched by position. -/
def sameOne (a b : Name) : CommandElabM Json := do
  let env ← getEnv
  let base := [("same", toJson #[a.toString, b.toString])]
  let some ca := env.find? a | return Json.mkObj (base ++ [("missing", toJson a.toString)])
  let some cb := env.find? b | return Json.mkObj (base ++ [("missing", toJson b.toString)])
  if ca.levelParams.length != cb.levelParams.length then
    return Json.mkObj (base ++ [("type_equal", toJson false), ("defeq", toJson false),
      ("value_equal", toJson false), ("note", toJson "different universe parameters")])
  let us := ca.levelParams.map Level.param
  let tb := cb.type.instantiateLevelParams cb.levelParams us
  let va := ca.value? (allowOpaque := true)
  let vb := (cb.value? (allowOpaque := true)).map (·.instantiateLevelParams cb.levelParams us)
  let defeq ← liftTermElabM do
    try Meta.isDefEq ca.type tb catch _ => pure false
  return Json.mkObj (base ++ [("type_equal", toJson (ca.type == tb)), ("defeq", toJson defeq),
    ("value_equal", toJson (va.isSome && va == vb))])

/-- Does `p` prove `type(a) ↔ type(b)`, and without reaching the proofs of `a` or `b`? -/
def iffOne (a b p : Name) : CommandElabM Json := do
  let env ← getEnv
  let base := [("iff", toJson #[a.toString, b.toString, p.toString])]
  let some ca := env.find? a | return Json.mkObj (base ++ [("missing", toJson a.toString)])
  let some cb := env.find? b | return Json.mkObj (base ++ [("missing", toJson b.toString)])
  let some cp := env.find? p | return Json.mkObj (base ++ [("missing", toJson p.toString)])
  if !(ca.levelParams.isEmpty && cb.levelParams.isEmpty && cp.levelParams.isEmpty) then
    return Json.mkObj (base ++ [("type_equal", toJson false), ("defeq", toJson false),
      ("note", toJson "universe-polymorphic statements are not supported")])
  let expected := mkApp2 (mkConst ``Iff) ca.type cb.type
  let defeq ← liftTermElabM do
    try Meta.isDefEq cp.type expected catch _ => pure false
  let axioms ← collectAxioms p
  let reaches := walk env [a, b] (usedBy cp).toList {} {}
  return Json.mkObj (base ++ [("type_equal", toJson (cp.type == expected)), ("defeq", toJson defeq),
    ("kind", toJson (kindOf cp)), ("axioms", toJson (axioms.map Name.toString)),
    ("uses", toJson (reaches.toList.map Name.toString))])

#eval show CommandElabM Unit from do
  let some path ← IO.getEnv "MBQC_INSPECT" | throwError "set MBQC_INSPECT to a request file"
  let lines := ((← IO.FS.readFile path).splitOn "\n").map String.trim |>.filter (· ≠ "")
  let decls := lines.filterMap fun l => if l.startsWith "decl " then some (l.drop 5).trim.toName else none
  let stops := lines.filterMap fun l => if l.startsWith "stop " then some (l.drop 5).trim.toName else none
  let sames := lines.filterMap fun l =>
    if l.startsWith "same " then
      match ((l.drop 5).trim.splitOn " ").filter (· ≠ "") with
      | [a, b] => some (a.toName, b.toName)
      | _ => none
    else none
  for n in decls do
    IO.println (← inspectOne stops n).compress
  for (a, b) in sames do
    IO.println (← sameOne a b).compress
  let iffs := lines.filterMap fun l =>
    if l.startsWith "iff " then
      match ((l.drop 4).trim.splitOn " ").filter (· ≠ "") with
      | [a, b, p] => some (a.toName, b.toName, p.toName)
      | _ => none
    else none
  for (a, b, p) in iffs do
    IO.println (← iffOne a b p).compress
