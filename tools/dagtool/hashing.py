"""
hashing.py — statement hashes (what a review pins) and input hashes (what
evidence pins). Line endings are normalized, so a Windows checkout with CRLF
files hashes the same as a Linux CI runner.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from .model import Dag, Node


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=None)
def file_hash(path: Path) -> str:
    """sha256 of a file with CRLF -> LF; 'missing' if it does not exist."""
    if not path.exists():
        return "missing"
    return _sha(path.read_bytes().replace(b"\r\n", b"\n"))


def tree_hash(directory: Path, pattern: str) -> str:
    if not directory.exists():
        return "missing"
    parts = [f"{p.relative_to(directory).as_posix()}:{file_hash(p)}"
             for p in sorted(directory.rglob(pattern)) if ".lake" not in p.parts]
    return _sha("\n".join(parts).encode())


def statement_hash(node: Node) -> str:
    """What a reviewer approved. Changing any of these voids the review."""
    payload = {
        "id": node.id,
        "kind": node.kind,
        "statement": node.statement.strip(),
        "statement_tex": (node.statement_tex or "").strip(),
        "lean_decl": node.lean_names,
        "conventions": node.conventions.as_dict(),
        "assumptions": sorted(node.assumptions),
    }
    return _sha(json.dumps(payload, sort_keys=True).encode())[:16]


def input_hash(dag: Dag, node: Node, check_params: dict, check_files: list[Path] = (),
               uses_lean: bool = False) -> tuple[str, dict]:
    """Hash of everything a check's verdict on `node` depends on, plus its parts.

    Parts: the statement, the statements of every definition it rests on and of
    its direct parents (with their check parameters), the
    code files it names, the check's parameters and implementation, the pinned
    Python requirements, and (for Lean nodes) the Lean sources and toolchain.
    """
    root = dag.root
    defs = sorted(a for a in dag.ancestors(node.id) if dag.nodes[a].kind == "definition")
    parts = {
        "statement": statement_hash(node),
        "definitions": {d: statement_hash(dag.nodes[d]) for d in defs},
        # direct parents: their statements and check parameters (some checks read a parent's formula)
        "parents": {e.src: statement_hash(dag.nodes[e.src]) + ":" + _sha(json.dumps(
            [c.params for c in dag.nodes[e.src].checks], sort_keys=True).encode())[:8]
            for e in dag.parents(node.id)},
        "code": {c: file_hash(root / c) for c in sorted(node.code)},
        "check_params": _sha(json.dumps(check_params, sort_keys=True).encode())[:16],
        "check_code": {p.relative_to(root).as_posix(): file_hash(p) for p in sorted(check_files)},
        "requirements": file_hash(root / "requirements.txt"),
    }
    if node.lean_decl or uses_lean:
        parts["lean_sources"] = tree_hash(root / "lean", "*.lean")
        parts["lean_toolchain"] = file_hash(root / "lean" / "lean-toolchain")
    return _sha(json.dumps(parts, sort_keys=True).encode())[:16], parts
