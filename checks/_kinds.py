"""
_kinds.py — the test types (one per folder of checks/): which question each answers and the highest status
a pass may grant. Light on purpose (no heavy imports), so dagtool can compute status without loading qiskit.

dagtool clamps every result to its type's ceiling, so a scaling test can never report `proved`, whatever its
code says. Adding a type means adding a folder, a row here, and a README for the folder.
"""

from __future__ import annotations

from dataclasses import dataclass

TRUTH_ORDER = ["conjecture", "empirical", "bounded", "assumed", "proved_modulo", "proved"]
TRUTH_RANK = {s: i for i, s in enumerate(TRUTH_ORDER)} | {"defined": len(TRUTH_ORDER) - 1, "refuted": -1}
FAITH_ORDER = ["unreviewed", "tested", "human_reviewed"]
FAITH_RANK = {s: i for i, s in enumerate(FAITH_ORDER)}


@dataclass(frozen=True)
class KindMeta:
    question: str      # faithfulness | truth
    ceiling: str       # highest status this type may grant
    summary: str


CHECK_KINDS: dict[str, KindMeta] = {
    # faithfulness: does the statement mean what we intend?
    "vocabulary":   KindMeta("faithfulness", "tested",
                             "Every constant in the Lean statement comes from the vetted definitions"),
    "differential": KindMeta("faithfulness", "tested",
                             "Lean's computable definitions reproduce the independent implementation's numbers"),
    "mutation":     KindMeta("faithfulness", "tested",
                             "Perturbed statements are rejected"),
    "nonvacuity":   KindMeta("faithfulness", "tested",
                             "The hypotheses are jointly satisfiable (witness)"),
    "equivalence":  KindMeta("faithfulness", "tested",
                             "Independent formalizations are provably equivalent"),
    # truth: is the statement true?
    "lean":         KindMeta("truth", "proved",
                             "Lean proof; #print axioms lists only standard axioms and declared assumptions"),
    "lean_proof":   KindMeta("truth", "proved",
                             "Another Lean proof of the same statement, written separately: identical statement, "
                             "a different proof term, no access to the other proofs"),
    "finite":       KindMeta("truth", "bounded",
                             "Exhaustive check on a stated finite domain"),
    "symbolic":     KindMeta("truth", "empirical",
                             "Computer-algebra certificate (sympy); proved only once Lean checks it"),
    "translation":  KindMeta("truth", "bounded",
                             "Compiled pattern equals its circuit, per checked instance"),
    "numerical":    KindMeta("truth", "empirical",
                             "Simulation against the exact answer on a stated domain"),
    "scaling":      KindMeta("truth", "empirical",
                             "Formula reproduces every count on a grid incl. held-out points"),
    "refuter":      KindMeta("truth", "empirical",
                             "Counterexample search; finds one (refuted) or records what was searched"),
    "literature":   KindMeta("truth", "assumed",
                             "Imported result: citation, exact form, convention map"),
    "reproduction": KindMeta("truth", "empirical",
                             "A recorded run of a pinned pipeline agrees with the claimed value"),
    "tool":         KindMeta("truth", "empirical",
                             "A pinned external tool (Stim, PyMatching, sinter, gridsynth, Qualtran, Azure Resource "
                             "Estimator) computes the value in CI and it agrees with the frozen claim"),
}

# Types that call the pinned external tools of tools/requirements.txt (hashed into their evidence).
TOOL_KINDS = ("tool", "refuter", "reproduction", "finite")

# Kinds whose verdict depends on the Lean sources (hashed into their evidence).
LEAN_KINDS = ("lean", "lean_proof", "vocabulary", "nonvacuity", "differential", "equivalence")

# Faithfulness checks a node of each kind needs before it counts as `tested`.
# A check in this list is required when the node declares it, and the Lean-only
# ones (LEAN_ONLY) are required automatically once the node has a lean_decl.
REQUIRED_FAITH = {
    "definition": ["differential"],
    "core": ["vocabulary", "mutation", "nonvacuity"],
    "assumption": ["literature"],
    "transfer": ["vocabulary", "mutation", "nonvacuity"],
    "lemma": ["vocabulary", "differential", "mutation", "nonvacuity", "equivalence"],
    "theorem": ["vocabulary", "differential", "mutation", "nonvacuity", "equivalence"],
}
LEAN_ONLY = ("vocabulary", "nonvacuity")


def clamp_truth(grant: str | None, kind: str) -> str | None:
    """A truth grant capped at the kind's ceiling. `refuted` is never capped."""
    if grant is None or grant == "refuted":
        return grant
    ceiling = CHECK_KINDS[kind].ceiling
    return grant if TRUTH_RANK[grant] <= TRUTH_RANK[ceiling] else ceiling
