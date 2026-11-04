"""
candidates.py — validate a reproduction candidate against the declared settings space. No heavy imports.

    python experiments/rre/candidates.py validate CANDIDATE.yaml

A candidate (YAML):

    settings: {target_p_algo: 0.05, coeffs: paper, factories: rre, gate_ns: 200}
    families:
      qft: {widgets: one, qubit_manager: simple}
      fh: {widgets: q40, qubit_manager: greedy-fifo}
    instances: ["fh:4"]

Every setting must be present and take a declared value; families and instances must be declared. Nothing else
is allowed, so trying a different configuration means choosing among declared alternatives.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SPACE_FILE = HERE / "settings_space.yaml"


def load_space() -> dict:
    return yaml.safe_load(SPACE_FILE.read_text(encoding="utf-8"))


def validate(candidate: dict, space: dict | None = None) -> list[str]:
    space = space or load_space()
    errs = []
    if not isinstance(candidate, dict):
        return ["the candidate is not a mapping"]
    extra = set(candidate) - {"settings", "families", "instances"}
    if extra:
        errs.append(f"unknown top-level keys: {sorted(extra)}")
    settings = candidate.get("settings") or {}
    for k, allowed in space["settings"].items():
        if k not in settings:
            errs.append(f"settings.{k} missing (one of {allowed})")
        elif settings[k] not in allowed:
            errs.append(f"settings.{k} = {settings[k]!r} is not declared (one of {allowed})")
    errs += [f"settings.{k} is not a declared setting" for k in set(settings) - set(space["settings"])]
    instances = candidate.get("instances") or []
    if not instances:
        errs.append("instances: at least one")
    errs += [f"instance {i!r} is not declared here (one of {space['instances']})" for i in instances if i not in space["instances"]]
    families = candidate.get("families") or {}
    needed = {i.split(":")[0] for i in instances if isinstance(i, str)}
    for fam in needed - set(families):
        errs.append(f"families.{fam} missing for instance(s) of that family")
    for fam, fs in families.items():
        if fam not in space["families"]:
            errs.append(f"family {fam!r} is not declared")
            continue
        fs = fs or {}
        fspace = space["family_settings"]
        for k in fspace:
            if k not in fs:
                errs.append(f"families.{fam}.{k} missing")
        if fs.get("widgets") is not None and fs["widgets"] not in fspace["widgets"]:
            errs.append(f"families.{fam}.widgets = {fs['widgets']!r} is not declared (one of {sorted(fspace['widgets'])})")
        if fs.get("qubit_manager") is not None and fs["qubit_manager"] not in fspace["qubit_manager"]:
            errs.append(f"families.{fam}.qubit_manager = {fs['qubit_manager']!r} is not declared")
        errs += [f"families.{fam}.{k} is not a declared setting" for k in set(fs) - set(fspace)]
    return errs


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2 or args[0] != "validate":
        print(__doc__)
        return 2
    errs = validate(yaml.safe_load(Path(args[1]).read_text(encoding="utf-8")))
    for e in errs:
        print(e)
    print("ok" if not errs else f"{len(errs)} problem(s)")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
