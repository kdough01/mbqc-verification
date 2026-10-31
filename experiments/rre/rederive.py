"""
rederive.py — recompute RRE's closed-form outputs from its own intermediate values, independently.

    python experiments/rre/rederive.py experiments/rre/results/fh_2x2.json

Appendix A of the paper gives formulas for many outputs in terms of a few inputs (d, ñ_logical, modules, factory
choice, gate counts, ε, timescales). This file implements those formulas without importing RRE and checks that
RRE's reported values satisfy them. It does not re-derive the code distance search (Algorithm 1) or the schedules.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent


def factory(config: dict, name: str) -> dict:
    return next(w for w in config["distill_widget_table"]["widgets"] if w["name"] == name)


def rederive(result: dict, config: dict) -> dict:
    r = result["rre"]
    d, n_tilde, modules = r["distance"], r["num_logical_qubits_per_busrail"], r["total_num_modules"]
    per_leg = modules // 2
    eps = r["diamond_norm_eps"]
    c0, c1 = (0.57, 8.83) if r["decomp_method"] == "mixed_fallback" else (3.0, 0.0)
    L_eps = math.ceil(c0 * math.log2(1 / eps) + c1)
    t_ns = config["ftqc"]["qcycle_char_timescale_ns"]
    n_phys = config["ftqc"]["processor"]["num_qubits"]
    f = factory(config, r["dist_widget_name"])
    l_edge = math.floor(math.sqrt(n_phys / (2 * d * d)))
    mem = math.ceil(n_tilde / per_leg)
    checks = {
        # Parameter 17: N_T = n_Rz·L_ε + n_T
        "t_count": (r["rz_count"] * L_eps + r["init_t_count"], r["t_count"], "Param 17: n_Rz·⌈c0 log2(1/ε)+c1⌉ + n_T"),
        # Parameters 4-7: memory and auxiliary bus, ⌈ñ / n_per-leg⌉ patches of 2d² each
        "memory_logical_qubits_per_module": (mem, r["memory_logical_qubits_per_module"], "Param 4"),
        "memory_physical_qubits_per_module": (2 * d * d * mem, r["memory_physical_qubits_per_module"], "Param 5"),
        "ancilla_physical_qubits_per_module": (2 * d * d * mem, r["ancilla_physical_qubits_per_module"], "Param 7"),
        # Parameter 9: T-transfer bus, 2d² per logical qubit
        "t_buffer_physical_qubits_per_module": (2 * d * d * r["t_buffer_logical_qubits_per_module"],
                                                r["t_buffer_physical_qubits_per_module"], "Param 9"),
        # Parameter 11: n_T-factories · Q
        "t_distillery_physical_qubits_per_module": (r["num_t_factories_per_module"] * f["qubits"],
                                                    r["t_distillery_physical_qubits_per_module"], "Param 11"),
        # Parameter 14: sum of the allocated components
        "num_alloc_physical_qubits_per_module": (
            r["memory_physical_qubits_per_module"] + r["ancilla_physical_qubits_per_module"]
            + r["t_buffer_physical_qubits_per_module"] + r["t_distillery_physical_qubits_per_module"],
            r["num_alloc_physical_qubits_per_module"], "Param 14"),
        # Parameter 35: 4·n_alloc-logical·n^per-leg_modules·d², with n_alloc-logical counting the T-factories as
        # n_T-factories·⌈L_length/(√2d)⌉⌈L_width/(√2d)⌉ patches of 2d² each
        "total_allocated_physical_qubits": (
            4 * (r["memory_logical_qubits_per_module"] + r["ancilla_logical_qubits_per_module"]
                 + r["t_buffer_logical_qubits_per_module"] + r["t_distillery_logical_qubits_per_module"])
            * per_leg * d * d, r["total_allocated_physical_qubits"], "Param 35"),
        # Parameter 35 against Parameter 14: both count allocated physical qubits, but Parameter 14 prices a
        # factory at its own Q qubits (Table I) and Parameter 35 at its footprint in 2d² patches
        "param35_equals_modules_times_param14": (modules * r["num_alloc_physical_qubits_per_module"],
                                                 r["total_allocated_physical_qubits"],
                                                 "consistency: modules × Param 14 = Param 35"),
        # Parameter 31: l_edge² logical patches fit in a module
        "avail_logical_qubits_per_module": (l_edge * l_edge, r["avail_logical_qubits_per_module"], "Param 31"),
        "total_avail_physical_qubits": (n_phys * modules, r["total_avail_physical_qubits"], "Param 30"),
        # Parameters 27-29: tocks
        "quantum_tock": (8 * d * t_ns * 1e-9, r["quantum_tock"], "Param 28: 8 d t"),
        "t_state_tock": (8 * f["cycles"] * t_ns * 1e-9, r["t_state_tock"], "Param 29: 8 C t"),
        "decoder_tock": (d * config["decoder_char_timescale_sec"], r["decoder_tock"], "Param 27: d t_decoder"),
    }
    out = {k: {"rederived": a, "reported": b, "formula": note,
               "match": math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-12)} for k, (a, b, note) in checks.items()}
    return {"lattice": result["instance"]["lattice"], "L_eps": L_eps, "quantities": out,
            "all_match": all(v["match"] for v in out.values()),
            "mismatches": sorted(k for k, v in out.items() if not v["match"])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("result")
    args = ap.parse_args(argv)
    sys.path.insert(0, str(HERE))
    import fh
    result = json.loads(Path(args.result).read_text())
    config = fh.load_params(HERE / result["config"]["file"], result["config"]["overrides"])
    print(json.dumps(rederive(result, config), indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
