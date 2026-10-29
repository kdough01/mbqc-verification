"""
base.py — the interface every check implements, and the registry dagtool runs.

A check looks at one node (plus its parameters from the node's YAML) and
returns a CheckResult. dagtool stamps it with the input hash and provenance,
clamps its grant to the kind's ceiling (verification/kinds.py), and writes it
to dag/evidence/<node>/<name>.json. Checks never edit nodes or set status.
"""

from __future__ import annotations

import inspect
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from .kinds import CHECK_KINDS

if TYPE_CHECKING:
    from dagtool.model import Dag, Node

Outcome = Literal["pass", "fail", "error", "skip"]


@dataclass
class CheckResult:
    outcome: Outcome
    grants: str | None = None          # truth: empirical | bounded | proved_modulo | proved | assumed | refuted
    domain: str | None = None          # e.g. "n in {2,3,4,5}, D in {3,5,7,9}"
    frontier: list[str] = field(default_factory=list)
    summary: str = ""                  # one line for humans
    evidence: dict[str, Any] = field(default_factory=dict)
    seed: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RunContext:
    dag: "Dag"
    quick: bool = False                # smaller grids where a check supports it
    cache: dict = field(default_factory=dict)   # shared across checks in one run

    @property
    def root(self) -> Path:
        return self.dag.root


class Check:
    """Subclass, set `kind`, implement `run`, and decorate with @register."""
    kind: ClassVar[str]

    def applies_to(self, node: "Node") -> bool:
        return True

    def run(self, node: "Node", params: dict, ctx: RunContext) -> CheckResult:
        raise NotImplementedError

    # ---- helpers ---------------------------------------------------------
    @classmethod
    def question(cls) -> str:
        return CHECK_KINDS[cls.kind].question

    @classmethod
    def source_files(cls) -> list[Path]:
        """Files whose contents decide this check's verdict (hashed into evidence)."""
        return [Path(inspect.getfile(cls)).resolve()]


REGISTRY: dict[str, type[Check]] = {}


def register(cls: type[Check]) -> type[Check]:
    if cls.kind not in CHECK_KINDS:
        raise ValueError(f"unknown check kind {cls.kind!r}; add it to verification/kinds.py")
    if cls.kind in REGISTRY:
        raise ValueError(f"two implementations registered for {cls.kind!r}")
    REGISTRY[cls.kind] = cls
    return cls


def load_all() -> dict[str, type[Check]]:
    """Import every check module so it registers itself."""
    import importlib
    import pkgutil

    import verification
    for mod in pkgutil.walk_packages(verification.__path__, "verification."):
        if mod.name.rsplit(".", 1)[-1] not in ("base", "kinds"):
            importlib.import_module(mod.name)
    return REGISTRY


class Timer:
    def __enter__(self):
        self.t0 = time.time()
        return self

    def __exit__(self, *exc):
        self.seconds = round(time.time() - self.t0, 2)
