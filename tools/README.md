# tools: the external tools the verifier calls, pinned

This folder holds how each external tool is installed and pinned, not the code that calls it. The code that runs a
tool lives in `src/mbqc_verify/` (`tools/` for the checking tools, `compilers/` for compilers), and the tests that
use them live in `checks/`.

| Tool | Pinned in | Called by | Used by tests |
|---|---|---|---|
| Stim, PyMatching, sinter | `requirements.txt` (this folder) | `src/mbqc_verify/tools/surface_code.py` | `tool/surface_code_memory`, `tool/surface_code_fit` |
| pygridsynth (Ross–Selinger) | `requirements.txt` | `src/mbqc_verify/tools/gridsynth.py` | `tool/gridsynth_rz` |
| Qualtran | `requirements.txt` | `src/mbqc_verify/tools/qualtran_cost.py` | `tool/qualtran_cost` |
| Azure Quantum Resource Estimator (`qdk`) | `requirements.txt` | `src/mbqc_verify/tools/azure_re.py` | `tool/azure_re_logical_counts`, `tool/azure_re_qsharp` |
| Hypothesis | `requirements.txt` | `checks/refuter/hypothesis.py` | `refuter/hypothesis` |
| cryptography (Fernet) | `requirements.txt` | `checks/_shared/heldout.py` | held-out expected values in `tool/*` and `reproduction/recorded_value` |
| RRE, Cabaliser, pyLIQTR | `rre/environment.sh`, `rre/requirements-rre.txt` | `experiments/rre/`, `src/mbqc_verify/compilers/cabaliser.py` | `reproduction/recorded_value`, the Cabaliser variants of `scaling/*` and `translation/recorded_compiler` (through the records in `experiments/compilers/results/`) |
| Lean 4 | `lean/lean-toolchain` (the Lean project) | `checks/_shared/lean.py` | `lean/*`, `lean_proof/*`, `vocabulary/*`, `nonvacuity/*`, `equivalence/*`, `differential/*` |
| Graphix, Qiskit | `requirements.txt` at the repository root (the verifier's own environment) | `src/mbqc_verify/compilers/graphix.py` | most `scaling/*`, `translation/graphix_pattern`, `differential/*` |

```bash
pip install -r requirements.txt && pip install --no-deps -r tools/requirements.txt   # every dependency listed
bash tools/rre/environment.sh                                                        # RRE + Cabaliser, into .rre/
```

`tools/requirements.txt` is installed with `--no-deps`, so it lists every package explicitly and nothing in the
root `requirements.txt` moves. It is hashed into the evidence of the tool, refuter, reproduction and finite tests,
so changing a pin re-runs them.
