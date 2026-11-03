"""
compare.py — our run of the paper's pipeline against the paper's Table II, quantity by quantity.

    python experiments/rre/compare.py experiments/rre/results/fh_2x2.json [--rel-tol 0.01]

How RRE's output columns map onto the table's columns is not stated in the paper; MAPPING records our reading, which
the QFT rows settle (README.md, "Calibration"). MAPPING_V1 is the first pass's reading.
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
    # Table II's ñ_logical column sits under "Input circuit": it is the logical qubits of the (decomposed) input circuit,
    # Parameter 15, not Appendix A's Parameter 2 (graph memory). QFT N-4/10/25/100 give 4/10/25/100 exactly.
    "n_logical": (lambda r: r["input_logical_qubits"], "Parameter 15, input-circuit logical qubits"),
    "bus_patches": (lambda r: (r["memory_logical_qubits_per_module"] + r["ancilla_logical_qubits_per_module"])
                    * r["total_num_modules"], "memory + auxiliary bus patches over all modules"),
    # Counted over all modules: QFT N-4/10 (2 modules) and N-100 (4 modules) reproduce only with the factor.
    "t_patches": (lambda r: (r["t_buffer_logical_qubits_per_module"] + r["t_distillery_logical_qubits_per_module"])
                  * r["total_num_modules"], "T-transfer bus + T-factory patches over all modules"),
    # Table II follows modules × Parameter 14 (factories priced at their Q qubits), not Parameter 35, which RRE
    # reports as total_allocated_physical_qubits (factories priced at their footprint in 2d² patches).
    "phys_qubits": (lambda r: r["num_alloc_physical_qubits_per_module"] * r["total_num_modules"],
                    "modules × Parameter 14"),
    "modules": (lambda r: r["total_num_modules"], "Parameter 12"),
    "time_s": (lambda r: r["total_ft_algorithm_time_sec"], "Parameter 47-48, total wall time"),
    "p4k_w": (lambda r: r["power_dissip_4K_kW"] * 1e3, "Parameter 40 (RRE reports kW)"),
    # RRE's power_dissip_mxc_kW column carries watts: 1.68e-7 there is the table's 168 nW (RRE 0.26.33 fixed
    # a "MXC dissipation state reporting bug"; the column name kept "kW").
    "p20mk_w": (lambda r: r["power_dissip_mxc_kW"], "Parameter 41 (RRE's column is in W despite its name)"),
    "energy_wh": (lambda r: r["total_ft_energy_kWh"] * 1e3, "Parameter 49 energy (RRE reports kWh)"),
}
# The first pass (results/table2_2x2.json, table2_4x4.json) used these readings; kept to reproduce those files.
MAPPING_V1 = dict(MAPPING, **{
    "n_logical": (lambda r: r["num_logical_qubits_per_busrail"], "Parameter 2, ñ_logical"),
    "t_patches": (lambda r: r["t_buffer_logical_qubits_per_module"] + r["t_distillery_logical_qubits_per_module"],
                  "T-transfer bus + T-factory patches per module"),
    "phys_qubits": (lambda r: r["total_allocated_physical_qubits"], "Parameter 35"),
})


def compare(result: dict, rel_tol: float = 0.01, mapping: dict | None = None) -> dict:
    table = yaml.safe_load((HERE / "paper_v3_table2.yaml").read_text())
    lattice = result["instance"]["lattice"]
    section = result["instance"].get("table_section", "fermi_hubbard")
    row = (table.get(section) or {}).get(lattice)
    if row is None:
        raise SystemExit(f"no Table II row for {section} {lattice}")
    out = {}
    for key, (get, note) in (mapping or MAPPING).items():
        ours = float(get(result["rre"]))
        theirs = float(row[key])
        ratio = ours / theirs if theirs else None
        out[key] = {"paper": theirs, "ours": ours, "ratio": round(ratio, 4) if ratio else None,
                    "match": ratio is not None and abs(ratio - 1) <= rel_tol, "reading": note}
    return {"section": section, "lattice": lattice, "rel_tol": rel_tol, "quantities": out,
            "matched": sorted(k for k, v in out.items() if v["match"]),
            "not_matched": sorted(k for k, v in out.items() if not v["match"])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("result")
    ap.add_argument("--rel-tol", type=float, default=0.01)
    ap.add_argument("--v1", action="store_true", help="the first pass's column readings (MAPPING_V1)")
    args = ap.parse_args(argv)
    print(json.dumps(compare(json.loads(Path(args.result).read_text()), args.rel_tol,
                             MAPPING_V1 if args.v1 else None), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
