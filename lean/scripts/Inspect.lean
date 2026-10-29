import MBQC
import Lean

/-!
Inspect declarations for the Lean checks (verification/truth/lean and friends).

    MBQC_INSPECT=<request file> lake env lean scripts/Inspect.lean

Request lines: `decl <Name>` to inspect a declaration, `stop <Prefix>` to name a
DAG node's declarations (a name or namespace). For each `decl`, prints one JSON
line with: kind, module, axioms (`#print axioms`), the constants its statement
uses with their modules (vocabulary check), the `stop` prefixes its proof
reaches through MBQC code (edge extraction), its Prop hypotheses, and, for an
`∃ …, A ∧ B` statement, its conjuncts (non-vacuity check).
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

#eval show CommandElabM Unit from do
  let some path ← IO.getEnv "MBQC_INSPECT" | throwError "set MBQC_INSPECT to a request file"
  let lines := ((← IO.FS.readFile path).splitOn "\n").map String.trim |>.filter (· ≠ "")
  let decls := lines.filterMap fun l => if l.startsWith "decl " then some (l.drop 5).trim.toName else none
  let stops := lines.filterMap fun l => if l.startsWith "stop " then some (l.drop 5).trim.toName else none
  for n in decls do
    IO.println (← inspectOne stops n).compress
