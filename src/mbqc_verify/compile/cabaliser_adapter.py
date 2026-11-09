"""
cabaliser_adapter.py — compile a Qiskit circuit with Cabaliser and count the graph state.

Two halves, so that each runs where its dependencies are:

  * `clifford_rz_ops(qc)` (verifier environment, needs Qiskit): transpile to
    Clifford + Rz (level 1) and list the gates. Rz by a multiple of π/2 is
    Clifford (I, S, Z, S†) and is passed as such, so only genuine rotations
    cost Cabaliser a measured vertex; this is the fairest input Cabaliser can get.
  * `cabaliser_counts(width, ops)` (the pinned RRE environment, needs Cabaliser):
    one widget for the whole circuit, inputs teleported in (Cabaliser's default),
    decomposed; returns N (graph vertices), E (graph edges), M (measured
    vertices = vertices that are not outputs), and Cabaliser's own time and space.

`compile_counts(qc)` runs the first half here and the second in the RRE
environment's Python (CABALISER_PYTHON, default .rre/venv/bin/python) as a
subprocess: `python -m mbqc_verify.compile.cabaliser_adapter` reads
{"width", "ops"} as JSON on stdin and prints the counts.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

BASIS = ["h", "s", "sdg", "x", "y", "z", "cx", "cz", "rz"]
REPO = Path(__file__).resolve().parents[3]


def clifford_rz_ops(qc) -> tuple[int, list[list]]:
    """(width, [[gate, qubits, angle or None], ...]) of qc after Qiskit's transpiler to Clifford + Rz."""
    from qiskit import transpile
    t = transpile(qc.remove_final_measurements(inplace=False), basis_gates=BASIS, optimization_level=1)
    ops = []
    for inst in t.data:
        name = inst.operation.name
        qs = [t.find_bit(q).index for q in inst.qubits]
        if name in ("barrier", "delay"):
            continue
        if name == "rz":
            theta = float(inst.operation.params[0])
            quarter = theta / (math.pi / 2)
            if abs(quarter - round(quarter)) < 1e-12:      # Clifford: I, S, Z, S† (up to global phase)
                gate = ("i", "s", "z", "sdg")[round(quarter) % 4]
                if gate != "i":
                    ops.append([gate, qs, None])
                continue
            ops.append(["rz", qs, theta])
        elif name in BASIS:
            ops.append([name, qs, None])
        else:
            raise ValueError(f"gate {name} left after transpiling to {BASIS}")
    return t.num_qubits, ops


def _widget(width: int, ops: list[list]):
    """Cabaliser's compiled widget as a dict (wid.json()), and the angle of each Rz tag."""
    from cabaliser import gates
    from cabaliser.operation_sequence import OperationSequence
    from cabaliser.widget import Widget
    table = {"h": gates.H, "s": gates.S, "sdg": gates.Sdag, "x": gates.X, "y": gates.Y, "z": gates.Z,
             "cx": gates.CNOT, "cz": gates.CZ}
    seq = OperationSequence(len(ops))
    angles = {0: 0.0}                          # tag 0: no rotation
    for name, qs, theta in ops:
        if name == "rz":
            tag = len(angles)                      # one tag per rotation: tag i is the i-th Rz
            angles[tag] = theta
            seq.append(gates.RZ, qs[0], tag)
        else:
            seq.append(table[name], *qs)
    wid = Widget(width, 2 * width + len(angles) + 8)
    wid(seq)
    wid.decompose()
    return wid.json(), angles


def cabaliser_counts(width: int, ops: list[list]) -> dict:
    """Compile with Cabaliser and count (runs in the RRE environment)."""
    obj, angles = _widget(width, ops)
    n_rz = len(angles) - 1
    adj = obj["adjacencies"]
    n = int(obj["n_qubits"])
    edges = sum(len(v) for v in adj.values()) // 2
    outputs = len(obj["outputnodes"])
    return {"N": n, "E": edges, "M": n - outputs, "space": int(obj["space"]), "time": int(obj["time"]),
            "rotations": n_rz, "inputs": width}


def simulate(obj: dict, angles: dict, psi):
    """The compiled graph state applied to input psi (big-endian, qubit 0 first), on the post-selected branch.

    Cabaliser's local_simulator semantics (simulate_dict_as_widget), as a statevector instead of dense matrices:
    inputs ⊗ |+>^N; CZ on every graph edge; each input i is joined to graph qubit i by a CZ and measured in X;
    local Cliffords; Rz(angle of tag) on each graph qubit; every scheduled non-output qubit is measured in X; the
    outputs, in `outputnodes` order, carry the result. Each X measurement keeps the + outcome."""
    import numpy as np
    from cabaliser import local_simulator as ls
    n_in, N = len(obj["statenodes"]), int(obj["n_qubits"])
    T = n_in + N
    st = np.asarray(psi, dtype=np.complex128).reshape((2,) * n_in)
    plus = np.full(2, 2 ** -0.5, dtype=np.complex128)
    for _ in range(N):
        st = np.multiply.outer(st, plus)

    def sl(axis, bit):
        idx = [slice(None)] * T
        idx[axis] = bit
        return tuple(idx)

    def cz(a, b):
        idx = [slice(None)] * T
        idx[a], idx[b] = 1, 1
        st[tuple(idx)] *= -1

    def one(axis, U):
        nonlocal st
        st = np.moveaxis(np.tensordot(U, st, axes=([1], [axis])), 0, axis)

    def measure_plus(axis):                       # project on |+>, then H: |+> -> |0>
        v = (st[sl(axis, 0)] + st[sl(axis, 1)]) * 2 ** -0.5
        st[sl(axis, 0)] = v
        st[sl(axis, 1)] = 0

    for a, nbrs in obj["adjacencies"].items():
        for b in nbrs:
            if b > int(a):
                cz(n_in + int(a), n_in + b)
    for i in range(n_in):
        cz(i, n_in + i)
        measure_plus(i)
    for g, name in enumerate(obj["local_cliffords"]):
        one(n_in + g, np.asarray(ls.LOCAL_CLIFFORD_TABLE[name], dtype=np.complex128))
    for g, tag in enumerate(obj["measurement_tags"]):
        if angles.get(int(tag), 0.0):
            one(n_in + g, np.asarray(ls._Rz(angles[int(tag)]), dtype=np.complex128))
    outputs = list(obj["outputnodes"])
    scheduled = {next(iter(d)) for layer in obj["consumptionschedule"] for d in layer}
    missing = set(range(N)) - scheduled - set(outputs)
    if missing:
        raise RuntimeError(f"graph qubits {sorted(missing)[:5]} are neither measured nor outputs")
    for g in sorted(scheduled - set(outputs)):
        measure_plus(n_in + g)
    keep = [n_in + g for g in outputs]
    idx = [0] * T
    for a in keep:
        idx[a] = slice(None)
    out = st[tuple(idx)]
    # axes of `out` are the kept axes in increasing position; put them in outputnodes order
    order = sorted(range(len(keep)), key=lambda i: keep[i])
    return np.transpose(out, np.argsort(order)).reshape(-1)


def cabaliser_translate(width: int, ops: list[list], unitary, inputs) -> dict:
    """Fidelity of the compiled graph state with the circuit's unitary on each input (RRE environment)."""
    import numpy as np
    obj, angles = _widget(width, ops)
    U = np.asarray(unitary, dtype=np.complex128)
    rows = []
    for label, psi in inputs:
        psi = np.asarray(psi, dtype=np.complex128)
        got, want = simulate(obj, angles, psi), U @ psi
        fid = float(abs(np.vdot(want, got)) ** 2 / ((np.vdot(got, got).real or 1.0) * np.vdot(want, want).real))
        rows.append({"input": label, "fidelity": fid})
    return {"vertices": int(obj["n_qubits"]), "rows": rows}


def _call(req: dict) -> dict:
    py = os.environ.get("CABALISER_PYTHON", str(REPO / ".rre" / "venv" / "bin" / "python"))
    if not Path(py).exists():
        raise RuntimeError(f"Cabaliser's Python ({py}) not found: build it with experiments/rre/environment.sh "
                           "or set CABALISER_PYTHON")
    p = subprocess.run([py, "-m", "mbqc_verify.compile.cabaliser_adapter"], input=json.dumps(req),
                       capture_output=True, text=True, timeout=3600, cwd=REPO,
                       env=dict(os.environ, PYTHONPATH=str(REPO / "src")))
    if p.returncode != 0:
        raise RuntimeError("Cabaliser failed:\n" + p.stderr[-3000:])
    return json.loads(p.stdout.strip().splitlines()[-1])


def compile_counts(qc):
    from .compilers import Counts
    width, ops = clifford_rz_ops(qc)
    d = _call({"width": width, "ops": ops})
    return Counts(d["N"], d["E"], d["M"], d["space"], {k: d[k] for k in ("time", "rotations", "inputs")})


def translate(qc, samples: int = 4, seed: int = 0) -> dict:
    """Compile qc with Cabaliser and compare the graph state with qc's unitary on every computational basis
    state and `samples` Haar-random states (post-selected branch). Small circuits only: the simulation holds
    inputs + all graph vertices at once."""
    import numpy as np
    from qiskit.quantum_info import Operator
    width, ops = clifford_rz_ops(qc)
    U = Operator(qc.remove_final_measurements(inplace=False).reverse_bits()).data   # big-endian, like Cabaliser
    rng = np.random.default_rng(seed)
    dim = 2 ** width
    inputs = [(f"|{b:0{width}b}>", np.eye(dim)[b]) for b in range(dim)]
    for k in range(samples):
        v = rng.normal(size=dim) + 1j * rng.normal(size=dim)
        inputs.append((f"random #{k}", v / np.linalg.norm(v)))
    enc = lambda a: [np.real(a).tolist(), np.imag(a).tolist()]
    return _call({"mode": "translate", "width": width, "ops": ops, "unitary": enc(U),
                  "inputs": [(lab, enc(v)) for lab, v in inputs]})


def _decode(v):
    import numpy as np
    return np.asarray(v[0]) + 1j * np.asarray(v[1])


if __name__ == "__main__":
    import contextlib
    import io
    req = json.loads(sys.stdin.read())
    with contextlib.redirect_stdout(io.StringIO()):
        if req.get("mode") == "translate":
            out = cabaliser_translate(req["width"], req["ops"], _decode(req["unitary"]),
                                      [(lab, _decode(v)) for lab, v in req["inputs"]])
        else:
            out = cabaliser_counts(req["width"], req["ops"])
    print(json.dumps(out))
