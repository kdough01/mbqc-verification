"""
predicates.py — load a predicate function a node names as FILE.py:FUNCTION, and call it on one point.

Shared by finite/exhaustive and refuter/hypothesis. The file must be listed under the node's `code:` (so a
change to it makes the evidence stale) and is compiled from source each time (no __pycache__ in the repository,
never a stale copy). A predicate takes one keyword argument per variable and returns a bool, or (bool, detail).
"""

from __future__ import annotations

import sys
import types
from pathlib import Path


def load_predicate(node, spec: str, root: Path):
    """The predicate named FILE.py:FUNCTION, from a file the node lists under `code:`."""
    if ":" not in str(spec):
        raise ValueError("predicate must be FILE.py:FUNCTION")
    file, fn = str(spec).rsplit(":", 1)
    if file not in node.code:
        raise ValueError(f"{file} must be listed under the node's code: (so changes to it re-run the check)")
    path = (root / file).resolve()
    if root.resolve() not in path.parents or path.suffix != ".py" or not path.exists():
        raise ValueError(f"{file} is not a Python file in the repository")
    name = "_predicate_" + "_".join(Path(file).with_suffix("").parts).replace(".", "_")
    mod = types.ModuleType(name)
    mod.__file__ = str(path)
    sys.modules[name] = mod
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), mod.__dict__)  # noqa: S102 - repository code
    return getattr(mod, fn)


def call(pred, point: dict) -> tuple[bool, object]:
    r = pred(**point)
    return (bool(r[0]), r[1]) if isinstance(r, tuple) else (bool(r), None)
