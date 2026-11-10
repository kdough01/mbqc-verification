# Compiler records

A cost formula is a claim about one compiler. The verifier compares the Hamiltonian-simulation formulas across
compilers through one interface (`src/mbqc_verify/compilers/__init__.py`):

| `compiler` | What it is | Runs in |
|---|---|---|
| `graphix` | Graphix 0.4.1 gate by gate (J-∧z), unoptimized | the verifier's environment, live |
| `graphix_opt` | Graphix 0.4.1 after standardization and Pauli-measurement removal | the verifier's environment, live |
| `cabaliser` | Cabaliser (Rigetti RRE's graph-state compiler), Clifford + Rz input, one widget | the pinned RRE environment (`tools/rre/environment.sh`) |

Compilers that need their own environment are run by `run.py`, which writes `results/<compiler>.json`. That file
holds the counts on every scaling-grid point and the translation runs (the compiled graph state against the circuit
on every basis input and random inputs). The checks with `compiler: <name>` read it, so CI needs no extra
environment, and the evidence goes stale when the record changes.

```bash
bash tools/rre/environment.sh                     # once
CABALISER_PYTHON=.rre/venv/bin/python python experiments/compilers/run.py --compiler cabaliser
dagtool run --stale
```

The `reproduce` workflow (Actions → reproduce → Run workflow) re-records Cabaliser along with the RRE reproduction.

The variant nodes are in `dag/nodes/hamsim/B/compilers/`. Each one is `variant_of` the Graphix claim it compares
with. To add another compiler, for example another thrust's optimizer, follow the steps at the top of
`compilers.py`.
