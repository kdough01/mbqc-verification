"""CODEOWNERS covers the verifier's own paths, and the ruleset that enforces it keeps CI able to push."""

from __future__ import annotations

import fnmatch
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# what must never change without the owner's review (README, toolkit "Proposals may only write to an allow-list")
PROTECTED = ["checks/_kinds.py", "checks/_framework.py", "checks/tool/_run.py", "checks/scaling/bilinear_formula.py",
             "dagtool/proposals.py", "dag/suites/policy.yaml", "tools/rre/environment.sh",
             "dag/schema/node.schema.json", "experiments/rre/paper_v3_table2.yaml", "experiments/rre/settings_space.yaml",
             "dag/heldout/x.json", "lean/scripts/Inspect.lean", "requirements.txt", "tools/requirements.txt",
             ".github/workflows/proposals.yml", ".github/CODEOWNERS", "dag/reports/toolkit.yaml"]


def patterns():
    rows = []
    for line in (REPO / ".github/CODEOWNERS").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            pat, *owners = line.split()
            rows.append((pat, owners))
    return rows


def covered(path: str) -> list[str]:
    owners = []
    for pat, who in patterns():
        p = pat.lstrip("/")
        if (p.endswith("/") and path.startswith(p)) or fnmatch.fnmatch(path, p):
            owners = who                                  # last match wins, as on GitHub
    return owners


def test_protected_paths_have_an_owner():
    for path in PROTECTED:
        assert covered(path) == ["@kdough01"], path


def test_proposals_are_not_owner_gated():
    assert covered("proposals/paper.p_x.t/proposal.json") == []


def test_ruleset_requires_code_owners_and_lets_actions_push():
    r = json.loads((REPO / ".github/rulesets/main.json").read_text())
    pr = next(x for x in r["rules"] if x["type"] == "pull_request")["parameters"]
    assert pr["require_code_owner_review"] is True
    assert {"actor_type": "Integration", "actor_id": 15368, "bypass_mode": "always"} in r["bypass_actors"]
    assert r["conditions"]["ref_name"]["include"] == ["~DEFAULT_BRANCH"]
