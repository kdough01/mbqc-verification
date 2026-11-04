"""
proof.py — lean_proof: one more Lean proof of a statement the node already proves.

A node's first proof is its `lean_decl` (the lean check). Each further proof is a `lean_proof` check whose
`decl` is a theorem in its own file, lean/MBQC/Papers/<paper>/<theorem>/Proof_<k>.lean. It passes when
    the declaration is a theorem, proved from standard axioms and declared assumptions only (as for `lean`);
    its statement is syntactically the main theorem's (definitional equality is not enough: `n + 0 = n` and
    `n = n + 0` are definitionally equal but are different statements);
    its proof term differs from every earlier proof's (an identical term is a copy, not another proof).
Tactic proofs elaborate with auxiliary names tied to the theorem's own name, so the term comparison catches
copies of term-mode proofs; the proposal step also refuses a file that repeats an earlier one.
The proof file cannot import other proofs (imports under MBQC.Papers are refused when it is proposed), so it
cannot reuse them. What it does not establish: that the proof uses a different mathematical idea. The proposer's
`approach` text says what the idea is; a person judges it.

Node params: decl: <Lean name>    approach: <one line>    added: <date>
"""

from __future__ import annotations

from verification.base import Check, CheckResult, register

from .leanrun import ASSUMPTION_NAMESPACE, STANDARD_AXIOMS, LeanUnavailable, inspect, owner, node_prefixes


@register
class LeanProofCheck(Check):
    kind = "lean_proof"

    def applies_to(self, node):
        return bool(node.lean_decl)

    def run(self, node, params, ctx):
        decl = params.get("decl")
        if not decl:
            return CheckResult("error", summary="lean_proof needs params.decl")
        try:
            info = inspect(ctx)
        except LeanUnavailable as e:
            return CheckResult("error", summary=str(e))
        d, same = info.get(decl), info.get(f"same:{node.lean_decl}|{decl}")
        if d is None or d.get("missing") or same is None or same.get("missing"):
            return CheckResult("fail", summary=f"{decl} or {node.lean_decl} not found in the Lean project")
        if d["kind"] != "theorem":
            return CheckResult("fail", summary=f"{decl} is a {d['kind']}, not a theorem")
        axioms = sorted(d["axioms"])
        extra = [a for a in axioms if a not in STANDARD_AXIOMS]
        prefixes = node_prefixes(ctx.dag)
        bad = [a for a in extra if not a.startswith(ASSUMPTION_NAMESPACE) or owner(a, prefixes) is None]
        ev = {"decl": decl, "of": node.lean_decl, "module": d["module"], "axioms": axioms,
              "statement_identical": same["type_equal"], "definitionally_equal": same["defeq"],
              "approach": params.get("approach")}
        if "sorryAx" in axioms:
            return CheckResult("fail", summary="the proof uses sorry", evidence=ev)
        if bad:
            return CheckResult("fail", summary=f"undeclared axioms: {', '.join(bad)}", evidence=ev)
        if not same["type_equal"]:
            why = "definitionally equal but not the same statement" if same["defeq"] else "a different statement"
            return CheckResult("fail", summary=f"{decl} proves {why}; restate {node.lean_decl} exactly", evidence=ev)
        earlier = [node.lean_decl] + [c.params.get("decl") for c in node.checks if c.kind == "lean_proof"]
        earlier = earlier[:earlier.index(decl)] if decl in earlier else earlier
        copies = [e for e in earlier if (info.get(f"same:{e}|{decl}") or {}).get("value_equal")]
        ev["same_proof_term_as"] = copies
        if copies:
            return CheckResult("fail", summary=f"{decl} has the same proof term as {copies[0]}: a copy", evidence=ev)
        assumption_nodes = sorted({owner(a, prefixes) for a in extra if owner(a, prefixes)})
        if extra:
            return CheckResult("pass", "proved_modulo", "all values in the statement", frontier=assumption_nodes,
                               summary=f"another proof of the same statement, from {len(extra)} assumption axiom(s)",
                               evidence=ev)
        return CheckResult("pass", "proved", "all values in the statement",
                           summary="another proof of the same statement; axioms: " + ", ".join(axioms or ["none"]),
                           evidence=ev)
