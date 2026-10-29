"""Tests of check logic that need no circuit compilation."""

from __future__ import annotations

from fractions import Fraction

from mbqc_verify.conventions import Conventions
from verification.kinds import clamp_truth
from verification.truth.scaling.grids import corners, interpolate, mismatches
from verification.truth.symbolic.coeff_positivity import certificate


def bilinear(a, b, c, e):
    return {(n, k): {"N": a * n * k + b * k + c * n + e} for n in (2, 3, 4) for k in (1, 2, 3)}


def test_mismatches_exact_formula():
    data = bilinear(36, -18, 92, -20)
    assert mismatches([36, -18, 92, -20], data, "N") == []
    assert len(mismatches([37, -18, 92, -20], data, "N")) == len(data)


def test_mismatches_accepts_fraction_strings():
    data = {(2, 1): {"N": 1}}
    assert mismatches(["1/2", 0, 0, 0], data, "N") == []


def test_interpolation_recovers_formula_and_detects_non_bilinear():
    data = bilinear(3, -1, 3, 0)
    pts = corners(list(data))
    assert interpolate(data, "N", pts) == [Fraction(3), Fraction(-1), Fraction(3), Fraction(0)]
    data[(3, 2)]["N"] += 1                      # break bilinearity off the corners
    coef = interpolate(data, "N", pts)
    assert mismatches(coef, data, "N") == [{"n": 3, "k": 2, "count": data[(3, 2)]["N"], "formula": str(coef[0] * 6 + coef[1] * 2 + coef[2] * 3 + coef[3])}]


def test_slide_certificate_holds_for_all_quantities():
    for q in "NEM":
        assert all(c["certifies_positive"] for c in certificate(q)), q


def test_clamp_truth():
    assert clamp_truth("proved", "scaling") == "empirical"
    assert clamp_truth("refuted", "scaling") == "refuted"
    assert clamp_truth("bounded", "translation") == "bounded"
    assert clamp_truth("proved", "lean") == "proved"


def test_convention_conflicts():
    a = Conventions.parse({"endian": "big", "angle": "pi_units"})
    b = Conventions.parse({"endian": "little"})
    assert a.conflicts(b) == {"endian": ("big", "little")}
