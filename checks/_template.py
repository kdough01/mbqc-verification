"""
TYPE/NAME — one line: what this test establishes, as a claim ("a formula reproduces every count").

What it checks
    The claim this test tests, in words a reviewer can check against the node's statement. Say what a pass
    does and does not establish.

How it works
    1. The steps, specific enough to reproduce the test by hand: what is built, with which seeds or grids,
       what is compared with what, exactly or within which tolerance.
    2. Name the helpers it uses (checks/_shared/..., src/mbqc_verify/...) so a reader can follow the code.

Parameters
    example_param   what it means, its values, and its default if it is optional

Passes when
    The condition for "pass".

Fails when
    The conditions for "fail", and what a failure means for the claim (refuted, or only "not shown").

Grants
    The status a pass gives: proved | proved_modulo | bounded | empirical | assumed for truth tests (capped
    by the type's ceiling, checks/_kinds.py), tested for faithfulness tests.

Example
    - test: TYPE/NAME
      params: {example_param: 3}
"""

# To add a test:
#   1. `dagtool new-test TYPE NAME` copies this file to checks/TYPE/NAME.py (or copy it by hand);
#   2. write the docstring above (every section is required except Cost, Limits, Notes, See also);
#   3. describe the node's params in PARAMS (a JSON-schema "properties" literal) and list the required ones;
#   4. implement run(); put helpers in checks/TYPE/_name.py, or checks/_shared/ if several types use them;
#   5. `dagtool readmes` adds the test to checks/TYPE/README.md; `pytest tests/test_check_files.py` checks
#      the file follows this shape and its Example validates;
#   6. name it from a node: `- test: TYPE/NAME` with `params:`, then `dagtool run --node <id>`.
# Delete these comments in the copy.

from __future__ import annotations

from checks._framework import Result

PARAMS = {
    "example_param": {"type": "integer", "minimum": 0},
}
REQUIRED = ["example_param"]


def applies_to(node) -> bool:      # optional: return False to make the run a skip
    return True


def run(node, params, ctx) -> Result:
    """node: dagtool.model.Node; params: the node's params (already validated); ctx: checks._framework.Context."""
    value = params["example_param"]
    if value >= 0:
        return Result("pass", "empirical", "the domain the verdict covers", summary="one line for people",
                      evidence={"value": value})
    return Result("fail", "refuted", "where it failed", summary="one line saying where and how")
