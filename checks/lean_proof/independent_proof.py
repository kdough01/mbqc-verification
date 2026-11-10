"""
lean_proof/independent_proof — one more Lean proof of the statement the node already proves.

What it checks
    That a separately written theorem proves exactly the node's statement, by a different proof, from
    standard axioms and declared assumptions only. A node's first proof is its lean_decl (lean/proof); each
    further proof is one of these tests, usually added by a proposal.

How it works
    1. Inspects the proof's declaration (decl), which lives in its own file,
       lean/MBQC/Papers/<paper>/<theorem>/Proof_<k>.lean.
    2. Checks that its statement is syntactically the main theorem's. Definitional equality is not enough:
       `n + 0 = n` and `n = n + 0` are definitionally equal but are different statements.
    3. Checks its axioms as lean/proof does.
    4. Compares its proof term with every earlier proof's: an identical term is a copy, not another proof.
       Proof files cannot import other proofs (imports under MBQC.Papers are refused when proposed).

Parameters
    decl        the Lean name of the additional proof
    approach    one line: the mathematical idea of this proof (a person judges it)
    added       when it was added (date)

Passes when
    Same statement, a different proof term, and only standard or declared axioms.

Fails when
    The declaration is missing or not a theorem, states something else (even something definitionally equal),
    repeats an earlier proof term, uses sorry, or rests on an undeclared axiom.

Grants
    proved, or proved_modulo the assumption nodes it uses.

Limits
    It does not establish that the proof uses a different mathematical idea; the approach text says what the
    idea is and a person judges it.

Example
    - test: lean_proof/independent_proof
      name: lean-proof-2
      params: {decl: MBQC.Papers.p_abc.theorem_1.proof_2, approach: "induction on n instead of a closed form"}
"""

from __future__ import annotations

from checks._framework import Result
from checks._shared.lean import ASSUMPTION_NAMESPACE, STANDARD_AXIOMS, LeanUnavailable, inspect, node_prefixes, owner

PARAMS = {"decl": {"type": "string"}, "approach": {"type": "string"}, "added": {"type": "string"}}
REQUIRED = ["decl"]


def applies_to(node):
    return bool(node.lean_decl)


def run(node, params, ctx):
    decl = params["decl"]
    try:
        info = inspect(ctx)
    except LeanUnavailable as e:
        return Result("error", summary=str(e))
    d, same = info.get(decl), info.get(f"same:{node.lean_decl}|{decl}")
    if d is None or d.get("missing") or same is None or same.get("missing"):
        return Result("fail", summary=f"{decl} or {node.lean_decl} not found in the Lean project")
    if d["kind"] != "theorem":
        return Result("fail", summary=f"{decl} is a {d['kind']}, not a theorem")
    axioms = sorted(d["axioms"])
    extra = [a for a in axioms if a not in STANDARD_AXIOMS]
    prefixes = node_prefixes(ctx.dag)
    bad = [a for a in extra if not a.startswith(ASSUMPTION_NAMESPACE) or owner(a, prefixes) is None]
    ev = {"decl": decl, "of": node.lean_decl, "module": d["module"], "axioms": axioms,
          "statement_identical": same["type_equal"], "definitionally_equal": same["defeq"],
          "approach": params.get("approach")}
    if "sorryAx" in axioms:
        return Result("fail", summary="the proof uses sorry", evidence=ev)
    if bad:
        return Result("fail", summary=f"undeclared axioms: {', '.join(bad)}", evidence=ev)
    if not same["type_equal"]:
        why = "definitionally equal but not the same statement" if same["defeq"] else "a different statement"
        return Result("fail", summary=f"{decl} proves {why}; restate {node.lean_decl} exactly", evidence=ev)
    earlier = [node.lean_decl] + [c.params.get("decl") for c in node.checks if c.kind == "lean_proof"]
    earlier = earlier[:earlier.index(decl)] if decl in earlier else earlier
    copies = [e for e in earlier if (info.get(f"same:{e}|{decl}") or {}).get("value_equal")]
    ev["same_proof_term_as"] = copies
    if copies:
        return Result("fail", summary=f"{decl} has the same proof term as {copies[0]}: a copy", evidence=ev)
    assumption_nodes = sorted({owner(a, prefixes) for a in extra if owner(a, prefixes)})
    if extra:
        return Result("pass", "proved_modulo", "all values in the statement", frontier=assumption_nodes,
                      summary=f"another proof of the same statement, from {len(extra)} assumption axiom(s)", evidence=ev)
    return Result("pass", "proved", "all values in the statement",
                  summary="another proof of the same statement; axioms: " + ", ".join(axioms or ["none"]), evidence=ev)
