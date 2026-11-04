"""
proposals.py — the verifier's side of a proposal: describe open theorems, give feedback, apply what passes.

    dagtool open-theorems [--json] [--count] [--node ID]   what is open, and what a proposal for it must look like
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

What a proposal can and cannot do:
  * It may write one Lean file at the node's own path and propose dependency edges to existing nodes.
  * It may not choose checks, tolerances or expected values. The checks for a formalized theorem are fixed here
    (lean, vocabulary, nonvacuity); `extra_checks` is rejected.
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
PROPOSAL_FILES = ("proposal.json", "theorem.lean", "attempts.json")
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
        "checks_run": ["lean", "vocabulary", "nonvacuity"],
        "proposal_format": {
            "directory": f"proposals/{node.id}/",
            "files": {"proposal.json": "required", "theorem.lean": "required when outcome is formalized",
                      "attempts.json": "optional record of every attempt and its rationale"},
            "proposal.json": {"node": node.id, "outcome": list(OUTCOMES), "reason": "text",
                              "lean_decl": f"{ns}.<theorem name>", "witness": f"{ns}.<witness name> or null",
                              "depends_on": [{"node": "<existing node id>", "kind": "uses | assumes | instantiates",
                                              "note": "text"}],
                              "statement_tex": "LaTeX or null", "notes": "text"},
            "lean_forbidden": [why for _, why in FORBIDDEN_LEAN],
        },
    }


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
    from verification.truth.lean.leanrun import lake
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

    def __init__(self, root: Path, node: Node, lean_file: Path):
        self.root = root
        self.files = {node.path: node.path.read_text(encoding="utf-8"),
                      root / "lean" / "MBQC.lean": (root / "lean" / "MBQC.lean").read_text(encoding="utf-8")}
        self.lean = root / lean_file
        self.lean_before = self.lean.read_text(encoding="utf-8") if self.lean.exists() else None
        self.evidence = root / "dag" / "evidence" / node.id
        self.evidence_before = {p: p.read_bytes() for p in self.evidence.rglob("*") if p.is_file()} \
            if self.evidence.exists() else None

    def restore(self) -> None:
        for p, text in self.files.items():
            p.write_text(text, encoding="utf-8")
        if self.lean_before is None:
            self.lean.unlink(missing_ok=True)
        else:
            self.lean.write_text(self.lean_before, encoding="utf-8")
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

    # apply: the Lean file, the import, the node's fixed checks and the proposed edges (never its statement)
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
    raw["lean_decl"] = prop["lean_decl"]
    deps = [{k: v for k, v in {"node": d["node"], "kind": d.get("kind", "uses"), "note": d.get("note")}.items() if v}
            for d in prop.get("depends_on") or []]
    if deps:
        raw["depends_on"] = deps
    raw["checks"] = [{"kind": "lean"}, {"kind": "vocabulary"},
                     {"kind": "nonvacuity", "params": {"witness": prop["witness"]}} if prop.get("witness") else {"kind": "nonvacuity"}]
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
    checks = [{"name": r["name"], "kind": r["kind"], "outcome": r["result"]["outcome"], "grants": r["result"]["grants"],
               "summary": r["result"]["summary"]} for r in records]
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

    from verification.base import load_all
    node = dag.nodes.get(node_id)
    if node is None:
        return {"node": node_id, "error": "unknown node"}
    check = load_all()["reproduction"]()
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
