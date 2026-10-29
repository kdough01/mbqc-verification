"""Graph-level checks: properties of the DAG as a whole. dagtool computes them on every
`dagtool status`, so they need no evidence files.

    conventions/  both ends of every edge agree, or the edge names a converter
    edges/        Lean-extracted edges agree with declared ones (wave 3)
    propagate/    effective status and frontiers (tools/dagtool/status.py)
    staleness/    evidence whose input hash changed (tools/dagtool/hashing.py)
    repro/        re-run checks and compare verdicts (`dagtool repro`)
"""
