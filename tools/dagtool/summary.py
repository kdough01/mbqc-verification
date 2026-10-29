"""
summary.py — a Markdown report of the DAG for a CI run summary ($GITHUB_STEP_SUMMARY).

Leads with what needs a person's attention, then what this run changed, then
the overall counts and the top of the review queue.
"""

from __future__ import annotations

from verification.kinds import FAITH_ORDER

from .model import Dag
from .status import compute, summary_counts

TRUTH_DISPLAY = ["proved", "proved_modulo", "defined", "assumed", "bounded", "empirical", "conjecture",
                 "broken", "refuted"]
TRUTH_LABEL = {"proved_modulo": "proved modulo", "defined": "definition"}


def _rank(t: str) -> int:
    from verification.kinds import TRUTH_RANK
    return {"broken": -1}.get(t, TRUTH_RANK.get(t, 0))


def regressions(st: dict, before: dict, dag: Dag | None = None) -> list[tuple[str, str, str]]:
    """Nodes whose effective truth got weaker during this run: (id, before, after).
    A node that acknowledges `refuted` is expected to be false and is skipped."""
    out = []
    for i, s in sorted(st.items()):
        b = before.get(i)
        if not b or (dag is not None and i in dag.nodes and "refuted" in dag.nodes[i].acknowledged):
            continue
        # a node whose evidence was stale is judged against what that evidence last said
        was = b.get("last_truth", b.get("truth", "conjecture")) if b.get("stale") else b.get("truth", "conjecture")
        if _rank(s.display_truth) < _rank(was):
            out.append((i, was, s.display_truth))
    return out


def _label(t: str) -> str:
    return TRUTH_LABEL.get(t, t.replace("_", " "))


def _cell(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def markdown(dag: Dag, before: dict | None = None, ran: list | None = None, browser_url: str | None = None) -> str:
    st = compute(dag)
    counts = summary_counts(st)
    out: list[str] = []

    problems = []
    for i, s in sorted(st.items()):
        for e in s.evidence:
            if e.fresh and e.outcome in ("fail", "error") and e.grants != "refuted":
                problems.append((i, e.name, e.outcome, e.summary))
        for f in s.flags:
            if f.level == "warn" and f.code not in ("stale", "broken", "check_failed", "mutation_survived"):
                problems.append((i, f.code.replace("_", " "), "warn", f.message))
    stale = sorted(i for i, s in st.items() if s.stale)
    if before is not None:
        for i, was, now in regressions(st, before, dag):
            problems.insert(0, (i, "regression", now, f"truth went from {_label(was)} to {_label(now)} in this run"))

    out.append("## Theorem DAG")
    verdict = f"**Needs attention: {len(problems)} problem(s).**" if problems else "**All checks pass.**"
    if stale:
        verdict += f" {len(stale)} node(s) still have stale evidence."
    if browser_url:
        verdict += f" [Open the theorem browser]({browser_url})."
    out += [verdict, ""]

    if problems:
        out += ["| Node | Check or flag | Result | Detail |", "| --- | --- | --- | --- |"]
        out += [f"| `{i}` | {_cell(n)} | {o} | {_cell(m)} |" for i, n, o, m in problems[:40]]
        out.append("")

    # what this run changed
    if before is not None:
        changes = []
        for i, s in st.items():
            b = before.get(i)
            if b is None:
                changes.append((i, "new", s.display_truth, "new", s.eff_faith))
            else:
                was = b.get("last_truth", b.get("truth")) if b.get("stale") else b.get("truth")
                if was != s.display_truth or b.get("faithfulness") != s.eff_faith:
                    changes.append((i, was, s.display_truth, b.get("faithfulness"), s.eff_faith))
        removed = sorted(set(before) - set(st))
        out.append("### Changed in this run")
        if changes or removed:
            out += ["| Node | Truth | Faithfulness |", "| --- | --- | --- |"]
            for i, tb, ta, fb, fa in sorted(changes):
                t = _label(ta) if tb == ta else f"{_label(tb)} → **{_label(ta)}**"
                f = fa if fb == fa else f"{fb} → **{fa}**"
                out.append(f"| `{i}` | {t} | {f} |")
            out += [f"| `{i}` | removed | |" for i in removed]
        else:
            out.append("No status changed.")
        out.append("")

    if ran is not None:
        if ran:
            secs = sum(r.get("seconds") or 0 for r in ran)
            out.append(f"<details><summary>{len(ran)} check(s) ran ({secs:.0f} s)</summary>\n")
            out += ["| Node | Check | Why | Result |", "| --- | --- | --- | --- |"]
            out += [f"| `{r['node']}` | {r['check']} | {r['reason']} | {r['outcome']}"
                    f"{' → ' + _label(r['grants']) if r.get('grants') else ''} |" for r in ran]
            out += ["", "</details>", ""]
        else:
            out += ["No checks needed to run: all evidence was fresh.", ""]

    # totals
    truth = counts["truth"]
    out.append("### Status of all nodes")
    out += ["| " + " | ".join(_label(t) for t in TRUTH_DISPLAY if truth.get(t)) + " |",
            "| " + " | ".join("---:" for t in TRUTH_DISPLAY if truth.get(t)) + " |",
            "| " + " | ".join(str(truth[t]) for t in TRUTH_DISPLAY if truth.get(t)) + " |", ""]
    faith = counts["faithfulness"]
    out.append("Faithfulness: " + ", ".join(f"{faith[k]} {k.replace('_', '-')}" for k in reversed(FAITH_ORDER)
                                            if faith.get(k)) + ".")
    out.append("")

    queue = sorted((s for s in st.values() if s.queue_score > 0), key=lambda s: (-s.queue_score, s.id))[:8]
    if queue:
        out += ["### Review queue (top 8)",
                "Record a review from **Actions → review → Run workflow**.", "",
                "| Node | Faithfulness | Descendants |", "| --- | --- | ---: |"]
        out += [f"| `{s.id}` | {s.own_faith.replace('_', '-')} | {s.descendants} |" for s in queue]
        out.append("")
    return "\n".join(out)
