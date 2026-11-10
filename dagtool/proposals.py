"""
proposals.py — the verifier's side of a proposal: describe open theorems, give feedback, apply what passes.

    dagtool open-theorems [--json] [--count] [--node ID]   what is open, and what a proposal for it must look like
    dagtool proof-targets [--json] [--node ID]             formalized theorems that can take another Lean proof
    dagtool feedback --proposal DIR                        run every check on a proposal without changing anything
    dagtool feedback --node ID --results-root DIR          a node's reproduction checks against candidate results
    dagtool apply-proposals DIR [--report F]               apply the proposals that pass (used by the proposals gate)
    dagtool proposal-paths < CHANGED_FILES                 which changed paths a proposal may touch
    dagtool lean-check FILE                                scan and compile one Lean file under lean/MBQC/Papers/

The verifier contains no model and calls none. Proposals are written elsewhere (by people or by tools in other
repositories, such as the Quantum Genesis dashboard) and reach the verifier as data:

    proposals/<node id>/proposal.json   outcome, Lean declaration, witness, dependency edges, notes
    proposals/<node id>/theorem.lean    the statement, its proof and a witness, in the node's own namespace
    proposals/<node id>/attempts.json   optional: every attempt the proposer made and why (kept as a record)
    proposals/<node id>/suite.json      required for a formalization: claim type and proposed checks (suites.py)
    proposals/<node id>/checks.py       optional: predicates the suite's finite/refuter checks call (scanned)

A proposal with outcome `proof` adds another Lean proof to a theorem that is already formalized. It goes in its
own file and namespace (lean/MBQC/Papers/<paper>/<theorem>/Proof_<k>.lean, <namespace>.Proof_<k>), cannot import
the other proofs, must state the theorem exactly as the main declaration does and must not repeat its proof term
(the lean_proof check). It must say in `approach` what idea the proof uses. The node then records every proof.

What a proposal can and cannot do:
  * It may write one Lean file at the node's own path and propose dependency edges to existing nodes.
  * It proposes a test suite, but the verifier decides it: the fixed Lean checks (lean, vocabulary, nonvacuity) are
    always added, the suite must meet its claim type's minimum and stay within dag/suites/policy.yaml, and expected
    values come only from frozen files or held-out values. `extra_checks` is rejected.
  * The Lean file is scanned first (no axiom, sorry, IO, metaprogramming, imports outside MBQC) and compiled with
    no credentials in the environment.
  * `feedback` runs exactly what `apply-proposals` runs and then restores every file, so a proposer can iterate on
    the verifier's own verdict without being able to change it. A rejected proposal leaves no trace in the DAG.
  * Status still comes only from evidence. Faithfulness stays below human-reviewed until a person approves the
    statement (review workflow), and `vocabulary` fails if the statement uses anything outside the vetted definitions.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path, PurePosixPath

import yaml

from .model import EDGE_KINDS, Dag, Node, load_dag

DONE_TAGS = ("formalized", "not-formalizable", "counterexample-suspected", "unproved")
OUTCOMES = ("formalized", "unproved", "not_formalizable", "counterexample")
PROOF_OUTCOME = "proof"      # another Lean proof of a formalized theorem
PROPOSAL_FILES = ("proposal.json", "theorem.lean", "attempts.json", "suite.json", "checks.py")
SECRET_ENV = ("GITHUB_TOKEN", "GH_TOKEN", "ACTIONS_RUNTIME_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
              "ACTIONS_ID_TOKEN_REQUEST_URL")
SECRET_PATTERN = re.compile(r"(TOKEN|SECRET|PASSWORD|API_KEY|CREDENTIAL)", re.I)

# Lean constructs a proposed file may not contain: they bypass the kernel, run code at build time,
# or extend the syntax. Proof automation (simp, omega, grind, decide) is fine.
FORBIDDEN_LEAN = [
    (r"\baxiom\b", "declares an axiom"), (r"\bsorry\b", "uses sorry"), (r"\badmit\b", "uses admit"),
    (r"#eval\b|#exit\b|#reduce\b", "runs a command"), (r"\brun_cmd\b|\brun_elab\b|\brun_meta\b", "runs code"),
    (r"\bIO\b", "uses IO"), (r"\bunsafe\b", "is unsafe"), (r"@\[\s*(extern|implemented_by|export)", "replaces code"),
    (r"\b(builtin_)?initialize\b", "runs code at load time"), (r"\bnative_decide\b", "trusts compiled code"),
    (r"^\s*(macro|macro_rules|syntax|elab|elab_rules|declare_syntax_cat|notation|infix[lr]?|prefix|postfix)\b",
     "extends the syntax"),
    (r"set_option\s+debug\.", "changes kernel checking"), (r"\bopaque\b", "declares an opaque constant"),
    (r"\bimplemented_by\b|\bextern\b", "replaces code"),
]



# ------------------------------------------------------------------ naming

def _ident(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", s)


def lean_names(node: Node) -> tuple[str, Path]:
    """(namespace, path) a proposal must use: one module and namespace per paper theorem."""
    paper = node.raw["paper"]
    pmod = "Paper_" + _ident(paper.get("paper_id") or node.id.split(".")[1])
    tmod = "T_" + _ident(node.id.split(".")[-1])
    return f"MBQC.Papers.{pmod}.{tmod}", Path("lean") / "MBQC" / "Papers" / pmod / f"{tmod}.lean"


def proofs_of(node: Node) -> list[dict]:
    """Every Lean proof the node records: the main declaration first, then each lean_proof check."""
    main = next((c.name for c in node.checks if c.kind == "lean"), None)
    if not node.lean_decl or main is None:
        return []
    out = [{"index": 1, "decl": node.lean_decl, "check": main, "approach": None}]
    for c in node.checks:
        if c.kind == "lean_proof":
            out.append({"index": len(out) + 1, "decl": c.params.get("decl"), "check": c.name,
                        "approach": c.params.get("approach"), "added": c.params.get("added")})
    return out


def proof_names(node: Node, index: int) -> tuple[str, Path]:
    """(namespace, path) for the node's proof number `index` (2, 3, ...)."""
    ns, path = lean_names(node)
    return f"{ns}.Proof_{index}", path.with_suffix("") / f"Proof_{index}.lean"


def proof_targets(dag: Dag, only: set[str] | None = None) -> list[Node]:
    """Formalized paper theorems (a main Lean declaration with a lean check) that can take another proof."""
    return sorted((n for n in dag.nodes.values() if (not only or n.id in only) and isinstance(n.raw.get("paper"), dict)
                   and n.lean_decl and any(c.kind == "lean" for c in n.checks)), key=lambda n: n.id)


def open_theorems(dag: Dag, only: set[str] | None = None) -> list[Node]:
    """Paper theorems with no checks and no recorded outcome yet."""
    out = []
    for n in dag.nodes.values():
        if only and n.id not in only:
            continue
        if isinstance(n.raw.get("paper"), dict) and not n.checks and not n.lean_decl and not set(n.tags) & set(DONE_TAGS):
            out.append(n)
    return sorted(out, key=lambda n: n.id)


def describe(dag: Dag, node: Node) -> dict:
    """Everything a proposer needs, as data: the statement, where the Lean must go, the vetted vocabulary and the
    proved results it may build on, and the proposal format. No instructions, only facts about the verifier."""
    from .status import compute
    st = compute(dag)
    ns, path = lean_names(node)

    def row(n: Node) -> dict:
        return {"id": n.id, "kind": n.kind, "truth": st[n.id].eff_truth, "lean": list(n.lean_names),
                "statement": " ".join(n.statement.split())[:800]}
    vocab = [row(n) for n in dag.nodes.values() if n.kind in ("definition", "assumption") and n.lean_names]
    blocks = [row(n) for n in dag.nodes.values() if n.kind in ("core", "transfer", "lemma", "theorem")
              and n.lean_decl and st[n.id].eff_truth in ("proved", "proved_modulo") and n.id != node.id]
    return {
        "node": node.id, "title": node.title, "statement": node.statement.strip(), "paper": node.raw.get("paper"),
        "namespace": ns, "lean_file": path.as_posix(),
        "vocabulary": sorted(vocab, key=lambda r: r["id"]), "building_blocks": sorted(blocks, key=lambda r: r["id"]),
        "checks_run": ["lean", "vocabulary", "nonvacuity", "+ the suite's checks"],
        "suite_policy": _suite_brief(dag.root),
        "proposal_format": {
            "directory": f"proposals/{node.id}/",
            "files": {"proposal.json": "required", "theorem.lean": "required when outcome is formalized",
                      "suite.json": "required when outcome is formalized: {claim_type, checks: [{test, name, params, "
                                    "rationale}]} (test: <type>/<name>, see suite_policy.tests; the older "
                                    "{kind, params} form is also accepted)",
                      "checks.py": "optional: predicates for finite/refuter checks, referenced as checks.py:FUNCTION",
                      "attempts.json": "optional record of every attempt and its rationale"},
            "proposal.json": {"node": node.id, "outcome": list(OUTCOMES), "reason": "text",
                              "lean_decl": f"{ns}.<theorem name>", "witness": f"{ns}.<witness name> or null",
                              "depends_on": [{"node": "<existing node id>", "kind": "uses | assumes | instantiates",
                                              "note": "text"}],
                              "statement_tex": "LaTeX or null", "notes": "text"},
            "lean_forbidden": [why for _, why in FORBIDDEN_LEAN],
        },
    }


def describe_proof(dag: Dag, node: Node, root: Path | None = None) -> dict:
    """What another proof of a formalized theorem must look like: the main declaration and its file (to restate the
    statement exactly), the proofs so far and their approaches (so a new one can use a different idea)."""
    root = root or dag.root
    proofs = proofs_of(node)
    k = len(proofs) + 1
    ns, path = proof_names(node, k)
    main_file = root / lean_names(node)[1]
    return {
        "node": node.id, "title": node.title, "statement": node.statement.strip(), "main_decl": node.lean_decl,
        "main_lean_file": lean_names(node)[1].as_posix(),
        "main_lean_source": main_file.read_text(encoding="utf-8") if main_file.exists() else None,
        "proofs": proofs, "next_index": k, "namespace": ns, "lean_file": path.as_posix(),
        "checks_run": ["lean_proof"],
        "rules": ["state the theorem exactly as the main declaration does (syntactically, not only definitionally)",
                  "a different proof term from every earlier proof", "no imports under MBQC.Papers",
                  "say in approach which idea the proof uses"],
        "proposal_format": {
            "directory": f"proposals/{node.id}/",
            "files": {"proposal.json": "required", "theorem.lean": "required: the proof, in namespace " + ns,
                      "attempts.json": "optional record of every attempt and its rationale"},
            "proposal.json": {"node": node.id, "outcome": PROOF_OUTCOME, "lean_decl": f"{ns}.<theorem name>",
                              "approach": "one line: the idea of this proof", "notes": "text"},
            "lean_forbidden": [why for _, why in FORBIDDEN_LEAN],
        },
    }


def _normalized(text: str) -> str:
    """Lean source without comments, namespace lines or whitespace, to spot a copied proof before compiling."""
    code = re.sub(r"/-.*?-/", "", text, flags=re.S)
    code = re.sub(r"--[^\n]*", "", code)
    code = re.sub(r"^\s*(namespace|end)\b[^\n]*$", "", code, flags=re.M)
    return re.sub(r"\s+", " ", code).strip()


def _suite_brief(root: Path) -> dict:
    """The policy plus what a suite may reference: frozen result files and held-out ids (never their values)."""
    from .suites import load_policy
    frozen = []
    for base in ("experiments", "dag/transcriptions"):
        if (root / base).exists():
            frozen += [p.relative_to(root).as_posix() for p in (root / base).rglob("*.json")
                       if "results" in p.parts or base == "dag/transcriptions"]
    held = sorted(p.stem for p in (root / "dag" / "heldout").glob("*.json")) if (root / "dag" / "heldout").exists() else []
    return {**load_policy(root), "frozen_files": sorted(frozen)[:200], "heldout_ids": held,
            "examples": {
                "finite": {"test": "finite/exhaustive", "name": "small-n", "params": {"predicate": "checks.py:holds",
                           "domain": {"n": {"range": [1, 60]}}}, "rationale": "every n up to 60, exhaustively"},
                "refuter": {"test": "refuter/hypothesis", "name": "random-n", "params": {
                            "predicate": "checks.py:holds", "strategy": {"n": {"integers": [1, 100000]}},
                            "max_examples": 1000}, "rationale": "large n the finite check does not reach"},
                "equivalence": {"test": "equivalence/iff_proof", "name": "restated", "params": {"other": "<ns>.restated",
                                "proof": "<ns>.restated_iff"}, "rationale": "a second, independently written statement"},
                "tool": {"test": "tool/qualtran_cost", "name": "tcount", "params": {"args": {"bloq":
                         "qualtran.bloqs.basic_gates.Toffoli"}, "path": "total_t_count", "expect": {"heldout": "<id>"},
                         "op": "eq", "domain": "one Toffoli"}, "rationale": "an independent count"}},
            "test_docs": {t: {"summary": i.summary, "what": i.sections.get("What it checks", ""),
                              "parameters": i.sections.get("Parameters", "")}
                          for t, i in _tests().items() if t in {x for v in load_policy(root)["tests"].values() for x in v}}}


def _tests():
    from checks._framework import discover
    return discover()


# ---------------------------------------------------------------- checking

def scan_lean(text: str) -> list[str]:
    problems = []
    code = re.sub(r"/-.*?-/", "", text, flags=re.S)
    code = re.sub(r"--[^\n]*", "", code)
    for pat, why in FORBIDDEN_LEAN:
        if re.search(pat, code, flags=re.M):
            problems.append(why)
    for m in re.finditer(r"^\s*import\s+(.+)$", code, flags=re.M):
        for mod in m.group(1).split():
            if not mod.startswith("MBQC.") or mod.startswith("MBQC.Papers."):
                problems.append(f"imports {mod} (only existing MBQC modules outside MBQC.Papers)")
    return sorted(set(problems))



def scrubbed_env() -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in SECRET_ENV and not k.startswith("INPUT_") and not SECRET_PATTERN.search(k)}
    env["ELAN_NO_OVERRIDE_NOTICE"] = "1"
    return env


def lean_check(root: Path, file: str) -> tuple[bool, str]:
    """Compile one proposed file with `lake env lean`, after the scan, without any credentials in the environment."""
    from checks._shared.lean import lake
    path = (root / file).resolve()
    papers = (root / "lean" / "MBQC" / "Papers").resolve()
    if papers not in path.parents or path.suffix != ".lean":
        return False, "only files under lean/MBQC/Papers/ can be checked"
    if not path.exists():
        return False, f"{file} does not exist"
    problems = scan_lean(path.read_text(encoding="utf-8"))
    if problems:
        return False, "not allowed in a proposed file: " + "; ".join(problems)
    p = subprocess.run([lake(), "env", "lean", str(path.relative_to(root / "lean"))], cwd=root / "lean",
                       capture_output=True, text=True, timeout=900, env=scrubbed_env())
    out = (p.stdout + p.stderr).strip()
    return p.returncode == 0 and "declaration uses 'sorry'" not in out, out[-6000:] or "ok"


def proposal_paths(paths: list[str]) -> tuple[bool, list[str]]:
    """A pull request carrying proposals may only add or change proposals/<node id>/<one of PROPOSAL_FILES>."""
    bad = []
    for p in paths:
        parts = PurePosixPath(p.strip()).parts
        if not parts:
            continue
        if len(parts) != 3 or parts[0] != "proposals" or parts[2] not in PROPOSAL_FILES \
                or not re.fullmatch(r"[a-z][a-z0-9_]*(\.[A-Za-z0-9_]+)+", parts[1]):
            bad.append(p.strip())
    return not bad, bad


# ------------------------------------------------------------------ apply

def _import_line(lean_file: Path) -> str:
    return "import " + ".".join(lean_file.with_suffix("").parts[1:])


def _set_import(root: Path, lean_file: Path, present: bool) -> None:
    f = root / "lean" / "MBQC.lean"
    lines = f.read_text(encoding="utf-8").splitlines()
    line = _import_line(lean_file)
    lines = [l for l in lines if l.strip() != line] + ([line] if present else [])
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")



def validate_proposal(dag: Dag, node: Node, prop: dict, ns: str) -> list[str]:
    errs = []
    if prop.get("node") not in (None, node.id):
        errs.append(f"proposal.json names node {prop.get('node')!r}, not {node.id}")
    if prop.get("outcome") not in OUTCOMES:
        errs.append(f"unknown outcome {prop.get('outcome')!r}")
    if prop.get("extra_checks"):
        errs.append("a proposal cannot choose checks: the checks for a theorem are fixed by the verifier")
    if prop.get("outcome") != "formalized":
        return errs
    decl = prop.get("lean_decl") or ""
    if not re.fullmatch(re.escape(ns) + r"\.[A-Za-z_][A-Za-z0-9_']*", decl):
        errs.append(f"lean_decl must be {ns}.<name>")
    w = prop.get("witness")
    if w and not re.fullmatch(re.escape(ns) + r"\.[A-Za-z_][A-Za-z0-9_']*", w):
        errs.append(f"witness must be {ns}.<name>")
    for d in prop.get("depends_on") or []:
        if not isinstance(d, dict) or d.get("node") not in dag.nodes or d.get("node") == node.id:
            errs.append(f"depends_on names an unknown node: {d!r}")
        elif d.get("kind", "uses") not in EDGE_KINDS or d.get("kind") == "variant_of":
            errs.append(f"edge kind {d.get('kind')!r} not allowed")
    return errs


def _load_raw(node: Node) -> dict:
    return yaml.safe_load(node.path.read_text(encoding="utf-8"))


def _save_raw(node: Node, raw: dict) -> None:
    node.path.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")


def _note(raw: dict, text: str) -> None:
    stamp = time.strftime("%Y-%m-%d", time.gmtime())
    raw["notes"] = ((raw.get("notes") or "").rstrip() + f"\n[{stamp}] {text}").strip()[:4000] + "\n"


class _Snapshot:
    """Every file a proposal can touch, so a dry run (feedback) or a rejected proposal restores them exactly."""

    def __init__(self, root: Path, node: Node, lean_file: Path, extra: tuple[Path, ...] = ()):
        self.root = root
        self.extra = {p: (p.read_bytes() if p.exists() else None) for p in extra}
        self.new_dirs = [d for p in extra for d in (p.parent, p.parent.parent) if not d.exists()]
        # Bytes, not text: a text round trip rewrites CRLF checkouts as LF.
        self.files = {node.path: node.path.read_bytes(),
                      root / "lean" / "MBQC.lean": (root / "lean" / "MBQC.lean").read_bytes()}
        self.lean = root / lean_file
        self.lean_before = self.lean.read_bytes() if self.lean.exists() else None
        self.evidence = root / "dag" / "evidence" / node.id
        self.evidence_before = {p: p.read_bytes() for p in self.evidence.rglob("*") if p.is_file()} \
            if self.evidence.exists() else None

    def restore(self) -> None:
        for p, data in self.files.items():
            if p.read_bytes() != data:
                p.write_bytes(data)
        for p, data in self.extra.items():
            if data is None:
                p.unlink(missing_ok=True)
            elif p.read_bytes() != data:
                p.write_bytes(data)
        for d in self.new_dirs:             # folders the proposal created, deepest first, only if left empty
            if d.exists() and not any(d.iterdir()):
                d.rmdir()
        if self.lean_before is None:
            self.lean.unlink(missing_ok=True)
        elif self.lean.read_bytes() != self.lean_before:
            self.lean.write_bytes(self.lean_before)
        shutil.rmtree(self.evidence, ignore_errors=True)
        for p, data in (self.evidence_before or {}).items():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)


def apply_one(root: Path, node_id: str, src: Path, run_checks: bool = True, dry_run: bool = False,
              echo=print) -> dict:
    """Check one proposal and, unless dry_run, add it to the DAG. Rejected proposals change nothing."""
    dag = load_dag(root)
    node = dag.nodes.get(node_id)
    row = {"node": node_id, "dry_run": dry_run}
    try:
        peek = json.loads((src / "proposal.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        peek = None
    if node is not None and isinstance(peek, dict) and peek.get("outcome") == PROOF_OUTCOME:
        return apply_proof(root, dag, node, src, peek, run_checks=run_checks, dry_run=dry_run, echo=echo)
    if node is None or node_id not in {n.id for n in open_theorems(dag)}:
        return {**row, "outcome": "skipped", "reason": "not an open paper theorem"}
    ns, lean_file = lean_names(node)
    if not (src / "proposal.json").exists():
        return {**row, "outcome": "rejected", "reason": "no proposal.json"}
    try:
        prop = json.loads((src / "proposal.json").read_text(encoding="utf-8"))
        assert isinstance(prop, dict)
    except (ValueError, AssertionError):
        return {**row, "outcome": "rejected", "reason": "proposal.json is not a JSON object"}
    errs = validate_proposal(dag, node, prop, ns)
    if errs:
        return {**row, "outcome": "rejected", "reason": "; ".join(errs)}
    reason = str(prop.get("reason") or "")[:600]
    snap = _Snapshot(root, node, lean_file)
    attempts = src / "attempts.json"

    def keep_record() -> None:
        if attempts.exists() and not dry_run:
            dest = root / "dag" / "proposals" / node_id
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(attempts, dest / time.strftime("attempts-%Y%m%dT%H%M%SZ.json", time.gmtime()))

    outcome = prop["outcome"]
    if outcome != "formalized":
        tag = {"unproved": "unproved", "not_formalizable": "not-formalizable", "counterexample": "counterexample-suspected"}[outcome]
        if dry_run:
            return {**row, "outcome": tag, "reason": reason, "accepted": True}
        raw = _load_raw(node)
        raw["tags"] = [t for t in raw.get("tags", []) if t not in DONE_TAGS] + [tag]
        _note(raw, f"proposal recorded as {tag}: {reason}" + (f" Notes: {prop['notes']}" if prop.get("notes") else ""))
        _save_raw(node, raw)
        keep_record()
        return {**row, "outcome": tag, "reason": reason, "accepted": True}
    if not (src / "theorem.lean").exists():
        return {**row, "outcome": "rejected", "reason": "outcome formalized but no theorem.lean"}
    text = (src / "theorem.lean").read_text(encoding="utf-8")
    problems = scan_lean(text)
    if problems or f"namespace {ns}" not in text:
        return {**row, "outcome": "rejected", "reason": "Lean file rejected: " + "; ".join(problems or [f"not inside namespace {ns}"])}
    from .suites import validate_suite
    if not (src / "suite.json").exists():
        return {**row, "outcome": "rejected", "reason": "suite.json is required with a formalization: the claim type "
                                                          "and the checks proposed beyond the fixed Lean ones"}
    try:
        suite = json.loads((src / "suite.json").read_text(encoding="utf-8"))
    except ValueError:
        return {**row, "outcome": "rejected", "reason": "suite.json is not JSON"}
    checks_py = (src / "checks.py").read_text(encoding="utf-8") if (src / "checks.py").exists() else None
    suite_errs, suite_checks = validate_suite(root, node_id, ns, suite, checks_py)
    if suite_errs:
        return {**row, "outcome": "rejected", "reason": "suite rejected: " + "; ".join(suite_errs), "suite_errors": suite_errs}
    pred_file = root / "dag" / "predicates" / f"{node_id}.py"
    snap = _Snapshot(root, node, lean_file, extra=(pred_file,))

    # apply: the Lean file, the import, the node's fixed checks and the proposed edges (never its statement)
    target = root / lean_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    _set_import(root, lean_file, True)
    if checks_py is not None:
        pred_file.parent.mkdir(parents=True, exist_ok=True)
        pred_file.write_text(checks_py, encoding="utf-8")

    def reject(why: str, **extra) -> dict:
        snap.restore()
        return {**row, "outcome": "rejected", "reason": why, **extra}

    if run_checks:
        try:
            ok, compiled = lean_check(root, lean_file.as_posix())
        except Exception as e:  # noqa: BLE001 - no toolchain, or it could not start
            return reject(f"the Lean toolchain could not run: {e}")
        if not ok:
            return reject("the Lean file does not compile", compiler=compiled)
    raw = _load_raw(node)
    raw["lean_decl"] = prop["lean_decl"]
    deps = [{k: v for k, v in {"node": d["node"], "kind": d.get("kind", "uses"), "note": d.get("note")}.items() if v}
            for d in prop.get("depends_on") or []]
    if deps:
        raw["depends_on"] = deps
    fixed = [{"test": "lean/proof"}, {"test": "vocabulary/vetted_constants"},
             {"test": "nonvacuity/witness", "params": {"witness": prop["witness"]}} if prop.get("witness")
             else {"test": "nonvacuity/witness"}]
    raw["checks"] = [{**c, "origin": "verifier"} for c in fixed] + suite_checks
    if checks_py is not None:
        raw["code"] = sorted(set(raw.get("code") or []) | {pred_file.relative_to(root).as_posix()})
    raw["tags"] = [t for t in raw.get("tags", []) if not t.startswith("claim:")] + [f"claim:{suite['claim_type']}"]
    if prop.get("statement_tex"):
        raw["statement_tex"] = str(prop["statement_tex"])[:4000]
    raw["tags"] = [t for t in raw.get("tags", []) if t not in ("open",) + DONE_TAGS] + ["formalized"]
    _note(raw, "formalized from a submitted proposal; the statement awaits human review. " + str(prop.get("notes") or ""))
    _save_raw(node, raw)
    try:
        dag = load_dag(root)
    except Exception as e:  # noqa: BLE001 - schema or edge problems
        return reject(f"the proposal makes the DAG invalid: {e}")
    if not run_checks:
        if dry_run:
            snap.restore()
        else:
            keep_record()
        return {**row, "outcome": "formalized", "reason": reason, "accepted": True, "checks": []}
    from .runner import plan, run
    records = run(dag, plan(dag, node_ids={node_id}), echo=lambda *a, **k: None)
    checks = [{"name": r["name"], "test": r["test"], "kind": r["kind"], "outcome": r["result"]["outcome"], "grants": r["result"]["grants"],
               "summary": r["result"]["summary"], "origin": _origin(raw, r["name"])} for r in records]
    bad = [c for c in checks if c["outcome"] in ("fail", "error")]
    if bad:
        return reject("checks did not pass: " + "; ".join(f"{c['name']}: {c['summary']}" for c in bad), checks=checks)
    from .status import compute
    gate = [f for f in compute(load_dag(root))[node_id].flags
            if f.code in ("check_failed", "mutation_survived", "missing_evidence")
            or (f.code == "convention_mismatch" and f.level == "warn")]
    if gate:   # would fail `dagtool check` in verify
        return reject("the result would fail the CI gate: " + "; ".join(f"{f.code}: {f.message}" for f in gate), checks=checks)
    if dry_run:
        snap.restore()
    else:
        keep_record()
        echo(f"{node_id}: formalized; " + ", ".join(f"{c['name']} {c['outcome']}" for c in checks))
    return {**row, "outcome": "formalized", "reason": reason, "accepted": True, "checks": checks}


def _origin(raw: dict, name: str) -> str:
    """Who asked for a check: the verifier (fixed) or the proposal's suite."""
    for c in raw.get("checks") or []:
        if (c.get("name") or str(c.get("test", "")).split("/")[0]) == name:
            return c.get("origin", "verifier")
    return "verifier"


def apply_proof(root: Path, dag: Dag, node: Node, src: Path, prop: dict, run_checks: bool = True,
                dry_run: bool = False, echo=print) -> dict:
    """Another Lean proof of a formalized theorem: its own file, the lean_proof check, nothing else changes."""
    row = {"node": node.id, "dry_run": dry_run, "kind": "proof"}
    if node.id not in {n.id for n in proof_targets(dag)}:
        return {**row, "outcome": "skipped", "reason": "not a formalized paper theorem (formalize it first)"}
    proofs = proofs_of(node)
    k = len(proofs) + 1
    ns, lean_file = proof_names(node, k)
    errs = []
    if prop.get("node") not in (None, node.id):
        errs.append(f"proposal.json names node {prop.get('node')!r}, not {node.id}")
    if prop.get("extra_checks") or prop.get("depends_on"):
        errs.append("a proof proposal cannot choose checks or edges: it only adds a proof")
    if not re.fullmatch(re.escape(ns) + r"\.[A-Za-z_][A-Za-z0-9_']*", prop.get("lean_decl") or ""):
        errs.append(f"lean_decl must be {ns}.<name> (this is proof {k})")
    approach = " ".join(str(prop.get("approach") or "").split())
    if not approach:
        errs.append("approach: say in one line which idea this proof uses")
    if not (src / "theorem.lean").exists():
        errs.append("no theorem.lean")
    if errs:
        return {**row, "outcome": "rejected", "reason": "; ".join(errs)}
    text = (src / "theorem.lean").read_text(encoding="utf-8")
    problems = scan_lean(text)
    if problems or f"namespace {ns}" not in text:
        return {**row, "outcome": "rejected", "reason": "Lean file rejected: " + "; ".join(problems or [f"not inside namespace {ns}"])}
    earlier = [root / lean_names(node)[1]] + [root / proof_names(node, p["index"])[1] for p in proofs[1:]]
    if any(f.exists() and _normalized(f.read_text(encoding="utf-8")) == _normalized(text) for f in earlier):
        return {**row, "outcome": "rejected", "reason": "the file repeats an earlier proof"}

    snap = _Snapshot(root, node, lean_file)
    target = root / lean_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    _set_import(root, lean_file, True)

    def reject(why: str, **extra) -> dict:
        snap.restore()
        return {**row, "outcome": "rejected", "reason": why, **extra}

    if run_checks:
        try:
            ok, compiled = lean_check(root, lean_file.as_posix())
        except Exception as e:  # noqa: BLE001 - no toolchain, or it could not start
            return reject(f"the Lean toolchain could not run: {e}")
        if not ok:
            return reject("the Lean file does not compile", compiler=compiled)
    raw = _load_raw(node)
    name = f"lean-proof-{k}"
    raw["checks"] = list(raw.get("checks") or []) + [{"test": "lean_proof/independent_proof", "name": name, "params": {
        "decl": prop["lean_decl"], "approach": approach[:300], "added": time.strftime("%Y-%m-%d", time.gmtime())}}]
    _note(raw, f"proof {k} added from a submitted proposal ({approach[:200]}). " + str(prop.get("notes") or ""))
    _save_raw(node, raw)
    try:
        dag = load_dag(root)
    except Exception as e:  # noqa: BLE001
        return reject(f"the proposal makes the DAG invalid: {e}")
    checks = []
    if run_checks:
        from .runner import plan, run
        records = [r for r in run(dag, plan(dag, node_ids={node.id}), echo=lambda *a, **k: None)]
        checks = [{"name": r["name"], "test": r["test"], "kind": r["kind"], "outcome": r["result"]["outcome"],
                   "grants": r["result"]["grants"], "summary": r["result"]["summary"]} for r in records]
        bad = [c for c in checks if c["outcome"] in ("fail", "error")]
        if bad:
            return reject("checks did not pass: " + "; ".join(f"{c['name']}: {c['summary']}" for c in bad), checks=checks)
        if not any(c["name"] == name and c["outcome"] == "pass" for c in checks):
            return reject(f"{name} did not run", checks=checks)
    if dry_run:
        snap.restore()
    else:
        attempts = src / "attempts.json"
        if attempts.exists():
            dest = root / "dag" / "proposals" / node.id
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(attempts, dest / time.strftime("attempts-%Y%m%dT%H%M%SZ.json", time.gmtime()))
        echo(f"{node.id}: proof {k} added; " + ", ".join(f"{c['name']} {c['outcome']}" for c in checks))
    return {**row, "outcome": "proof_added", "index": k, "reason": approach, "accepted": True, "checks": checks}


def apply(root: Path, in_dir: Path, run_checks: bool = True, echo=print) -> list[dict]:
    rows = []
    for src in sorted(p for p in in_dir.iterdir() if p.is_dir()):
        row = apply_one(root, src.name, src, run_checks=run_checks, echo=echo)
        echo(f"{row['node']}: {row['outcome']}{' — ' + row['reason'] if row.get('reason') else ''}")
        rows.append(row)
    return rows


def feedback(root: Path, src: Path, run_checks: bool = True) -> dict:
    """Exactly what apply-proposals would do, then restore every file: the verifier's verdict on a proposal."""
    node_id = src.name
    try:
        node_id = json.loads((src / "proposal.json").read_text(encoding="utf-8")).get("node") or node_id
    except (OSError, ValueError, AttributeError):
        pass
    return apply_one(root, node_id, src, run_checks=run_checks, dry_run=True, echo=lambda *a, **k: None)


def reproduction_feedback(dag: Dag, node_id: str, results_root: Path) -> dict:
    """A node's reproduction checks evaluated on candidate results (files named like the committed ones, in
    results_root). Expected values still come from the node's own check parameters; nothing is written."""
    from types import SimpleNamespace

    from checks._framework import module
    node = dag.nodes.get(node_id)
    if node is None:
        return {"node": node_id, "error": "unknown node"}
    check = module("reproduction/recorded_value")
    ctx = SimpleNamespace(dag=SimpleNamespace(root=results_root))
    rows = []
    for c in node.checks:
        if c.kind != "reproduction":
            continue
        params = dict(c.params)
        params["results"] = Path(params["results"]).name
        if isinstance(params.get("expect"), dict) and params["expect"].get("results"):
            params["expect"] = dict(params["expect"], results=Path(params["expect"]["results"]).name)
        r = check.run(node, params, ctx)
        ev = r.evidence or {}
        row = {"name": c.name, "outcome": r.outcome, "summary": r.summary, "value": ev.get("value"),
               "expect": ev.get("expect"), "op": params.get("op", "approx"), "rel_tol": params.get("rel_tol", 0.01)}
        # the expected value must be the frozen one: compare with what the committed results give
        frozen = check.run(node, dict(c.params), SimpleNamespace(dag=dag)).evidence or {}
        if frozen.get("expect") is not None and ev.get("expect") is not None and frozen["expect"] != ev["expect"]:
            row.update(outcome="error", summary=f"the candidate's expected value {ev['expect']} differs from the "
                                                f"frozen one {frozen['expect']}; candidates cannot change claims")
        rows.append(row)
    passed = sum(r["outcome"] == "pass" for r in rows)
    return {"node": node_id, "passed": passed, "of": len(rows), "checks": rows}
