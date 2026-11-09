"""
suites.py — a proposal's test suite: what it must contain, what it may contain, and how two suites differ.

    dagtool suite-policy [--json]        the policy (dag/suites/policy.yaml) as data
    dagtool suite-diff OLD NEW           added / removed / tightened / loosened / modified checks between two suites

A suite (proposals/<node>/suite.json) is
    {"claim_type": "<one of the policy's claim types>",
     "checks": [{"kind": "...", "name": "...", "params": {...}, "rationale": "why this check tests the claim"}]}
with predicates for `finite` and `refuter` in proposals/<node>/checks.py, referenced as "checks.py:FUNCTION".

The verifier decides, not the proposer:
  * the fixed Lean checks are always added; every require_one_of group of the claim type must be met;
  * only the claim type's allowed kinds, within the policy's parameter rules;
  * expected values come from a frozen file already in the repository or a held-out value, never a literal;
  * checks.py passes an allow-list scan (no I/O, no dunder access, no eval, only the policy's imports).
suite_diff is the same comparison the Quantum Genesis dashboard uses to hold a revision to its diagnosis
(adding or tightening checks is free; removing, loosening or modifying one needs a person's sign-off).
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import yaml

NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,60}")


def load_policy(root: Path) -> dict:
    return yaml.safe_load((root / "dag" / "suites" / "policy.yaml").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ predicate scan

ALLOWED_NODES = (
    ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.Assign, ast.AugAssign, ast.AnnAssign,
    ast.Expr, ast.If, ast.For, ast.While, ast.Break, ast.Continue, ast.Pass, ast.Assert,
    ast.Import, ast.ImportFrom, ast.alias,
    ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare, ast.IfExp, ast.Call, ast.keyword, ast.Lambda,
    ast.Constant, ast.Name, ast.Load, ast.Store, ast.Attribute, ast.Subscript, ast.Slice, ast.Starred,
    ast.List, ast.Tuple, ast.Set, ast.Dict, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
    ast.comprehension, ast.JoinedStr, ast.FormattedValue,
    ast.And, ast.Or, ast.Not, ast.Invert, ast.UAdd, ast.USub,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.MatMult,
    ast.LShift, ast.RShift, ast.BitOr, ast.BitXor, ast.BitAnd,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot,
)
FORBIDDEN_NAMES = {"eval", "exec", "compile", "open", "input", "__import__", "globals", "locals", "vars",
                   "getattr", "setattr", "delattr", "breakpoint", "memoryview", "help", "exit", "quit", "dir",
                   "type", "object", "super", "classmethod", "staticmethod", "property"}


def scan_python(text: str, imports: list[str]) -> list[str]:
    """Problems that keep a proposal's checks.py from running (empty: allowed)."""
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        return [f"does not parse: {e.msg} (line {e.lineno})"]
    problems = set()
    for n in ast.walk(tree):
        if not isinstance(n, ALLOWED_NODES):
            problems.add(f"uses {type(n).__name__}")
        if isinstance(n, ast.Name) and n.id in FORBIDDEN_NAMES:
            problems.add(f"uses {n.id}")
        if isinstance(n, (ast.Name, ast.Attribute)):
            ident = n.id if isinstance(n, ast.Name) else n.attr
            if ident.startswith("__") or ident.startswith("_"):
                problems.add(f"uses the private name {ident}")
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module or ""]
            for m in mods:
                if m.split(".")[0] not in imports:
                    problems.add(f"imports {m} (allowed: {', '.join(imports)})")
            if isinstance(n, ast.ImportFrom) and n.level:
                problems.add("uses a relative import")
    for f in tree.body:
        if not isinstance(f, (ast.FunctionDef, ast.Import, ast.ImportFrom, ast.Assign, ast.Expr)):
            problems.add(f"top-level {type(f).__name__} (only imports, constants and functions)")
        if isinstance(f, ast.Expr) and not isinstance(f.value, ast.Constant):
            problems.add("runs code at import")
        if isinstance(f, ast.FunctionDef) and f.decorator_list:
            problems.add("uses decorators")
    return sorted(problems)


def functions(text: str) -> set[str]:
    return {f.name for f in ast.parse(text).body if isinstance(f, ast.FunctionDef)}


# ------------------------------------------------------------------ suite validation

def _frozen(root: Path, expect, where: str) -> list[str]:
    """Expected values must be a frozen file already in the repository, or a held-out value."""
    if isinstance(expect, dict) and set(expect) == {"heldout"}:
        return [] if (root / "dag" / "heldout" / f"{expect['heldout']}.json").exists() \
            else [f"{where}: no held-out value {expect['heldout']!r}"]
    if isinstance(expect, dict) and "results" in expect and "path" in expect:
        p = (root / str(expect["results"])).resolve()
        ok = root.resolve() in p.parents and p.exists() and p.suffix == ".json" \
            and str(expect["results"]).split("/")[0] in ("experiments", "dag")
        return [] if ok else [f"{where}: expect.results must be an existing JSON file under experiments/ or dag/"]
    return [f"{where}: expected values come from a frozen file ({{results, path}}) or a held-out value "
            f"({{heldout: ID}}), never from the proposal"]


def validate_suite(root: Path, node_id: str, ns: str, suite, checks_py: str | None) -> tuple[list[str], list[dict]]:
    """(errors, the checks to record). Checks get origin=proposal; predicates point at the stored checks.py."""
    policy = load_policy(root)
    if not isinstance(suite, dict):
        return ["suite.json must be an object"], []
    ct = suite.get("claim_type")
    types = policy["claim_types"]
    if ct not in types:
        return [f"claim_type must be one of {sorted(types)}"], []
    spec = types[ct]
    errs, out, names = [], [], set()
    preds = set()
    if checks_py is not None:
        problems = scan_python(checks_py, policy["predicate_imports"])
        if problems:
            errs.append("checks.py refused: " + "; ".join(problems))
        else:
            preds = functions(checks_py)
    rows = suite.get("checks") or []
    if not isinstance(rows, list):
        return ["suite.checks must be a list"], []
    for i, c in enumerate(rows):
        where = f"check {i + 1}"
        if not isinstance(c, dict):
            errs.append(f"{where}: not an object")
            continue
        kind, name, params = c.get("kind"), c.get("name"), c.get("params") or {}
        where = f"check {name or i + 1} ({kind})"
        if kind in policy["required"]:
            errs.append(f"{where}: the {kind} check is added by the verifier, not the suite")
            continue
        if kind not in spec["allowed"]:
            errs.append(f"{where}: {kind} is not allowed for claim type {ct} (allowed: {spec['allowed']})")
            continue
        if not isinstance(name, str) or not NAME_RE.fullmatch(name) or name in names \
                or name in policy["required"] or name.startswith("lean-proof-"):
            errs.append(f"{where}: name must be unique, lowercase letters, digits, '-' or '_'")
        names.add(name)
        if not str(c.get("rationale") or "").strip():
            errs.append(f"{where}: rationale: say what in the claim this check tests")
        if not isinstance(params, dict):
            errs.append(f"{where}: params must be an object")
            continue
        rule = policy["params"].get(kind, {})
        params = dict(params)
        if kind in ("finite", "refuter"):
            pred = str(params.get("predicate", ""))
            if not pred.startswith("checks.py:") or pred.split(":", 1)[1] not in preds:
                errs.append(f"{where}: predicate must be checks.py:FUNCTION, a function in the proposal's checks.py")
            params["predicate"] = f"checks/papers/{node_id}.py:" + pred.split(":", 1)[-1]
        if kind == "finite":
            size = 1
            for k, v in (params.get("domain") or {}).items():
                if isinstance(v, dict) and "range" in v and len(v["range"]) == 2:
                    size *= max(0, int(v["range"][1]) - int(v["range"][0]) + 1)
                elif isinstance(v, dict) and isinstance(v.get("values"), list):
                    size *= len(v["values"])
                else:
                    errs.append(f"{where}: domain.{k} must be {{range: [lo, hi]}} or {{values: [...]}}")
            if not params.get("domain"):
                errs.append(f"{where}: a finite check needs a domain")
            elif size > rule.get("max_points", 10 ** 6):
                errs.append(f"{where}: the domain has {size} points, more than {rule['max_points']}")
            params.pop("max_points", None)
        if kind == "refuter":
            if params.get("source") != rule.get("source", "hypothesis"):
                errs.append(f"{where}: a proposed refuter uses source: hypothesis")
            n = int(params.get("max_examples", 500))
            if not rule.get("min_examples", 0) <= n <= rule.get("max_examples", 10 ** 6):
                errs.append(f"{where}: max_examples must be in [{rule.get('min_examples')}, {rule.get('max_examples')}]")
            if not params.get("strategy"):
                errs.append(f"{where}: a hypothesis search needs a strategy")
        if kind in ("tool", "reproduction"):
            errs += _frozen(root, params.get("expect"), where)
        if kind == "tool":
            allowed_tools = spec.get("tools")
            if allowed_tools and params.get("tool") not in allowed_tools:
                errs.append(f"{where}: claim type {ct} uses tools {allowed_tools}")
            args = params.get("args") or {}
            if int(args.get("shots", 0)) > rule.get("max_shots", 10 ** 6) \
                    or max([int(args.get("distance", 0))] + [int(d) for d in args.get("distances", [])]) > rule.get("max_distance", 99):
                errs.append(f"{where}: shots ≤ {rule.get('max_shots')} and distance ≤ {rule.get('max_distance')}")
            if not params.get("domain"):
                errs.append(f"{where}: say what the comparison covers in domain")
        if kind == "reproduction":
            res = str(params.get("results", ""))
            if not (root / res).exists() or not res.startswith(("experiments/", "dag/")):
                errs.append(f"{where}: results must be an existing recorded file under experiments/ or dag/")
        if kind == "equivalence":
            for k in ("other", "proof"):
                if not re.fullmatch(re.escape(ns) + r"\.[A-Za-z_][A-Za-z0-9_']*", str(params.get(k, ""))):
                    errs.append(f"{where}: {k} must be a declaration in {ns} (in the proposal's theorem.lean)")
        out.append({"kind": kind, "name": name, "params": params, "origin": "proposal",
                    "rationale": " ".join(str(c.get("rationale") or "").split())[:400]})
    kinds = {c["kind"] for c in out}
    for group in spec.get("require_one_of", []):
        if not kinds & set(group):
            errs.append(f"claim type {ct} needs at least one of {group}")
    return errs, out


# ------------------------------------------------------------------ comparing two suites

def _size(domain) -> int:
    n = 1
    for v in (domain or {}).values():
        if isinstance(v, dict) and "range" in v:
            n *= max(0, int(v["range"][1]) - int(v["range"][0]) + 1)
        elif isinstance(v, dict) and isinstance(v.get("values"), list):
            n *= len(v["values"])
    return n


def _compare(old: dict, new: dict) -> str:
    """tightened | loosened | modified | same, for two versions of one check."""
    if old == new:
        return "same"
    po, pn = old.get("params") or {}, new.get("params") or {}
    if old.get("kind") != new.get("kind"):
        return "modified"
    moves = []
    rest_o, rest_n = dict(po), dict(pn)
    for key, bigger_is_tighter in (("max_examples", True), ("max_points", True), ("rel_tol", False)):
        if key in po or key in pn:
            a, b = po.get(key), pn.get(key)
            rest_o.pop(key, None), rest_n.pop(key, None)
            if a != b and a is not None and b is not None:
                moves.append("tightened" if (b > a) == bigger_is_tighter else "loosened")
            elif a != b:
                moves.append("modified")
    if "domain" in po or "domain" in pn:
        a, b = _size(po.get("domain")), _size(pn.get("domain"))
        rest_o.pop("domain", None), rest_n.pop("domain", None)
        if po.get("domain") != pn.get("domain"):
            moves.append("tightened" if b > a and _contains(pn.get("domain"), po.get("domain")) else
                         "loosened" if b < a and _contains(po.get("domain"), pn.get("domain")) else "modified")
    args_o, args_n = (rest_o.pop("args", {}) or {}), (rest_n.pop("args", {}) or {})
    if args_o != args_n:
        if set(args_o) == set(args_n) and all(args_o[k] == args_n[k] for k in args_o if k != "shots"):
            moves.append("tightened" if args_n["shots"] > args_o["shots"] else "loosened")
        else:
            moves.append("modified")
    if rest_o != rest_n:
        moves.append("modified")
    if "modified" in moves or ("loosened" in moves and "tightened" in moves):
        return "modified"
    return moves[0] if moves else "same"


def _axis(v) -> set:
    vals = range(int(v["range"][0]), int(v["range"][1]) + 1) if "range" in v else v.get("values", [])
    return {json.dumps(x) for x in vals}


def _contains(big, small) -> bool:
    """Every point of domain `small` is in domain `big` (same variables, each axis a subset)."""
    big, small = big or {}, small or {}
    return set(big) == set(small) and all(_axis(small[k]) <= _axis(big[k]) for k in big)


def suite_diff(old: dict | None, new: dict | None) -> dict:
    old_checks = {c.get("name"): c for c in (old or {}).get("checks") or []}
    new_checks = {c.get("name"): c for c in (new or {}).get("checks") or []}
    out = {"added": sorted(set(new_checks) - set(old_checks)), "removed": sorted(set(old_checks) - set(new_checks)),
           "tightened": [], "loosened": [], "modified": [], "unchanged": []}
    for name in sorted(set(old_checks) & set(new_checks)):
        a = {k: v for k, v in old_checks[name].items() if k != "rationale"}
        b = {k: v for k, v in new_checks[name].items() if k != "rationale"}
        verdict = _compare(a, b)
        out["unchanged" if verdict == "same" else verdict].append(name)
    if (old or {}).get("claim_type") != (new or {}).get("claim_type"):
        out["modified"].append("claim_type")
    out["needs_signoff"] = bool(out["removed"] or out["loosened"] or out["modified"])
    return out
