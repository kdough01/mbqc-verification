"""
dagtool — validate, run and inspect the theorem DAG.

    dagtool validate                     schema, ids, edges, cycles, converters
    dagtool run [--stale] [--node ID]... [--kind K]... [--quick]
                                         run checks and write dag/evidence/
    dagtool status [--json] [--node ID]  computed status of every node
    dagtool show ID                      one node: statement, edges, evidence, flags
    dagtool queue [-n N]                 human review queue, most valuable first
    dagtool review ID --reviewer NAME --decision approve|reject [--notes TEXT]
    dagtool repro [--node ID]... [--kind K]...   re-run checks, compare verdicts
    dagtool render [--out PATH]          the theorem browser (self-contained HTML)
    dagtool summary [--before F] [--ran F] [--browser-url U]   Markdown report for CI
    dagtool check                        CI gate: exit 1 on stale evidence, failures or bad edges
    dagtool pull-papers [--server URL]   add open theorems from the review site as dag/nodes/papers/
    dagtool export [--out PATH]          computed DAG as JSON (nodes, edges, status, verdicts)

Run from the repository root (or pass --root).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .model import DagError, load_dag


def _status(dag):
    from .status import compute
    return compute(dag)


def cmd_validate(dag, args):
    from .status import edge_convention_conflicts
    print(f"ok: {len(dag.nodes)} nodes, {len(dag.edges)} edges, no cycles")
    for e, left in edge_convention_conflicts(dag):
        acknowledged = "convention_mismatch" in dag.nodes[e.dst].acknowledged
        level = "info" if e.kind == "variant_of" or acknowledged else "warn"
        print(f"  {level}: {e.src} -> {e.dst} ({e.kind}) conventions differ: {left}")
    return 0


def cmd_run(dag, args):
    from .evidence import prune
    from .runner import plan, run
    for f in prune(dag):
        print(f"removed evidence of a check that no longer exists: {f.relative_to(dag.root)}")
    planned = plan(dag, node_ids=set(args.node or []), kinds=set(args.kind or []), only_stale=args.stale)
    if not planned:
        print("nothing to run: all evidence is fresh")
        if args.report:
            Path(args.report).write_text("[]\n", encoding="utf-8")
        return 0
    records = run(dag, planned, quick=args.quick)
    if args.report:
        reasons = {(p.node.id, p.spec.name): p.reason for p in planned}
        Path(args.report).write_text(json.dumps([
            {"node": r["node"], "check": r["name"], "kind": r["kind"], "reason": reasons[(r["node"], r["name"])],
             "outcome": r["result"]["outcome"], "grants": r["result"]["grants"], "summary": r["result"]["summary"],
             "seconds": r["provenance"]["seconds"]} for r in records], indent=1) + "\n", encoding="utf-8")
    bad = [r for r in records if r["result"]["outcome"] == "error"]
    for r in bad:
        print(f"ERROR {r['node']} :: {r['name']}: {r['result']['summary']}", file=sys.stderr)
    return 1 if bad else 0


def cmd_status(dag, args):
    from .status import summary_counts
    st = _status(dag)
    if args.json:
        out = {i: {"truth": s.display_truth, "own_truth": s.own_truth, "last_truth": s.last_truth,
                   "domain": s.own_domain,
                   "faithfulness": s.eff_faith, "own_faithfulness": s.own_faith, "frontier": s.frontier,
                   "stale": s.stale, "upstream_stale": s.upstream_stale,
                   "flags": [f.__dict__ for f in s.flags]} for i, s in st.items()}
        print(json.dumps(out, indent=1))
        return 0
    ids = args.node or dag.topo_order()
    w = max(len(i) for i in ids)
    print(f"{'node':{w}s}  {'truth':14s} {'faithfulness':14s} notes")
    for i in ids:
        s = st[i]
        notes = []
        if s.stale:
            notes.append("STALE")
        elif s.upstream_stale:
            notes.append("upstream stale")
        if s.frontier:
            notes.append(f"frontier: {', '.join(s.frontier)}")
        warns = [f.code for f in s.flags if f.level == "warn" and f.code not in ("stale", "broken")]
        if warns:
            notes.append("flags: " + ", ".join(sorted(set(warns))))
        print(f"{i:{w}s}  {s.display_truth:14s} {s.eff_faith:14s} {'; '.join(notes)}")
    c = summary_counts(st)
    print(f"\ntruth: {c['truth']}\nfaithfulness: {c['faithfulness']}")
    return 0


def cmd_show(dag, args):
    if args.id not in dag.nodes:
        print(f"unknown node {args.id}", file=sys.stderr)
        return 2
    n, s = dag.nodes[args.id], _status(dag)[args.id]
    print(f"{n.id}  [{n.kind}{', layer ' + n.layer if n.layer else ''}]  {n.title}\n")
    print(f"  {n.statement.strip()}\n")
    print(f"  truth: {s.display_truth} (own: {s.own_truth}{', on ' + s.own_domain if s.own_domain else ''})")
    print(f"  faithfulness: {s.eff_faith} (own: {s.own_faith}; required checks: {s.faith_required or 'none'}"
          f"{'; missing ' + str(s.faith_missing) if s.faith_missing else ''})")
    if s.frontier:
        print(f"  frontier: {', '.join(s.frontier)}")
    print(f"  statement hash: {s.statement_hash}")
    for e in dag.parents(n.id, kinds=("uses", "assumes", "instantiates", "variant_of")):
        print(f"  <- {e.kind:12s} {e.src}")
    for e in dag.children(n.id, kinds=("uses", "assumes", "instantiates", "variant_of")):
        print(f"  -> {e.kind:12s} {e.dst}")
    for ev in s.evidence:
        print(f"  evidence {ev.name:14s} {ev.outcome:5s} {ev.grants or '':10s} {'' if ev.fresh else 'STALE '}{ev.summary}")
    for f in s.flags:
        print(f"  {f.level}: {f.code}: {f.message}")
    return 0


def cmd_queue(dag, args):
    st = _status(dag)
    rows = sorted((s for s in st.values() if s.queue_score > 0), key=lambda s: (-s.queue_score, s.id))
    print(f"{'score':>6s}  {'node':40s} {'own faith':14s} {'desc':>4s}  why")
    for s in rows[: args.n]:
        n = dag.nodes[s.id]
        why = [f.code for f in s.flags if f.level == "warn"]
        if n.needs_human_review and s.own_faith != "human_reviewed":
            why.insert(0, f"{n.kind} needs review")
        print(f"{s.queue_score:6.0f}  {s.id:40s} {s.own_faith:14s} {s.descendants:4d}  {', '.join(why)}")
    return 0


def cmd_review(dag, args):
    from .evidence import Review, append_review
    from .hashing import statement_hash
    if args.id not in dag.nodes:
        print(f"unknown node {args.id}", file=sys.stderr)
        return 2
    n = dag.nodes[args.id]
    h = statement_hash(n)
    print(f"Reviewing {n.id}: {n.title}\n\n  {n.statement.strip()}\n")
    if n.statement_tex:
        print(f"  TeX: {n.statement_tex.strip()}\n")
    print(f"  conventions: {n.conventions.as_dict() or 'none'}")
    defs = sorted(a for a in dag.ancestors(n.id) if dag.nodes[a].kind == "definition")
    for d in defs:
        print(f"  rests on definition {d}: {dag.nodes[d].statement.strip()}")
    print(f"\n  statement hash: {h}")
    path = append_review(dag, n.id, Review(reviewer=args.reviewer, date=args.date or "", statement_hash=h,
                                           decision=args.decision, notes=args.notes or ""))
    print(f"recorded {args.decision} in {path.relative_to(dag.root)}")
    return 0


def cmd_repro(dag, args):
    from .runner import plan, repro
    planned = plan(dag, node_ids=set(args.node or []), kinds=set(args.kind or []))
    diffs = repro(dag, planned, quick=args.quick)
    return 1 if diffs else 0


def cmd_summary(dag, args):
    from .summary import markdown
    before = json.loads(Path(args.before).read_text(encoding="utf-8")) if args.before and Path(args.before).exists() else None
    ran = json.loads(Path(args.ran).read_text(encoding="utf-8")) if args.ran and Path(args.ran).exists() else None
    print(markdown(dag, before=before, ran=ran, browser_url=args.browser_url))
    return 0


def cmd_render(dag, args):
    from .render import render
    out = Path(args.out) if args.out else dag.root / "dag" / "build" / "index.html"
    render(dag, out)
    print(f"wrote {out}")
    return 0


def cmd_check(dag, args):
    """CI gate."""
    from .summary import regressions
    st = _status(dag)
    problems = []
    if args.before and Path(args.before).exists():
        before = json.loads(Path(args.before).read_text(encoding="utf-8"))
        for i, was, now in regressions(st, before, dag):
            problems.append(f"{i}: regression: truth went from {was} to {now} in this run")
    for i, s in st.items():
        if s.stale:
            problems.append(f"{i}: stale evidence (run `dagtool run --stale`)")
        for f in s.flags:
            if f.code in ("check_failed", "mutation_survived", "missing_evidence"):
                problems.append(f"{i}: {f.code}: {f.message}")
            if f.code == "convention_mismatch" and f.level == "warn" and not args.allow_convention_warnings:
                problems.append(f"{i}: {f.code}: {f.message}")
    for p in problems:
        print(p)
    print(f"{len(problems)} problem(s)")
    return 1 if problems else 0


def cmd_pull_papers(dag, args):
    import urllib.error

    from .papers import pull
    try:
        written = pull(dag, args.server, dry_run=args.dry_run)
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"could not read open theorems from {args.server}: {e}", file=sys.stderr)
        return 1
    for p in written:
        print(("would add " if args.dry_run else "added ") + p.relative_to(dag.root).as_posix())
    print(f"{len(written)} new paper theorem(s)")
    return 0


def cmd_export(dag, args):
    from .papers import export
    text = json.dumps(export(dag, circuits=not args.no_circuits), ensure_ascii=False, default=str)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="dagtool", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="repository root (default: current directory)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    p = sub.add_parser("run")
    p.add_argument("--stale", action="store_true", help="only checks whose evidence is missing or stale")
    p.add_argument("--node", action="append")
    p.add_argument("--kind", action="append")
    p.add_argument("--quick", action="store_true", help="smaller grids (evidence records a smaller domain)")
    p.add_argument("--report", help="write a JSON list of the checks that ran (for dagtool summary)")
    p = sub.add_parser("status")
    p.add_argument("--json", action="store_true")
    p.add_argument("--node", action="append")
    p = sub.add_parser("show")
    p.add_argument("id")
    p = sub.add_parser("queue")
    p.add_argument("-n", type=int, default=20)
    p = sub.add_parser("review")
    p.add_argument("id")
    p.add_argument("--reviewer", required=True)
    p.add_argument("--decision", choices=["approve", "reject"], required=True)
    p.add_argument("--notes")
    p.add_argument("--date")
    p = sub.add_parser("repro")
    p.add_argument("--node", action="append")
    p.add_argument("--kind", action="append")
    p.add_argument("--quick", action="store_true")
    p = sub.add_parser("summary", help="Markdown report for a CI run summary")
    p.add_argument("--before", help="`dagtool status --json` output saved before the run")
    p.add_argument("--ran", help="the JSON report written by `dagtool run --report`")
    p.add_argument("--browser-url", help="where the rendered theorem browser is published")
    p = sub.add_parser("render")
    p.add_argument("--out")
    p = sub.add_parser("check")  # acknowledged warnings are information and pass
    p.add_argument("--allow-convention-warnings", action="store_true")
    p.add_argument("--before", help="`dagtool status --json` saved before the run; a node whose truth got weaker fails")
    from .papers import DEFAULT_SERVER
    p = sub.add_parser("pull-papers", help="add open theorems from the review site")
    p.add_argument("--server", default=DEFAULT_SERVER)
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("export", help="computed DAG as JSON")
    p.add_argument("--out")
    p.add_argument("--no-circuits", action="store_true")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    sys.path[:0] = [str(root), str(root / "src"), str(root / "tools")]
    try:
        dag = load_dag(root)
    except DagError as e:
        print(f"invalid DAG:\n{e}", file=sys.stderr)
        return 2
    return globals()[f"cmd_{args.cmd.replace('-', '_')}"](dag, args)


if __name__ == "__main__":
    sys.exit(main())
