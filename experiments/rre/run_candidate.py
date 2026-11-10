"""
run_candidate.py — run a reproduction candidate with the pinned pipeline and write results a node can score.

    python experiments/rre/run_candidate.py --candidate CANDIDATE.yaml --out DIR

Validates the candidate against settings_space.yaml first (nothing runs if it is not declared), then runs each
instance with exactly those settings and writes DIR/<family>_<label>.json and DIR/table2_<family>_<label>.json,
named like the committed results, so `dagtool feedback --node ID --results-root DIR` scores them against the
node's frozen expected values. DIR/candidate.json records the candidate, the resolved settings and timings.
Needs the RRE environment (tools/rre/environment.sh).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def main(argv=None) -> int:
    import calibrate
    import compare
    import fh
    from candidates import load_space, validate
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    cand = yaml.safe_load(Path(args.candidate).read_text(encoding="utf-8"))
    space = load_space()
    errs = validate(cand, space)
    if errs:
        print(json.dumps({"valid": False, "problems": errs}, indent=1))
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    record = {"candidate": cand, "runs": [], "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    for inst in cand["instances"]:
        model, n = inst.split(":")
        fam = cand["families"][model]
        mg, mq = space["family_settings"]["widgets"][fam["widgets"]]
        point = dict(cand["settings"], qubit_manager=fam["qubit_manager"])
        t0 = time.time()
        row = {"instance": inst, "node": space["nodes"].get(inst)}
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                r = fh.run(int(n), "random", 0, HERE / "config_paper_v3.yaml", [], max_gates=mg, max_q=mq,
                           qubit_manager=fam["qubit_manager"], model=model, params=calibrate.params_for(point),
                           label=f"candidate:{inst}")
            stem = f"{model}_{r['instance']['lattice']}"
            (out / f"{stem}.json").write_text(json.dumps(r, indent=1, default=str) + "\n", encoding="utf-8")
            c = compare.compare(r)
            (out / f"table2_{stem}.json").write_text(json.dumps(c, indent=1) + "\n", encoding="utf-8")
            row.update(results=f"table2_{stem}.json", matched=c["matched"], not_matched=c["not_matched"])
        except Exception as e:   # recorded: some declared settings break the pipeline for some instances
            row["error"] = f"{type(e).__name__}: {e}"[:400]
        row["seconds"] = round(time.time() - t0, 1)
        record["runs"].append(row)
    (out / "candidate.json").write_text(json.dumps(record, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
