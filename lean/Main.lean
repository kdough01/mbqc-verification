import MBQC.Defs.JCZ
import MBQC.Defs.GraphixGates

/-!
`mbqc_counts`: one J/CZ stream per input line, `width tok tok ...` with tokens
`J:q` and `C:a:b`; prints `N E M` for each line. Used by the differential check.

A line `G gate gate ...` with gates `cnot:c:t`, `cz:a:b`, `rzz:c:t`, `ccx:a:b:t`,
`h:q`, `x:q`, `rx:q`, `ry:q`, `rz:q`, `u:q` instead prints the J/CZ stream that
`gatesToJcz` gives (tokens `J:q` and `C:a:b`), for comparison with Graphix's
`instructions_to_jcz`.
-/

open MBQC.Defs

def parseLine (line : String) : Option (Nat × List Instr) := do
  let toks := (line.splitOn " ").filter (· ≠ "")
  match toks with
  | [] => none
  | w :: rest =>
    let width ← w.toNat?
    let instrs ← rest.mapM fun t =>
      match t.splitOn ":" with
      | ["J", q] => q.toNat?.map Instr.J
      | ["C", a, b] => do return Instr.CZ (← a.toNat?) (← b.toNat?)
      | _ => none
    return (width, instrs)

def parseGate (t : String) : Option Gate := do
  match t.splitOn ":" with
  | ["cnot", c, q] => return .cnot (← c.toNat?) (← q.toNat?)
  | ["cz", a, b] => return .cz (← a.toNat?) (← b.toNat?)
  | ["rzz", a, b] => return .rzz (← a.toNat?) (← b.toNat?)
  | ["ccx", a, b, c] => return .ccx (← a.toNat?) (← b.toNat?) (← c.toNat?)
  | ["h", q] => return .h (← q.toNat?)
  | ["x", q] => return .x (← q.toNat?)
  | ["rx", q] => return .rx (← q.toNat?)
  | ["ry", q] => return .ry (← q.toNat?)
  | ["rz", q] => return .rz (← q.toNat?)
  | ["u", q] => return .u (← q.toNat?)
  | _ => none

def showInstr : Instr → String
  | .J q => s!"J:{q}"
  | .CZ a b => s!"C:{a}:{b}"

partial def loop (stdin : IO.FS.Stream) (stdout : IO.FS.Stream) : IO Unit := do
  let line ← stdin.getLine
  if line.isEmpty then return
  let toks := (line.trimRight.splitOn " ").filter (· ≠ "")
  if toks.head? = some "G" then
    match toks.tail.mapM parseGate with
    | some gs => stdout.putStrLn (" ".intercalate ((gatesToJcz gs).map showInstr))
    | none => stdout.putStrLn "error"
    loop stdin stdout
    return
  match parseLine line.trimRight with
  | some (w, prog) =>
    let g := compileJcz w prog
    stdout.putStrLn s!"{g.numVertices} {g.numEdges} {g.numMeasurements}"
  | none => stdout.putStrLn "error"
  loop stdin stdout

def main : IO Unit := do
  loop (← IO.getStdin) (← IO.getStdout)
