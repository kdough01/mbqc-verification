# mbqc-verification

Translate gate-based quantum results into measurement-based (MBQC) ones, and verify them with as little human
oversight as possible. Every claim is a node in a DAG of theorems. Its status is computed from the evidence that
checks leave behind, and nobody (human or LLM) writes "proved" by hand.

The first worked example is the slide *Hamiltonian simulation: explicit costs and trade-offs*
(`docs/img/hamsim_slide.png`). Its Layers A, B and C are the first nodes (see [docs/hamsim.md](docs/hamsim.md)).

## Layout

```text
src/mbqc_verify/          the objects: circuits, QSP angles, circuit -> MBQC compiler, conventions
lean/                     Lean 4 project (core Lean, no Mathlib): definitions, proofs, assumption axioms
verification/             the checks, sorted by the question each answers
  faithfulness/           does the statement mean what we intend?   vocabulary, differential, mutation, nonvacuity, review
  truth/                  is it true?   lean, symbolic, translation, numerical, scaling, refuter, literature
  graph/                  properties of the DAG: conventions, Lean-extracted edges, propagation, staleness, repro
dag/
  nodes/<area>/<id>.yaml  one claim per file, hand-written (schema: dag/schema/node.schema.json)
  reviews/<id>.yaml       human statement reviews, pinned to the statement hash
  evidence/<id>/*.json    written by checks, committed
tools/dagtool/            CLI: validate, run, status, show, queue, review, repro, render, check
experiments/hamsim/       the full report (run_all.py), plots, results/hamsim_results.json, figures/
docs/                     write-ups and images
.github/                  CI: verify (every push), papers (pull site theorems), review (by hand), repro (weekly), setup action
tests/                    unit tests for the status rules and check logic
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
miss marked, and a data table underneath. The circuit drawings come from `src/mbqc_verify/compile/export.py`.

### One-time setup

- **Pages:** Settings → Pages → Source: **GitHub Actions**. Until then the `pages` job fails without failing the run.
  Pages on a private repository needs a paid GitHub plan; the browser is always available as a run artifact.
- **Branch protection:** if `main` requires pull requests, the bot cannot push evidence to it. Either allow
  `github-actions[bot]` to bypass, or work on branches (evidence is committed to whichever branch you push).

### Running locally (optional)

```bash
pip install -r requirements.txt && pip install -e .     # Python 3.11+
cd lean && lake build && cd ..                          # needs elan
dagtool run --stale && dagtool status && dagtool check
```

Other commands: `dagtool show <id>`, `dagtool queue`, `dagtool render`, `dagtool summary`, `dagtool repro`,
`dagtool pull-papers`, `dagtool export`.
`python experiments/hamsim/run_all.py` prints the full Hamiltonian-simulation report.

## Papers from the Thrust 2 review site

The team's review site ([genesis-thrust2-review.fly.dev](https://genesis-thrust2-review.fly.dev), code in
`doe-genesis-ai-quantum/thrusts/2-theorem-transfer/review-site`) splits each uploaded paper into modules. Every theorem
module becomes a DAG theorem, and the site's **Theorem DAG** tab shows this DAG.

- **In:** the `papers` workflow (every three hours, or Actions → **papers** → Run workflow) runs
  `dagtool pull-papers`, which writes each open paper theorem as `dag/nodes/papers/<paper>/<id>.yaml` with a `paper:`
  field and no checks, so it starts as `conjecture` (shown as *open*). It never overwrites a node file, so add
  `depends_on` edges into the core and the `checks` that should run by editing that file. Then it runs `verify`.
- **Out:** `verify` writes `dagtool export` (nodes, edges, computed status, evidence summaries and a verdict per
  node) to `site/dag.json`; on main it is published with the browser at
  `https://kdough01.github.io/mbqc-verification/dag.json`, and the site reads it from there.
- **Verdict** (`tools/dagtool/verdict.py`): *rejected* if refuted or broken, *verified* if effective truth is at least
  `empirical` (listing the check kinds that passed), otherwise *open*. `core_support` counts the definition, core and
  transfer nodes a claim rests on.

No secrets: this repository and its Pages site are public, and so is the site's theorem list. Pages must be on
(Settings → Pages → Source: **GitHub Actions**). `MODULUS_URL` (repository variable) overrides the site address.

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

Each check kind has a ceiling (`verification/kinds.py`): a scaling fit can never grant more than `empirical`, whatever
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

## Adding a claim

1. Write `dag/nodes/<area>/<id>.yaml`: `id`, `kind`, `title`, `statement`, `conventions`, `depends_on`, and the
   `checks` that should run (see the existing nodes and the schema).
2. If it is formalized, add the theorem under `lean/MBQC/`, set `lean_decl`, and add the `lean`, `vocabulary` and
   `nonvacuity` checks (with a `…_nonvacuous` witness theorem when it has hypotheses). Unproved facts about code
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
