"""
conventions.py — the conventions every object, statement and check is stated in.

The code base juggles several conventions that silently change what a number
means. Each DAG node declares the ones it uses (`conventions:` in its YAML), and
`verification/graph/conventions` checks that both ends of every edge agree, or
that the edge names a converter from CONVERTERS below.

    angle   pi_units | radians              Graphix angles are in units of pi, Qiskit's in radians
    endian  big | little                    Graphix statevectors are big-endian, Qiskit's little-endian
    input   plus | zero                     MBQC patterns start in |+>^n, circuits in |0>^n
    phase   global_dropped | exact          patterns are only defined up to global phase
    degree  qsvt_calls_per_sequence |       what "degree" counts: our QSVT D (block-encoding calls in
            gqsp_laurent_degree |           one sequence), our GQSP d (Laurent degree, 2d calls),
            trotter_steps |                 Trotter steps r,
            slide_polynomial_degree         or the slide's d_eps / g_eps (polynomial degree, undefined
                                            relative to ours; see docs/hamsim.md)
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from enum import Enum


class Angle(str, Enum):
    PI_UNITS = "pi_units"
    RADIANS = "radians"


class Endian(str, Enum):
    BIG = "big"
    LITTLE = "little"


class InputState(str, Enum):
    PLUS = "plus"
    ZERO = "zero"


class Phase(str, Enum):
    GLOBAL_DROPPED = "global_dropped"
    EXACT = "exact"


class Degree(str, Enum):
    QSVT_CALLS_PER_SEQUENCE = "qsvt_calls_per_sequence"
    GQSP_LAURENT_DEGREE = "gqsp_laurent_degree"
    TROTTER_STEPS = "trotter_steps"
    SLIDE_POLYNOMIAL_DEGREE = "slide_polynomial_degree"


AXES: dict[str, type[Enum]] = {
    "angle": Angle,
    "endian": Endian,
    "input": InputState,
    "phase": Phase,
    "degree": Degree,
}


@dataclass(frozen=True)
class Conventions:
    angle: Angle | None = None
    endian: Endian | None = None
    input: InputState | None = None
    phase: Phase | None = None
    degree: Degree | None = None

    @staticmethod
    def parse(d: dict | None) -> "Conventions":
        """From a node's `conventions:` mapping. Unknown axes or values raise ValueError."""
        d = d or {}
        unknown = set(d) - set(AXES)
        if unknown:
            raise ValueError(f"unknown convention axes: {sorted(unknown)}")
        return Conventions(**{k: AXES[k](v) for k, v in d.items()})

    def as_dict(self) -> dict[str, str]:
        return {k: v.value for k, v in asdict(self).items() if v is not None}

    def conflicts(self, other: "Conventions") -> dict[str, tuple[str, str]]:
        """Axes both sides set, to different values: {axis: (self, other)}."""
        a, b = self.as_dict(), other.as_dict()
        return {k: (a[k], b[k]) for k in a.keys() & b.keys() if a[k] != b[k]}


# The conventions of the Graphix pipeline in compile/qiskit_to_mbqc.py
# (Graphix side) and of the Qiskit circuits in hamsim/circuits.py.
GRAPHIX = Conventions(angle=Angle.PI_UNITS, endian=Endian.BIG, input=InputState.PLUS,
                      phase=Phase.GLOBAL_DROPPED)
QISKIT = Conventions(angle=Angle.RADIANS, endian=Endian.LITTLE, input=InputState.ZERO,
                     phase=Phase.EXACT)


# Named converters an edge may cite (`convert: [radians_to_pi_units, ...]`) to
# bridge a convention mismatch. Each maps one axis value to another, and is
# implemented where the conversion actually happens in the code.
CONVERTERS: dict[str, tuple[str, str, str]] = {
    # name: (axis, from, to)
    "radians_to_pi_units": ("angle", "radians", "pi_units"),        # to_graphix_circuit: theta / pi
    "little_to_big_endian": ("endian", "little", "big"),            # verify: reverse_qargs()
    "zero_to_plus_input": ("input", "zero", "plus"),                # H on every qubit before compiling
    "drop_global_phase": ("phase", "exact", "global_dropped"),      # compare |<a|b>|, not <a|b>
    "phase_insensitive_counts": ("phase", "global_dropped", "exact"),   # resource counts ignore phase
    "endian_insensitive_counts": ("endian", "big", "little"),           # resource counts ignore ordering
    "input_insensitive_counts": ("input", "plus", "zero"),              # resource counts ignore input
}


def radians_to_pi_units(theta: float) -> float:
    return theta / math.pi
