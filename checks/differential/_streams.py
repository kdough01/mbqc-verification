"""
_streams.py — Graphix's J/CZ streams as text the Lean `mbqc_counts` executable reads (lean/Main.lean).

A stream line is `<width> J:q C:a:b ...`; a gate line is `G cnot:c:t h:q ...` (argument order of the Lean
constructors in lean/MBQC/Defs/GraphixGates.lean).
"""

from __future__ import annotations

import numpy as np
from graphix import instruction as gi
from graphix.transpiler import instructions_to_jcz

from mbqc_verify.compilers.graphix import pattern_stats, to_graphix_circuit
from mbqc_verify.hamsim.analysis import generic_circuit


def jcz_tokens(instructions) -> list[str]:
    """Graphix's J/CZ stream as `J:q` / `C:a:b` tokens (global phases dropped)."""
    toks = []
    for ins in instructions_to_jcz(instructions):
        kind = ins.kind.name
        if kind == "J":
            toks.append(f"J:{ins.target}")
        elif kind == "CZ":
            a, b = ins.targets
            toks.append(f"C:{a}:{b}")
        elif kind != "GPHASE":
            raise ValueError(f"unexpected instruction {kind} in the J/CZ stream")
    return toks


def gate_token(ins) -> str:
    """A Graphix instruction as the Lean `G` token (argument order of the Lean constructor)."""
    k = ins.kind.name
    if k in ("CNOT", "RZZ"):
        return f"{k.lower()}:{ins.control}:{ins.target}"
    if k == "CZ":
        return f"cz:{ins.targets[0]}:{ins.targets[1]}"
    if k == "CCX":
        return f"ccx:{ins.controls[0]}:{ins.controls[1]}:{ins.target}"
    if k in ("H", "X", "RX", "RY", "RZ", "U"):
        return f"{k.lower()}:{ins.target}"
    raise ValueError(f"gate {k} is not in the Lean model (MBQC.Defs.Gate)")


def single_gates() -> list[tuple[str, list]]:
    """Every gate kind of the Lean model, on several qubit orders, with generic angles."""
    a, b, c = 0.37, -1.21, 2.05
    out = []
    for p, q in ((0, 1), (1, 0), (2, 0), (1, 3)):
        out += [(f"cnot {p},{q}", [gi.CNOT(target=q, control=p)]), (f"cz {p},{q}", [gi.CZ(targets=(p, q))]),
                (f"rzz {p},{q}", [gi.RZZ(target=q, control=p, angle=a)])]
    for p, q, r in ((0, 1, 2), (2, 0, 1), (1, 2, 0), (3, 0, 2)):
        out.append((f"ccx {p},{q},{r}", [gi.CCX(target=r, controls=(p, q))]))
    for q in (0, 2):
        out += [(f"h {q}", [gi.H(target=q)]), (f"x {q}", [gi.X(target=q)]), (f"rx {q}", [gi.RX(target=q, angle=a)]),
                (f"ry {q}", [gi.RY(target=q, angle=b)]), (f"rz {q}", [gi.RZ(target=q, angle=c)]),
                (f"u {q}", [gi.U(target=q, theta=a, phi=b, lambda_=c)])]
    return out


def circuit_instructions(method: str, n: int, k: int) -> list:
    hc = generic_circuit(method, n, k, np.random.default_rng(1000 * n + k))
    return list(to_graphix_circuit(hc.circuit).instruction)


def stream_and_counts(method: str, n: int, k: int, cache: dict) -> tuple[str, tuple[int, int, int]]:
    """One J/CZ stream line for Lean, and Graphix's (N, E, M) of the unoptimized pattern."""
    key = ("jcz", method, n, k)
    if key not in cache:
        hc = generic_circuit(method, n, k, np.random.default_rng(1000 * n + k))
        gc = to_graphix_circuit(hc.circuit)
        line = " ".join([str(gc.width)] + jcz_tokens(gc.instruction))
        s = pattern_stats(gc.transpile().pattern)
        cache[key] = (line, (s["total_nodes"], s["edges (CZ)"], s["measurements"]))
    return cache[key]
