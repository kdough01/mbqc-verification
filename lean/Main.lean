import MBQC.Defs.JCZ

/-!
`mbqc_counts`: one J/CZ stream per input line, `width tok tok ...` with tokens
`J:q` and `C:a:b`; prints `N E M` for each line. Used by the differential check.
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

partial def loop (stdin : IO.FS.Stream) (stdout : IO.FS.Stream) : IO Unit := do
  let line ← stdin.getLine
  if line.isEmpty then return
  match parseLine line.trimRight with
  | some (w, prog) =>
    let g := compileJcz w prog
    stdout.putStrLn s!"{g.numVertices} {g.numEdges} {g.numMeasurements}"
  | none => stdout.putStrLn "error"
  loop stdin stdout

def main : IO Unit := do
  loop (← IO.getStdin) (← IO.getStdout)
