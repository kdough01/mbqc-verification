"""
surface_code.py — Stim + PyMatching (+ sinter statistics): logical error rates of the rotated surface code.

    memory(args)  one memory experiment: distance d, rounds (default d), physical error p, shots, seed.
                  Circuit-level depolarizing noise from Stim's generator with every noise parameter = p
                  (after Clifford gates, after reset, before measurement, before each round on data qubits),
                  decoded by minimum-weight perfect matching (PyMatching). Returns the shot error rate, the
                  per-round rate (sinter.shot_error_rate_to_piece_error_rate) and a likelihood interval
                  (sinter.fit_binomial, max_likelihood_factor 1000).
    fit(args)     memory() on a grid of distances and error rates, then a least-squares fit of
                  per_round = kappa * (p / p_th) ** ((d + 1) / 2) in log space (the form of Saadatmand et al.
                  Eq. (1)), returning kappa, p_th and every grid point.

Deterministic: Stim's sampler is seeded, PyMatching is deterministic. Heavy imports happen inside the functions.
"""

from __future__ import annotations

import math

NOISE_KEYS = ("after_clifford_depolarization", "after_reset_flip_probability", "before_measure_flip_probability",
              "before_round_data_depolarization")


def versions() -> dict:
    import pymatching
    import sinter
    import stim
    return {"stim": stim.__version__, "pymatching": pymatching.__version__, "sinter": sinter.__version__}


def memory(args: dict) -> dict:
    import pymatching
    import sinter
    import stim
    d = int(args["distance"])
    rounds = int(args.get("rounds") or d)
    p = float(args["p"])
    shots = int(args.get("shots", 10000))
    seed = int(args.get("seed", 0))
    basis = args.get("basis", "z")
    if basis not in ("x", "z") or d < 3 or d % 2 == 0 or not 0 < p < 0.5 or shots < 1:
        raise ValueError("surface_code.memory needs an odd distance >= 3, basis x|z, 0 < p < 0.5, shots >= 1")
    circuit = stim.Circuit.generated(f"surface_code:rotated_memory_{basis}", distance=d, rounds=rounds,
                                     **{k: p for k in NOISE_KEYS})
    matching = pymatching.Matching.from_detector_error_model(circuit.detector_error_model(decompose_errors=True))
    det, obs = circuit.compile_detector_sampler(seed=seed).sample(shots, separate_observables=True)
    errors = int((matching.decode_batch(det)[:, 0] != obs[:, 0]).sum())
    fit = sinter.fit_binomial(num_shots=shots, num_hits=errors, max_likelihood_factor=1000)
    per_round = sinter.shot_error_rate_to_piece_error_rate(fit, pieces=rounds)
    return {"distance": d, "rounds": rounds, "p": p, "basis": basis, "shots": shots, "seed": seed,
            "errors": errors, "logical_error_rate": errors / shots,
            "interval": [fit.low, fit.high],
            "per_round": per_round.best, "per_round_interval": [per_round.low, per_round.high],
            "noise": "stim generated circuit-level depolarizing, all four parameters = p", "decoder": "pymatching"}


def fit(args: dict) -> dict:
    distances = [int(d) for d in args["distances"]]
    ps = [float(p) for p in args["ps"]]
    shots = int(args.get("shots", 10000))
    seed = int(args.get("seed", 0))
    points = []
    for i, d in enumerate(distances):
        for j, p in enumerate(ps):
            points.append(memory({"distance": d, "p": p, "shots": shots, "seed": seed + 1000 * i + j,
                                  "rounds": args.get("rounds"), "basis": args.get("basis", "z")}))
    usable = [pt for pt in points if pt["errors"] > 0]
    if len(usable) < 2:
        raise ValueError("fewer than two grid points saw a logical error; raise shots or p")
    # log per_round = log kappa + ((d+1)/2) log p - ((d+1)/2) log p_th: linear in (1, (d+1)/2 * log p, (d+1)/2)
    rows = [(1.0, (pt["distance"] + 1) / 2 * math.log(pt["p"]), (pt["distance"] + 1) / 2) for pt in usable]
    ys = [math.log(pt["per_round"]) for pt in usable]
    # the exponent of p is fixed by the model, so move it to the left: y - (d+1)/2 log p = log kappa - (d+1)/2 log p_th
    xs = [r[2] for r in rows]
    zs = [y - r[1] for y, r in zip(ys, rows)]
    n = len(xs)
    mx, mz = sum(xs) / n, sum(zs) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        raise ValueError("the fit needs at least two distances")
    slope = sum((x - mx) * (z - mz) for x, z in zip(xs, zs)) / sxx
    intercept = mz - slope * mx
    resid = [z - (intercept + slope * x) for x, z in zip(xs, zs)]
    return {"kappa": math.exp(intercept), "p_th": math.exp(-slope), "points": points, "used_points": len(usable),
            "rms_log_residual": math.sqrt(sum(r * r for r in resid) / n),
            "model": "per_round = kappa * (p / p_th) ** ((d + 1) / 2)"}
