"""
leanrun.py — build the Lean project and inspect declarations, once per dagtool run.

Shared by the lean, vocabulary, nonvacuity and differential checks. Needs `lake`
on PATH (or in ~/.elan/bin): install elan, and it fetches the toolchain pinned in
lean/lean-toolchain.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

STANDARD_AXIOMS = {"propext", "Quot.sound", "Classical.choice"}
ASSUMPTION_NAMESPACE = "MBQC.Assumptions."


class LeanUnavailable(RuntimeError):
    pass


def lake() -> str:
    exe = shutil.which("lake") or str(Path.home() / ".elan" / "bin" / "lake")
    if not Path(exe).exists() and not shutil.which(exe):
        raise LeanUnavailable("`lake` not found: install elan (https://github.com/leanprover/elan), "
                              "which fetches the toolchain pinned in lean/lean-toolchain")
    return exe


def _run(args: list[str], cwd: Path, stdin: str | None = None, timeout: int = 3600) -> subprocess.CompletedProcess:
    env = dict(os.environ, ELAN_NO_OVERRIDE_NOTICE="1")
    return subprocess.run(args, cwd=cwd, input=stdin, capture_output=True, text=True, timeout=timeout, env=env)


def build(ctx) -> dict:
    """`lake build` (library and the counts executable), cached for the run."""
    if "lean_build" not in ctx.cache:
        root = ctx.root / "lean"
        p = _run([lake(), "build", "MBQC", "mbqc_counts"], root)
        ctx.cache["lean_build"] = {"ok": p.returncode == 0, "log": (p.stdout + p.stderr)[-4000:]}
    return ctx.cache["lean_build"]


def node_prefixes(dag) -> dict[str, str]:
    """{lean name or namespace: node id} for every node that names Lean declarations."""
    return {name: nid for nid, n in dag.nodes.items() for name in n.lean_names}


def inspect(ctx) -> dict[str, dict]:
    """Inspect every node's main declaration and every witness, cached for the run."""
    if "lean_inspect" in ctx.cache:
        return ctx.cache["lean_inspect"]
    b = build(ctx)
    if not b["ok"]:
        raise RuntimeError("lake build failed:\n" + b["log"])
    dag = ctx.dag
    decls = {n.lean_decl for n in dag.nodes.values() if n.lean_decl and n.kind not in ("definition", "assumption")}
    decls |= {c.params["witness"] for n in dag.nodes.values() for c in n.checks if c.params.get("witness")}
    lines = [f"decl {d}" for d in sorted(decls)] + [f"stop {p}" for p in sorted(node_prefixes(dag))]
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
        req = f.name
    try:
        env_args = [lake(), "env", "lean", "scripts/Inspect.lean"]
        p = subprocess.run(env_args, cwd=ctx.root / "lean", capture_output=True, text=True, timeout=1800,
                           env=dict(os.environ, MBQC_INSPECT=req, ELAN_NO_OVERRIDE_NOTICE="1"))
    finally:
        os.unlink(req)
    if p.returncode != 0:
        raise RuntimeError("Lean inspection failed:\n" + (p.stdout + p.stderr)[-4000:])
    out = {}
    for line in p.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            d = json.loads(line)
            out[d["name"]] = d
    ctx.cache["lean_inspect"] = out
    return out


def owner(name: str, prefixes: dict[str, str]) -> str | None:
    """The node whose Lean names cover `name` (longest matching prefix)."""
    best = None
    for p, nid in prefixes.items():
        if name == p or name.startswith(p + "."):
            if best is None or len(p) > len(best[0]):
                best = (p, nid)
    return best[1] if best else None


def counts_exe(ctx) -> Path:
    if not build(ctx)["ok"]:
        raise RuntimeError("lake build failed:\n" + build(ctx)["log"])
    exe = ctx.root / "lean" / ".lake" / "build" / "bin" / ("mbqc_counts.exe" if os.name == "nt" else "mbqc_counts")
    if not exe.exists():
        raise RuntimeError(f"{exe} missing after lake build")
    return exe


def run_counts(ctx, lines: list[str]) -> list[tuple[int, int, int]]:
    """Lean's (N, E, M) for each J/CZ stream line."""
    p = _run([str(counts_exe(ctx))], ctx.root / "lean", stdin="\n".join(lines) + "\n", timeout=1800)
    if p.returncode != 0:
        raise RuntimeError(p.stderr[-2000:])
    rows = p.stdout.split("\n")
    out = []
    for r in rows[: len(lines)]:
        if r.strip() == "error":
            raise RuntimeError("mbqc_counts could not parse a stream")
        a, b, c = (int(x) for x in r.split())
        out.append((a, b, c))
    return out
