# mbqc-verification

Translate gate-based quantum results into measurement-based (MBQC) ones, and verify them with as little human
oversight as possible. Every claim is a node in a DAG of theorems. Its status is computed from the evidence that
checks leave behind, and nobody (human or LLM) writes "proved" by hand.

The first worked example is the slide *Hamiltonian simulation: explicit costs and trade-offs*
(`docs/img/hamsim_slide.png`). Its Layers A, B and C are the first nodes (see [docs/hamsim.md](docs/hamsim.md)).

## Layout

```text
checks/                   every test a node can run: one file per test, checks/<type>/<name>.py (checks/README.md)
  <type>/                 one folder per type (scaling, lean, numerical, translation, tool, ...), each with a README
                          that explains the type and lists its tests; files starting with _ are helpers
  _shared/                helpers several types use (Lean runs, scaling grids, predicates, held-out values)
  _framework.py           what a test file is and how dagtool finds, validates and runs one
  _kinds.py               each type's question and the highest status it may grant
  _template.py            copy this (dagtool new-test TYPE NAME) to add a test
src/mbqc_verify/          the code the tests call
  compilers/              circuit -> MBQC compilers: graphix (unoptimized and optimized), cabaliser; add others here
  hamsim/                 Hamiltonian-simulation circuits, QSP angles, cost analysis
  tools/                  adapters for the pinned external tools (Stim, gridsynth, Qualtran, Azure RE)
  conventions.py          the convention axes every node declares
lean/                     Lean 4 project (core Lean, no Mathlib): definitions, proofs, assumption axioms
tools/                    external tools' pins and environments: requirements.txt (Stim, PyMatching, Qualtran, ...),
                          rre/ (the RRE + Cabaliser environment)
dag/
  nodes/<area>/<id>.yaml  one claim per file, hand-written (schema: dag/schema/node.schema.json)
  reviews/<id>.yaml       human statement reviews, pinned to the statement hash
  reports/<id>.yaml       narrative for a per-paper verification report (dagtool report)
  evidence/<id>/*.json    written by checks, committed
  heldout/<id>.json       sealed expected values (open only in CI on main)
  predicates/<id>.py      predicates a proposal's finite and refuter checks call (from its checks.py)
  suites/policy.yaml      what a proposal's test suite must and may contain
dagtool/                  CLI: validate, run, tests, test, status, show, queue, review, repro, render, report, check
experiments/hamsim/       the full report (run_all.py), plots, results/hamsim_results.json, figures/
experiments/rre/          reproduction of Saadatmand et al. (arXiv:2406.06015) with their pinned pipeline
experiments/compilers/    counts and translation runs of compilers that need their own environment (Cabaliser)
docs/                     write-ups and images
.github/                  CI: verify (every push), papers (pull site theorems), proposals (gate for submitted proofs), reproduce (manual), review, repro (weekly), setup
tests/                    pytest for the verifier itself (status rules, the tests' logic, the file contract)
scripts/protect-main.sh   applies the main ruleset (.github/rulesets/main.json) that enforces .github/CODEOWNERS
```

## How it runs

Everything runs in GitHub Actions; nothing needs to run on your computer. Push, and the `verify` workflow:

1. installs the pinned Python packages and Lean (both cached between runs) and builds `lean/`,
2. runs the tests and validates the DAG,
3. re-runs only the checks your push made stale (an edited statement, changed code, a new node),
4. commits the new evidence back to the branch as `github-actions[bot]`,
5. renders the theorem browser and, on `main`, publishes it to GitHub Pages,
6. fails if a check failed or crashed, a warning is not acknowledged, or a claim got weaker than it was
   before the push (for example a formula that held is now refuted).

Each run's summary page shows what changed, anything that needs attention, the overall status, and the top of the
review queue. The rendered browser is also attached to every run as the `theorem-browser` artifact.

| To… | Do this |
| --- | --- |
| Check a change | Push it. Pull afterwards to get the evidence commit. |
| Re-run every check from scratch | Actions → **verify** → Run workflow → `all` (about 10 minutes) |
| Record a human review | Actions → **review** → Run workflow: node id, approve or reject, notes |
| See every theorem | The Pages site, `https://<user>.github.io/mbqc-verification/` |
| Confirm results reproduce | Automatic every Monday (**repro**), or run it by hand from Actions |

Workflows live in `.github/workflows/`; the shared setup steps are in `.github/actions/setup/`.

### The theorem browser

One page, three tabs. **Dependency graph** shows every claim with its truth and faithfulness; click one for its
statement, evidence and neighbours, or search by id, title, tag or status. **Circuits** draws the smallest instance of
each method three ways: the Qiskit circuit as built, the MBQC pattern the compiler makes from it (one row per qubit,
each CZ drawn at the step it is applied), and the pattern after Pauli measurements are removed (edges this creates
are drawn curved). Hover a vertex for its measurement. **Review queue** lists what a person should review next.
Scaling claims plot the compiled counts against the claimed formula, one line per `n`, with held-out points and any
miss marked, and a data table underneath. The circuit drawings come from `src/mbqc_verify/compilers/graphix_export.py`.

### One-time setup

- **Pages:** Settings → Pages → Source: **GitHub Actions**. Until then the `pages` job fails without failing the run.
  Pages on a private repository needs a paid GitHub plan; the browser is always available as a run artifact.
- **Branch protection:** use the ruleset in `.github/rulesets/main.json` (`scripts/protect-main.sh`, or Settings →
  Rules → Rulesets → New ruleset → Import a ruleset). It requires the code owner's review for the paths in
  `.github/CODEOWNERS`, lets GitHub Actions keep pushing evidence and applied proposals to `main`, and lets admins
  bypass only through a pull request.
- **Held-out values:** `dagtool heldout keygen`, then Settings → Environments → New environment `heldout`,
  deployment branches: `main` only, secret `HELDOUT_KEY` = the key. Keep a copy offline; it is not stored anywhere
  else. After adding it, run the verify workflow with `rerun: all` so checks that skipped without it re-run.

### Running locally (optional)

```bash
pip install -r requirements.txt && pip install -e .     # Python 3.11+
pip install --no-deps -r tools/requirements.txt         # the pinned external tools (every dependency listed)
cd lean && lake build && cd ..                          # needs elan
dagtool run --stale && dagtool status && dagtool check
```

`dagtool tests` lists every test; `dagtool test <type>/<name> --node <id>` runs one without writing anything.
Other commands: `dagtool show <id>`, `dagtool queue`, `dagtool render`, `dagtool summary`, `dagtool repro`,
`dagtool pull-papers`, `dagtool export`, `dagtool report`, `dagtool open-theorems`, `dagtool feedback`,
`dagtool apply-proposals`, `dagtool lean-check`, `dagtool proof-targets`, `dagtool heldout`, `dagtool tool`.
`python experiments/hamsim/run_all.py` prints the full Hamiltonian-simulation report.

## Papers from the Thrust 2 review site

The team's review site ([genesis-thrust2-review.northcentralus.cloudapp.azure.com](https://genesis-thrust2-review.northcentralus.cloudapp.azure.com), code in
`doe-genesis-ai-quantum/thrusts/2-theorem-transfer/review-site`) splits each uploaded paper into modules. Every theorem
module becomes a DAG theorem, and the site's **Theorem DAG** tab shows this DAG.

- **In:** the `papers` workflow (every 15 minutes, or Actions → **papers** → Run workflow) runs
  `dagtool pull-papers`, which writes each open paper theorem as `dag/nodes/papers/<paper>/<id>.yaml` with a `paper:`
  field and no checks, so it starts as `conjecture` (shown as *open*). It never overwrites a node file.
- **Proposals** (from outside this repository): the verifier contains no model and calls none. A proposal for an
  open theorem is a pull request adding `proposals/<node id>/proposal.json`, `theorem.lean` and optionally
  `attempts.json` (every attempt and its rationale, kept as a record). What a proposal must contain comes from
  `dagtool open-theorems --json`: the statement, the Lean namespace and path, the vetted vocabulary and the proved
  results it may build on. Before submitting, a proposer runs `dagtool feedback --proposal DIR`, which runs exactly
  what the gate runs and then restores every file. The Quantum Genesis dashboard does this from its tickets
  (`doe-genesis-ai-quantum/dashboard/verifier.py`).
- **The proposals gate** (`.github/workflows/proposals.yml`, `pull_request_target`): runs the base branch's own copy of
  the workflow and tools, refuses a pull request that touches anything outside `proposals/`, copies the proposal files
  out as data and runs `dagtool apply-proposals`: Lean scanned (no axioms, `sorry`, IO or metaprogramming) and
  compiled without credentials, the node's fixed `lean`, `vocabulary` and `nonvacuity` checks, the CI gate. A proposal
  cannot choose checks, tolerances or expected values. What passes is committed to main and the pull request is closed
  with the verdict; honest non-results are recorded as `unproved`, `not-formalizable` or `counterexample-suspected`; a
  rejected proposal changes nothing and its pull request stays open for a revision. Faithfulness stays below
  human-reviewed until someone approves the statement.
- **Test suites**: a formalization carries `suite.json`, the claim type and the checks the proposer suggests beyond the
  fixed `lean`, `vocabulary` and `nonvacuity` (which the verifier always adds), with a rationale each; predicates for
  `finite` and `refuter` checks go in `checks.py`. `dag/suites/policy.yaml` sets each claim type's minimum
  (`require_one_of`), the types it may use, the tests allowed for each, and their parameter limits. Each check names
  its test (`{"test": "refuter/hypothesis", "name": ..., "params": ..., "rationale": ...}`); the older
  `{"kind": ..., "params": ...}` form is still accepted and translated (`dagtool/legacy.py`). Expected values must name a frozen file or a
  held-out value; `checks.py` passes an allow-list scan (no I/O, no `eval`, no names starting with `_`, only the listed
  imports) before it runs, and is stored as `dag/predicates/<node>.py`. `dagtool suite-policy` prints the policy;
  `dagtool suite-diff OLD NEW` classifies a revision's changes as added, removed, tightened, loosened or modified (the
  dashboard uses it to hold each revision to its diagnosis). Recorded checks carry `origin` (verifier, proposal or
  author), and every theorem's sheet lists its tests with their result.
- **More than one Lean proof**: a formalized theorem can take further proofs. `dagtool proof-targets --json` gives
  the main declaration and its source (to restate the theorem exactly), the proofs so far with their approaches, and
  the namespace and file for the next one (`<namespace>.Proof_<k>`, `lean/MBQC/Papers/<paper>/<theorem>/Proof_<k>.lean`).
  The proposal is `outcome: proof` with an `approach` line. The gate adds it as a `lean_proof` check, which passes when
  the declaration is a theorem from standard axioms and declared assumptions only, its statement is *syntactically*
  the main theorem's (definitional equality is not enough), and its proof term differs from every earlier proof's. The
  file cannot import other proofs. The node's sheet and `dag.json` (`proofs`, `meta.lean_proofs`) show how many Lean
  proofs it has and how many pass. What this does not show: that the proofs use different mathematical ideas; the
  approach text says that, and a person judges it.
- **Reproduction candidates**: for numerical claims, a candidate configuration chosen from
  `experiments/rre/settings_space.yaml` runs with `experiments/rre/run_candidate.py`, and
  `dagtool feedback --node ID --results-root DIR` scores it against the node's frozen expected values.
- **Out:** `verify` writes `dagtool export` (nodes, edges, computed status, evidence summaries and a verdict per
  node) to `site/dag.json`; on main it is published with the browser at
  `https://kdough01.github.io/mbqc-verification/dag.json`, and the site reads it from there.
- **Verdict** (`dagtool/verdict.py`): *rejected* if refuted or broken, *verified* if effective truth is at least
  `empirical` (listing the test types that passed), otherwise *open*. `core_support` counts the definition, core and
  transfer nodes a claim rests on.

No secrets: this repository and its Pages site are public, and so is the site's theorem list. Pages must be on
(Settings → Pages → Source: **GitHub Actions**). `MODULUS_URL` (repository variable) overrides the site address.

## Reproducing published results

Numerical claims from papers (resource counts, runtimes) are checked by re-running the authors' own pipeline,
pinned, outside `dagtool run`, and committing the results with provenance. A `reproduction` check reads one
recorded value and compares it with the claim (`approx` within `rel_tol`, or `eq`/`ge`/`le`); agreement grants
`empirical` on the stated domain, disagreement refutes the node there, and a results file that does not exist
yet is a skip. The first case is Table II of Saadatmand et al. (arXiv:2406.06015v3): the settings the paper does
not state are calibrated on its QFT rows (a grid of real runs; one point reproduces them), then Fermi–Hubbard and
Ising are scored with those settings unchanged. See [experiments/rre/README.md](experiments/rre/README.md) for the
protocol, the findings and how to run the larger instances on a bigger machine, and
`dag/nodes/reproductions/saadatmand2024/` for the nodes. The
`reproduce` workflow (manual) rebuilds the environment, reruns the small lattices and commits the results.

### Verification reports

Each paper the verifier has checked gets a page that shows what was checked, how, and what came out:
the scope, the pipeline under test, the approach step by step (including what got in the way), the
configuration with what the paper states and what it leaves out, figures of the results, the findings, where
the nodes sit in the DAG, and every check with its latest evidence. CI publishes them next to the theorem
browser at `reports/` (linked from its header); the first is
[reports/saadatmand2024.html](https://kdough01.github.io/mbqc-verification/reports/saadatmand2024.html). Every report
also carries two shared sections, kept in `dag/reports/toolkit.yaml` and published on their own at
[reports/toolkit.html](https://kdough01.github.io/mbqc-verification/reports/toolkit.html): strategies that carry over
to future papers, and the verification tools a check can use depending on the kind of claim (with which are in the
verifier, which were used in a reproduction, and which are candidates).

The narrative lives in `dag/reports/<id>.yaml` (scope, steps, configuration, findings, open items and figure
specs). Numbers, outcomes and statuses are never written there: `dagtool report` reads them from the DAG, the
evidence and the committed results when it renders, so the page cannot drift from the checks. To add a report
for another paper, copy `dag/reports/saadatmand2024.yaml`, point it at that paper's nodes
(`dag/nodes/reproductions/<id>/` are included automatically) and results, and run
`dagtool report` (output in `dag/build/reports/`).

## How status works

Each node has two separate statuses:

| Truth (is it true?) | Meaning |
| --- | --- |
| `proved` | Lean proof using only `propext`, `Quot.sound`, `Classical.choice` |
| `proved_modulo` | proved, given the assumptions listed in its frontier |
| `assumed` | imported from the literature, with citation, exact form and convention map |
| `bounded` | proved on a stated finite domain or instance |
| `empirical` | evidence on a stated domain, no proof |
| `conjecture` | no evidence yet |
| `refuted` | a counterexample exists |
| `broken` | something it relies on is refuted |

| Faithfulness (does it mean what we intend?) | Meaning |
| --- | --- |
| `human_reviewed` | a person approved this exact statement (hash-pinned) |
| `tested` | every applicable automatic faithfulness check passed |
| `unreviewed` | neither |

Each test type has a ceiling (`checks/_kinds.py`): a scaling fit can never grant more than `empirical`, whatever
its code returns. Status then propagates down the DAG:

- A node's effective truth is the weakest among itself and the parents it `uses`.
- Parents it `assumes` (or lists under `assumptions:`) join its *frontier* instead. A proved node with a non-empty
  frontier is `proved_modulo`.
- `instantiates` edges are a proof route. They only count once the node's own evidence is a proof.
- Once a Lean proof passes, the edges extracted from the declarations it actually uses replace the declared ones, and
  mismatches are flagged.
- Effective faithfulness is capped by the `definition` and `core` nodes a claim rests on.
- Evidence records a hash of everything it depends on (statement, definitions, parents, code files, check code,
  requirements, Lean sources). When any of these change, the evidence goes stale and stops counting until it is re-run.

## Tests a node can run

Every test is a file in [`checks/`](checks/README.md): `checks/<type>/<name>.py`, named from a node as
`test: <type>/<name>`. Each folder's README explains its type and lists its tests, and each file's docstring
says what the test checks, how it works, its parameters, when it passes and what it grants. To add one, run
`dagtool new-test <type> <name>` and follow [checks/README.md](checks/README.md#adding-a-test).

Every tool on the [toolkit page](https://kdough01.github.io/mbqc-verification/reports/toolkit.html) is pinned and
runs in CI. A node uses one by naming its test and parameters; nothing else is needed.

| Tool | Test | Example parameters |
| --- | --- | --- |
| Stim + PyMatching + sinter | `tool/surface_code_memory`, `tool/surface_code_fit` | `args: {distance: 5, p: 0.003, shots: 100000, seed: 1}`, `path: per_round` (also `interval`, `kappa`, `p_th`) |
| gridsynth (Ross–Selinger) | `tool/gridsynth_rz` | `args: {angles: [0.3, 1.1], epsilon: "1e-6"}`, `path: mean_t_count` (each circuit's error is recomputed) |
| Qualtran | `tool/qualtran_cost` | `args: {bloq: qualtran.bloqs.qft.QFTTextBook, kwargs: {bitsize: 8}}`, `path: total_t_count` |
| Azure Resource Estimator (local, `qdk`) | `tool/azure_re_logical_counts`, `tool/azure_re_qsharp` | `args: {counts: {numQubits: 100, tCount: 1000000}}`, `path: physical_qubits` |
| Hypothesis | `refuter/hypothesis` | `predicate: experiments/x/claims.py:holds`, `strategy: {n: {integers: [2, 500]}}`, `max_examples: 500` |
| (exhaustive) | `finite/exhaustive` | `predicate: …`, `domain: {n: {range: [2, 50]}, d: {values: [3, 5, 7]}}` — grants `bounded` |
| Lean | `equivalence/iff_proof` | `other: <second formalization>`, `proof: <theorem stmt(main) ↔ stmt(other)>` that uses neither proof |
| Held-out values | any `tool/…` or `reproduction/recorded_value` test | `expect: {heldout: ID}` after `dagtool heldout seal ID VALUE` |

`tool/…` tests compare `path` of the tool's output with `expect` (a number, `{results: FILE, path: P}` in a frozen
file, or `{heldout: ID}`) by `op` (`approx` with `rel_tol`, `eq`, `ge`, `le`, `within [low, high]`), grant at most
`empirical` on `domain`, and record the tool versions. `dagtool tool NAME --args '{...}'` prints a tool's output
without a node. A predicate file must be listed under the node's `code:`, so editing it re-runs the check.

## Adding a claim

1. Write `dag/nodes/<area>/<id>.yaml`: `id`, `kind`, `title`, `statement`, `conventions`, `depends_on`, and the
   `checks` that should run, each `- test: <type>/<name>` with its `params:` (`dagtool tests` lists them).
2. If it is formalized, add the theorem under `lean/MBQC/`, set `lean_decl`, and add the `lean/proof`,
   `vocabulary/vetted_constants` and `nonvacuity/witness` tests (with a `…_nonvacuous` witness theorem when it has hypotheses). Unproved facts about code
   output go in `lean/MBQC/Assumptions/` as axioms, owned by an `assumption` node.
3. Push. CI runs its checks and commits the evidence; the run summary and the browser show the result.
4. If it is a definition, core lemma, assumption or transfer theorem, a person reviews the statement with the
   **review** workflow.
5. A claim that is meant to be false (a re-test expected to fail) lists `refuted` under `acknowledged:` with the
   reason, so its refutation is not reported as a regression.

## Conventions

`src/mbqc_verify/conventions.py` names every convention that changes what a number means: angle units (π vs
radians), qubit ordering, input state, global phase, and what "degree" counts. Nodes declare theirs, and an edge
whose two ends disagree is flagged unless it names a converter. This is how the slide's `d ≥ g` comparison gets
caught: our QSVT `D` and GQSP `d` measure different things.
