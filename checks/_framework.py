"""
_framework.py — what a test in checks/ is, and how dagtool finds, validates and runs one.

A test is one file, checks/<type>/<name>.py, and its id is "<type>/<name>". The folder is the test's type
(scaling, lean, numerical, ...): it decides the question the test answers and the highest status a pass may
grant (checks/_kinds.py). A node runs a test by naming it:

    checks:
    - test: scaling/bilinear_formula
      params: {method: qsvt, compiler: graphix, quantity: N, coef: [294, -144, 362, -30]}
      name: optional evidence file stem (defaults to the type; needed when a node runs a type twice)

Every test file has the same shape:

    \"\"\"<type>/<name> — one-line summary.

    What it checks      the claim the test tests, in words
    How it works        the steps, enough to reproduce the test by hand
    Parameters          one entry per key of PARAMS
    Passes when         ...
    Fails when          ...
    Grants              the status a pass gives (and what a failure means)
    Example             a node's checks: entry, as YAML (it is validated)
    [Cost, Limits, Notes, See also]   optional
    \"\"\"
    PARAMS = {...}      JSON-schema properties of the node's params (a literal: read without importing)
    REQUIRED = [...]    the params that must be given
    def applies_to(node) -> bool      optional: False makes the run a skip
    def run(node, params, ctx) -> Result

Files starting with "_" are helpers, not tests: checks/<type>/_x.py for one type, checks/_shared/ for several.
The evidence of a run pins the test file and every helper it imports (source_files), so changing any of them
makes that evidence stale. Copy checks/_template.py to start a test; tests/test_check_files.py enforces the
shape, and `dagtool readmes` regenerates each folder's README table from the docstrings.
"""

from __future__ import annotations

import ast
import importlib
import re
import textwrap
import time
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from ._kinds import CHECK_KINDS

if TYPE_CHECKING:
    from dagtool.model import Dag, Node

CHECKS_DIR = Path(__file__).resolve().parent
ROOT = CHECKS_DIR.parent
TEST_ID = re.compile(r"[a-z][a-z0-9_]*/[a-z][a-z0-9_]*")

REQUIRED_SECTIONS = ("What it checks", "How it works", "Parameters", "Passes when", "Fails when", "Grants", "Example")
OPTIONAL_SECTIONS = ("Cost", "Limits", "Notes", "See also")
SECTIONS = REQUIRED_SECTIONS + OPTIONAL_SECTIONS

Outcome = Literal["pass", "fail", "error", "skip"]


@dataclass
class Result:
    """What a test returns. dagtool stamps it with the input hash and provenance and writes it as evidence."""
    outcome: Outcome
    grants: str | None = None          # truth: empirical | bounded | proved_modulo | proved | assumed | refuted
    domain: str | None = None          # what the verdict covers, e.g. "n in {2,3,4,5}, D in {3,5,7,9}"
    frontier: list[str] = field(default_factory=list)
    summary: str = ""                  # one line for people
    evidence: dict[str, Any] = field(default_factory=dict)
    seed: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


CheckResult = Result   # the older name


@dataclass
class Context:
    """Shared by every test in one dagtool run."""
    dag: "Dag"
    quick: bool = False                # smaller grids where a test supports it
    cache: dict = field(default_factory=dict)

    @property
    def root(self) -> Path:
        return self.dag.root


RunContext = Context   # the older name


# ------------------------------------------------------------------ the docstring contract

def parse_docstring(doc: str) -> tuple[str, str, dict[str, str]]:
    """(header id, one-line summary, {section: dedented text}) of a test's docstring."""
    lines = textwrap.dedent(doc or "").strip("\n").splitlines()
    head = lines[0].strip() if lines else ""
    m = re.match(r"([a-z0-9_]+/[a-z0-9_]+)\s+[—-]\s+(.+)", head)
    header, summary = (m.group(1), m.group(2).strip()) if m else ("", head)
    sections: dict[str, list[str]] = {}
    current = None
    for line in lines[1:]:
        if line and not line[0].isspace() and line.strip() in SECTIONS:
            current = line.strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return header, summary, {k: textwrap.dedent("\n".join(v)).strip() for k, v in sections.items()}


def first_sentence(text: str) -> str:
    flat = " ".join(text.split())
    m = re.match(r"(.+?[.!?])(\s|$)", flat)
    return m.group(1) if m else flat


@dataclass
class CheckInfo:
    """A test as read from its file, without importing it."""
    id: str
    type: str
    name: str
    path: Path
    header: str
    summary: str
    sections: dict[str, str]
    params: dict
    required: list[str]

    def problems(self) -> list[str]:
        """What keeps this file from following the contract (empty: it does)."""
        out = []
        if self.header != self.id:
            out.append(f"the docstring must start with '{self.id} — <summary>'")
        if not self.summary:
            out.append("the docstring needs a one-line summary after the id")
        for s in REQUIRED_SECTIONS:
            if not self.sections.get(s):
                out.append(f"missing docstring section '{s}'")
        documented = self.sections.get("Parameters", "")
        for p in self.params:
            if not re.search(rf"(^|\s){re.escape(p)}(\s|:|$)", documented, re.M):
                out.append(f"parameter {p!r} is not described under 'Parameters'")
        for p in self.required:
            if p not in self.params:
                out.append(f"REQUIRED names {p!r}, which PARAMS does not define")
        if self.type not in CHECK_KINDS:
            out.append(f"folder {self.type!r} is not a test type (checks/_kinds.py)")
        return out

    def examples(self) -> list[dict]:
        """The checks: entries of the Example section."""
        import yaml
        data = yaml.safe_load(self.sections.get("Example", "")) or []
        return data if isinstance(data, list) else [data]


def _literal(tree: ast.Module, name: str, default):
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(t, ast.Name) and t.id == name for t in targets) and node.value is not None:
            return ast.literal_eval(node.value)
    return default


def read_test(path: Path) -> CheckInfo:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    header, summary, sections = parse_docstring(ast.get_docstring(tree) or "")
    t, n = path.parent.name, path.stem
    return CheckInfo(id=f"{t}/{n}", type=t, name=n, path=path, header=header, summary=summary, sections=sections,
                    params=_literal(tree, "PARAMS", {}), required=list(_literal(tree, "REQUIRED", [])))


def check_files(checks_dir: Path = CHECKS_DIR) -> list[Path]:
    return sorted(p for p in checks_dir.glob("*/*.py")
                  if not p.name.startswith("_") and not p.parent.name.startswith("_"))


@lru_cache(maxsize=None)
def discover(checks_dir: Path = CHECKS_DIR) -> dict[str, CheckInfo]:
    """Every test in checks/, by id (read, not imported: listing tests needs no heavy dependencies)."""
    return {info.id: info for info in map(read_test, check_files(checks_dir))}


def info(test_id: str) -> CheckInfo:
    tests = discover()
    if test_id not in tests:
        raise KeyError(f"no test {test_id!r}: expected a file checks/{test_id}.py (see `dagtool tests`)")
    return tests[test_id]


def kind_of(test_id: str) -> str:
    """A test's type: the folder it is in."""
    return test_id.split("/", 1)[0]


def validate(test_id: str, params: dict) -> list[str]:
    """Problems with a node's params for this test (empty: they are valid)."""
    import jsonschema
    t = info(test_id)
    schema = {"type": "object", "properties": t.params, "required": t.required, "additionalProperties": False}
    v = jsonschema.Draft202012Validator(schema)
    return [f"{'.'.join(map(str, e.absolute_path)) or 'params'}: {e.message}"
            for e in sorted(v.iter_errors(params or {}), key=lambda e: list(e.absolute_path))]


@lru_cache(maxsize=None)
def module(test_id: str):
    info(test_id)
    return importlib.import_module("checks." + test_id.replace("/", "."))


# ------------------------------------------------------------------ what a test's verdict depends on

def _imports(path: Path) -> set[Path]:
    """checks/ modules a file imports (absolute `checks.x.y` or relative), as file paths."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    pkg = path.parent.relative_to(ROOT).parts
    out = set()
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base = list(pkg[: len(pkg) - node.level + 1])
                mod = base + (node.module.split(".") if node.module else [])
            else:
                mod = (node.module or "").split(".")
            names = [mod + [a.name] for a in node.names] + [mod]
        elif isinstance(node, ast.Import):
            names = [a.name.split(".") for a in node.names]
        for parts in names:
            if not parts or parts[0] != "checks":
                continue
            for cand in (ROOT.joinpath(*parts).with_suffix(".py"), ROOT.joinpath(*parts, "__init__.py")):
                if cand.exists() and cand.name not in ("_framework.py", "_kinds.py") \
                        and cand.parent != CHECKS_DIR and cand.name != "__init__.py":
                    out.add(cand)
    return out


@lru_cache(maxsize=None)
def source_files(test_id: str) -> tuple[Path, ...]:
    """The test's file and every checks/ helper it imports, transitively (hashed into its evidence)."""
    seen, todo = set(), [info(test_id).path]
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        seen.add(p)
        todo += sorted(_imports(p) - seen)
    return tuple(sorted(seen))


# ------------------------------------------------------------------ running one

def run(test_id: str, node: "Node", params: dict, ctx: Context) -> Result:
    """Validate params, then run the test (a crash or invalid params is an `error` result, never an exception)."""
    import traceback
    bad = validate(test_id, params)
    if bad:
        return Result("error", summary=f"{test_id}: invalid params: {'; '.join(bad)}")
    mod = module(test_id)
    applies = getattr(mod, "applies_to", None)
    if applies is not None and not applies(node):
        return Result("skip", summary=f"{test_id} does not apply to this node")
    try:
        return mod.run(node, dict(params or {}), ctx)
    except Exception as e:  # a crashing test is evidence too
        return Result("error", summary=f"{type(e).__name__}: {e}", evidence={"traceback": traceback.format_exc(limit=8)})


class Timer:
    def __enter__(self):
        self.t0 = time.time()
        return self

    def __exit__(self, *exc):
        self.seconds = round(time.time() - self.t0, 2)
