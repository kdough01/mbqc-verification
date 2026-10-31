"""
compare.py — our run of the paper's pipeline against the paper's Table II, quantity by quantity.

    python experiments/rre/compare.py experiments/rre/results/fh_2x2.json [--rel-tol 0.01]

How RRE's output columns map onto the table's columns is not stated in the paper; MAPPING records our reading.
A quantity "matches" when it agrees within rel_tol (the table prints 3 significant figures, so 1% by default).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent

# table column -> (how to get it from RRE's CSV row, what that reading assumes)
MAPPING = {
    "n_logical": (lambda r: r["num_logical_qubits_per_busrail"], "Parameter 2, ñ_logical"),
    "bus_patches": (lambda r: (r["memory_logical_qubits_per_module"] + r["ancilla_logical_qubits_per_module"])
                    * r["total_num_modules"], "memory + auxiliary bus patches over all modules (our reading)"),
    "t_patches": (lambda r: r["t_buffer_logical_qubits_per_module"] + r["t_distillery_logical_qubits_per_module"],
                  "T-transfer bus + T-factory patches per module (our reading)"),
    "phys_qubits": (lambda r: r["total_allocated_physical_qubits"], "Parameter 35"),
    "modules": (lambda r: r["total_num_modules"], "Parameter 12"),
    "time_s": (lambda r: r["total_ft_algorithm_time_sec"], "Parameter 47-48, total wall time"),
    "p4k_w": (lambda r: r["power_dissip_4K_kW"] * 1e3, "Parameter 40 (RRE reports kW)"),
    # RRE's power_dissip_mxc_kW column carries watts: 1.68e-7 there is the table's 168 nW (RRE 0.26.33 fixed
    # a "MXC dissipation state reporting bug"; the column name kept "kW").
    "p20mk_w": (lambda r: r["power_dissip_mxc_kW"], "Parameter 41 (RRE's column is in W despite its name)"),
    "energy_wh": (lambda r: r["total_ft_energy_kWh"] * 1e3, "Parameter 49 energy (RRE reports kWh)"),
}


def compare(result: dict, rel_tol: float = 0.01) -> dict:
    table = yaml.safe_load((HERE / "paper_v3_table2.yaml").read_text())
    lattice = result["instance"]["lattice"]
    row = table["fermi_hubbard"].get(lattice)
    if row is None:
        raise SystemExit(f"no Table II row for {lattice}")
    out = {}
    for key, (get, note) in MAPPING.items():
        ours = float(get(result["rre"]))
        theirs = float(row[key])
        ratio = ours / theirs if theirs else None
        out[key] = {"paper": theirs, "ours": ours, "ratio": round(ratio, 4) if ratio else None,
                    "match": ratio is not None and abs(ratio - 1) <= rel_tol, "reading": note}
    return {"lattice": lattice, "rel_tol": rel_tol, "quantities": out,
            "matched": sorted(k for k, v in out.items() if v["match"]),
            "not_matched": sorted(k for k, v in out.items() if not v["match"])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("result")
    ap.add_argument("--rel-tol", type=float, default=0.01)
    args = ap.parse_args(argv)
    print(json.dumps(compare(json.loads(Path(args.result).read_text()), args.rel_tol), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
