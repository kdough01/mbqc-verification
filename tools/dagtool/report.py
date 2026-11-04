"""
report.py — per-paper verification reports: what was checked, how, and what came out.

    dagtool report                      -> dag/build/reports/<id>.html and index.html
    dagtool report --out site/reports   (CI publishes them next to the theorem browser)

A report combines a hand-written narrative (dag/reports/<id>.yaml: scope, the approach step by step, the
configuration, findings, open items, figure specs) with the live DAG: every node's computed status, every
check's latest evidence, and the committed results files the figures read. Narrative is written once; numbers,
outcomes and statuses are never copied into it, so the page cannot drift from the evidence.

Pages are static and self-contained (no scripts): inline CSS using the theorem browser's tokens, HTML bar and
strip charts, one inline SVG for the dependency graph, and a table view under every figure.
"""

from __future__ import annotations

import html
import json
import math
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path

import yaml

from .evidence import git_commit, now_utc
from .model import Dag
from .render import TEMPLATE as BROWSER, _slug
from .status import compute

REPORTS_DIR = ("dag", "reports")
DEFAULT_REPO = "https://github.com/kdough01/mbqc-verification"
TRUTH_VAR = {"proved": "t-proved", "proved_modulo": "t-modulo", "defined": "t-defined", "assumed": "t-assumed",
             "bounded": "t-bounded", "empirical": "t-empirical", "conjecture": "t-conjecture",
             "refuted": "t-refuted", "broken": "t-broken"}
OUTCOME = {"pass": ("pass", "✓", "reproduced"), "fail": ("fail", "✗", "not reproduced"),
           "skip": ("skip", "–", "not run yet"), "error": ("error", "!", "error"),
           None: ("skip", "–", "no evidence yet")}
CONFIG_BADGE = {"stated": "stated", "ambiguous": "ambiguous", "not stated": "not stated",
                "calibrated": "settled by calibration"}


class ReportError(ValueError):
    pass


# ---------------------------------------------------------------- small helpers

def esc(s) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def inline(text) -> str:
    """Escape, then `code`, **bold**, *italic* and [label](url); nothing is interpreted inside code spans."""
    out = []
    for k, part in enumerate(re.split(r"`([^`]+)`", "" if text is None else str(text))):
        if k % 2:
            out.append(f"<code>{esc(part)}</code>")
            continue
        s = esc(part)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"(?<![\w*])\*([^*\s][^*]*)\*(?![\w*])", r"<i>\1</i>", s)
        s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', s)
        out.append(s)
    return "".join(out)


def num(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return str(v)
    v = float(v)
    if v == 0:
        return "0"
    if v.is_integer() and abs(v) < 1e7:
        return f"{int(v):,}"
    a = abs(v)
    if a >= 1e6:
        return f"{v / 1e6:.3g}M"
    if a < 1e-3:
        return f"{v:.3g}"
    return f"{v:.4g}"


def get_path(data, path: str):
    for part in path.split("."):
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


def repo_url(root: Path) -> str:
    if os.environ.get("GITHUB_REPOSITORY"):
        return f"https://github.com/{os.environ['GITHUB_REPOSITORY']}"
    try:
        url = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"], capture_output=True,
                             text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        url = ""
    m = re.match(r"(?:https://github\.com/|git@github\.com:)([^/]+/[^/]+?)(?:\.git)?$", url)
    return f"https://github.com/{m.group(1)}" if m else DEFAULT_REPO


def tokens_css() -> tuple[str, str]:
    """The browser's font link and color/type tokens (light, dark and forced themes), so both pages match."""
    page = BROWSER.read_text(encoding="utf-8")
    fonts = re.search(r'<link rel="stylesheet" href="https://fonts\.googleapis\.com[^>]*>', page).group(0)
    tokens = re.search(r'(?s)(:root \{.*?:root\[data-theme="dark"\] \{[^}]*\})', page).group(1)
    return fonts, tokens


def load_spec(path: Path) -> dict:
    spec = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for key in ("id", "title"):
        if not spec.get(key):
            raise ReportError(f"{path}: missing `{key}`")
    return spec


TOOLKIT_FILE = "toolkit.yaml"


def report_specs(root: Path) -> list[tuple[Path, dict]]:
    d = root.joinpath(*REPORTS_DIR)
    if not d.exists():
        return []
    return [(p, load_spec(p)) for p in sorted(d.glob("*.yaml")) if p.name != TOOLKIT_FILE]


def load_toolkit(root: Path) -> dict:
    """dag/reports/toolkit.yaml: strategies that carry over between papers, and the verification tools we use or may
    use, with when each applies. Shared by every report and the index."""
    p = root.joinpath(*REPORTS_DIR, TOOLKIT_FILE)
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.exists() else {}


# ---------------------------------------------------------------- the model a page is built from

class Context:
    def __init__(self, dag: Dag, spec: dict, st=None):
        self.dag, self.spec = dag, spec
        self.st = st if st is not None else compute(dag)
        self.repo = repo_url(dag.root)
        base = dag.root / "dag" / "nodes" / "reproductions" / spec["id"]
        own = [i for i, n in dag.nodes.items() if base in n.path.parents]
        referenced = []
        for sec in ("steps", "findings"):
            for item in spec.get(sec, []) or []:
                referenced += item.get("nodes", []) or []
        for fig in spec.get("figures", []) or []:
            referenced += [c["node"] for c in fig.get("columns", []) or []]
        missing = sorted({i for i in referenced if i not in dag.nodes})
        if missing:
            raise ReportError(f"report {spec['id']}: unknown nodes {', '.join(missing)}")
        order = {i: k for k, i in enumerate(dag.topo_order())}
        self.nodes = sorted(set(own) | set(referenced), key=lambda i: order[i])
        self.evidence = {i: {e.name: e for e in self.st[i].evidence} for i in self.nodes}
        self._files: dict[str, object] = {}

    def file(self, rel: str):
        if rel not in self._files:
            p = self.dag.root / rel
            self._files[rel] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
        return self._files[rel]

    def blob(self, rel: str) -> str:
        kind = "tree" if (self.dag.root / rel).is_dir() else "blob"
        return f"{self.repo}/{kind}/main/{rel}"

    def browser(self, node_id: str) -> str:
        return f"../index.html#{_slug(node_id)}"

    def checks(self):
        """Every check of every report node with its latest evidence (None if it never ran)."""
        for i in self.nodes:
            for c in self.dag.nodes[i].checks:
                yield i, c, self.evidence[i].get(c.name)


# ---------------------------------------------------------------- pieces

def status_chip(ctx: Context, node_id: str, label: bool = True) -> str:
    s = ctx.st[node_id]
    truth = s.display_truth
    ack = "refuted" in (ctx.dag.nodes[node_id].acknowledged or {})
    extra = " · acknowledged" if ack and truth == "refuted" else ""
    stale = " · stale" if s.stale else ""
    title = ctx.dag.nodes[node_id].title
    text = f'<span class="nid">{esc(node_id)}</span>' if label else ""
    return (f'<a class="chip-node" href="{esc(ctx.browser(node_id))}" title="{esc(title)}">'
            f'<span class="sw" style="background:var(--{TRUTH_VAR.get(truth, "t-conjecture")})"></span>'
            f'{text}<span class="st">{esc(truth)}{extra}{stale}</span></a>')


GENERIC = {"pass": "pass", "fail": "fail"}


def outcome_badge(outcome, kind: str = "reproduction") -> str:
    cls, mark, word = OUTCOME.get(outcome, OUTCOME[None])
    if kind != "reproduction":
        word = GENERIC.get(outcome, word)
    return f'<span class="oc {cls}"><span aria-hidden="true">{mark}</span> {esc(word)}</span>'


def file_links(ctx: Context, files) -> str:
    out = []
    for f in files or []:
        exists = (ctx.dag.root / f).exists()
        name = f.split("/")[-1]
        out.append(f'<a class="file" href="{esc(ctx.blob(f))}" title="{esc(f)}">{esc(name)}</a>' if exists
                   else f'<span class="file missing" title="{esc(f)} (not committed yet)">{esc(name)}</span>')
    return " ".join(out)


def table(headers, rows, cls="") -> str:
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tablewrap"><table class="{cls}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def details_table(headers, rows) -> str:
    return f'<details class="tv"><summary>Table view</summary>{table(headers, rows)}</details>'


# ---------------------------------------------------------------- figures

def check_values(ev):
    if ev is None:
        return None, None
    e = (ev.record.get("result") or {}).get("evidence") or {}
    return e.get("value"), e.get("expect")


def fig_check_matrix(ctx: Context, fig: dict) -> str:
    cols = fig["columns"]
    rows = fig["rows"]
    head = '<th scope="col">Quantity</th>' + "".join(
        f'<th scope="col"><a href="{esc(ctx.browser(c["node"]))}">{esc(c["label"])}</a></th>' for c in cols)
    body, tv = [], []
    for name, label in rows.items():
        cells, tvrow = [f'<th scope="row">{esc(label)}</th>'], [esc(label)]
        for c in cols:
            ev = ctx.evidence[c["node"]].get(name)
            outcome = ev.outcome if ev else None
            cls, mark, word = OUTCOME.get(outcome, OUTCOME[None])
            value, expect = check_values(ev)
            if value is not None and expect:
                inner = (f'<span class="mk" aria-hidden="true">{mark}</span><span class="v">{num(value)}</span>'
                         f'<span class="vs">paper {num(expect)}</span><span class="r">×{value / expect:.3g}</span>')
                tvrow.append(f"{word}: {num(value)} vs {num(expect)}")
            else:
                inner = f'<span class="mk" aria-hidden="true">{mark}</span><span class="vs">{esc(word)}</span>'
                tvrow.append(esc(word))
            stale = "" if (ev is None or ev.fresh) else " stale"
            tip = ev.summary if ev else "this check has not run"
            cells.append(f'<td class="cell {cls}{stale}" title="{esc(tip)}">{inner}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
        tv.append(tvrow)
    legend = ('<div class="legend">' + "".join(
        f'<span class="oc {k}"><span aria-hidden="true">{m}</span> {w}</span>'
        for k, m, w in (OUTCOME["pass"], OUTCOME["fail"], OUTCOME["skip"])) + "</div>")
    return (f'<div class="tablewrap"><table class="matrix"><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>{legend}')


MARKERS = ["circle", "square", "diamond", "triangle", "circle"]
RAMP = ["--r2", "--r4", "--r3", "--r5", "--r1"]


def ratio_points(ctx: Context, fig: dict, figures: dict):
    """(columns, row labels, points) for a ratio strip. Points are (row label, column, ours/paper, ours, paper)."""
    pts = []
    if "series" in fig:              # comparison files written by experiments (quantities.<q>.ours / .paper)
        cols, rows = fig["series"], fig["rows"]
        for k, s in enumerate(cols):
            data = ctx.file(s["file"]) or {}
            for q, label in rows.items():
                e = (data.get("quantities") or {}).get(q)
                if e and e.get("paper"):
                    pts.append((label, k, float(e["ours"]) / float(e["paper"]), float(e["ours"]), float(e["paper"])))
        return cols, rows, pts
    base = figures[fig["of"]]
    cols, rows = base["columns"], base["rows"]
    for name, label in rows.items():
        for k, c in enumerate(cols):
            value, expect = check_values(ctx.evidence[c["node"]].get(name))
            if value is not None and expect:
                pts.append((label, k, value / expect, value, expect))
    return cols, rows, pts


def fig_ratio_strip(ctx: Context, fig: dict, figures: dict) -> str:
    cols, rows, pts = ratio_points(ctx, fig, figures)
    if not pts:
        return '<p class="muted">No results yet.</p>'
    used = sorted({p[1] for p in pts})
    lo = math.log10(min(0.5, min(p[2] for p in pts) / 1.15))
    hi = math.log10(max(2.0, max(p[2] for p in pts) * 1.15))
    x = lambda r: 100 * (math.log10(r) - lo) / (hi - lo)   # noqa: E731
    tol = float(fig.get("tolerance", 0.01))
    ticks = [t for t in (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50) if lo <= math.log10(t) <= hi]
    grid = "".join(f'<span class="gl{" one" if t == 1 else ""}" style="left:{x(t):.2f}%"></span>' for t in ticks)
    band = f'<span class="band" style="left:{x(1 - tol):.2f}%;width:{x(1 + tol) - x(1 - tol):.2f}%"></span>'
    out = []
    for name, label in rows.items():
        marks = "".join(
            f'<span class="pt {MARKERS[k]}" style="left:{x(r):.2f}%;top:calc(50% + {(used.index(k) - (len(used) - 1) / 2) * 9:.1f}px);--c:var({RAMP[k]})" '
            f'title="{esc(cols[k]["label"])}: {num(v)} vs paper {num(e)} (×{r:.3g})"></span>'
            for (lab, k, r, v, e) in pts if lab == label)
        out.append(f'<div class="srow"><div class="slab">{esc(label)}</div>'
                   f'<div class="track">{grid}{band}{marks}</div></div>')
    axis = "".join(f'<span class="tk" style="left:{x(t):.2f}%">{t:g}×</span>' for t in ticks)
    legend = '<div class="legend">' + "".join(
        f'<span><span class="pt static {MARKERS[k]}" style="--c:var({RAMP[k]})"></span>{esc(cols[k]["label"])}</span>'
        for k in used) + '<span><span class="bandkey"></span>within tolerance</span></div>'
    tv = details_table(["Quantity", "Instance", "Ours", "Paper", "Ours ÷ paper"],
                       [[esc(lab), esc(cols[k]["label"]), num(v), num(e), f"{r:.3g}"] for lab, k, r, v, e in pts])
    return (f'{legend}<div class="strip">{"".join(out)}<div class="srow axis"><div class="slab"></div>'
            f'<div class="track">{axis}</div></div></div>{tv}')


def bar_groups(ctx: Context, fig: dict):
    groups = []
    for g in fig["groups"]:
        data = ctx.file(g["file"])
        items = []
        if data is None:
            groups.append((g["label"], None, g["file"]))
            continue
        if "rows" in g:
            spec = g["rows"]
            for row in get_path(data, spec["path"]):
                try:
                    v = get_path(row, spec["value"])
                except (KeyError, IndexError, TypeError):
                    v = None
                lab = (spec["label"].format_map(defaultdict(lambda: "?", row)) if "{" in spec["label"]
                       else row.get(spec["label"], "?"))
                items.append((lab, v, row.get("error") or (None if v is not None else "no value")))
        else:
            for it in g["items"]:
                try:
                    items.append((it["label"], get_path(data, it["path"]), None))
                except (KeyError, IndexError, TypeError):
                    items.append((it["label"], None, "missing in results"))
        groups.append((g["label"], items, g["file"]))
    return groups


def fig_bars(ctx: Context, fig: dict) -> str:
    rel = bool(fig.get("relative"))
    log = fig.get("scale") == "log"
    thr = fig.get("threshold")
    ref = fig.get("reference")
    unit = fig.get("unit", "")
    out, tv = [], []
    groups = bar_groups(ctx, fig)
    allv = []
    for _, items, _ in groups:
        if items:
            b0 = next((v for _, v, _ in items if v is not None), None)
            allv += [(v / b0 if rel and b0 else v) for _, v, _ in items if v is not None]
    per_group = fig.get("scale_per_group", False)
    top = max(allv + [1.0 if rel else 0.0]) or 1.0
    if ref is not None:
        top = max(top, ref)
    lo = math.floor(math.log10(max(min([v for v in allv if v > 0] or [1e-3]), 1e-12))) if log else 0
    if log and lo >= math.log10(top):
        lo = math.log10(top) - 1
    for label, items, f in groups:
        if items is None:
            out.append(f'<div class="bgroup"><h4>{esc(label)}</h4><p class="muted">No results yet ({esc(f)}).</p></div>')
            continue
        base = next((v for _, v, _ in items if v is not None), None) if rel else None
        vals = [(lab, (None if v is None else v / base if rel and base else v), err, v) for lab, v, err in items]
        if per_group and not log:
            top = max([v for _, v, _, _ in vals if v is not None] + [1.0 if rel else 0.0]) or 1.0
        if log:
            pos = lambda v: 0 if v <= 0 else max(1.5, 100 * (math.log10(v) - lo) / (math.log10(top) - lo))  # noqa: E731
        else:
            pos = lambda v: 100 * v / top   # noqa: E731
        rows = []
        for lab, v, err, raw in vals:
            if v is None:
                rows.append(f'<div class="brow"><div class="blab">{esc(lab)}</div><div class="btrack"></div>'
                            f'<div class="bval err" title="{esc(err)}">failed</div></div>')
                tv.append([esc(label), esc(lab), esc(err or "—")])
                continue
            state = ""
            if thr is not None:
                state = " ok" if v >= thr else " bad"
            text = f"{v:.3g}×" if rel else f"{num(v)}{(' ' + unit) if unit else ''}"
            mark = (' <span aria-hidden="true">✓</span>' if v >= thr else ' <span aria-hidden="true">✗</span>') if thr is not None else ""
            tip = f"{lab}: {num(raw)}{(' ' + unit) if unit else ''}" + (f" ({v:.3g}× baseline)" if rel else "")
            rows.append(f'<div class="brow" title="{esc(tip)}"><div class="blab">{esc(lab)}</div>'
                        f'<div class="btrack"><span class="bar{state}" style="width:{pos(v):.2f}%"></span>'
                        + (f'<span class="ref" style="left:{pos(1.0):.2f}%"></span>' if rel else "")
                        + (f'<span class="ref thr" style="left:{pos(thr):.2f}%"></span>' if thr is not None else "")
                        + (f'<span class="ref" style="left:{pos(ref):.2f}%"></span>' if ref is not None else "")
                        + f'</div><div class="bval">{text}{mark}</div></div>')
            tv.append([esc(label), esc(lab), f"{num(raw)}{(' ' + unit) if unit else ''}" + (f" ({v:.3g}×)" if rel else "")])
        src = f'<a class="file" href="{esc(ctx.blob(f))}">{esc(f.split("/")[-1])}</a>'
        out.append(f'<div class="bgroup"><h4>{esc(label)} <span class="src">{src}</span></h4>{"".join(rows)}</div>')
    note = ""
    if rel:
        note = '<p class="fnote">The thin mark is the baseline (1.0×).</p>'
    if thr is not None:
        note = f'<p class="fnote">The thin mark is the pass threshold ({thr:g}); log scale.</p>'
    if ref is not None:
        note = f'<p class="fnote">The thin mark is {esc(fig.get("reference_label", f"{ref:g}"))}{"; log scale" if log else ""}.</p>'
    return f'<div class="bgrid">{"".join(out)}</div>{note}' + details_table(["Group", "Item", "Value"], tv)


def fig_ranking(ctx: Context, fig: dict) -> str:
    """Grid points ranked by how many columns they reproduce (calibrate.py's summary)."""
    data = ctx.file(fig["file"])
    if data is None:
        return f'<p class="muted">No results yet ({esc(fig["file"])}).</p>'
    ranked = get_path(data, fig["path"])
    total = get_path(data, fig["of"])
    names = fig.get("names", {})
    top = ranked[: int(fig.get("top", 10))]
    rows, tv = [], []
    for k, e in enumerate(top):
        lab = ", ".join(f"{names.get(a, a)} {v}" for a, v in e["point"].items() if a in names)
        w = 100 * e["matched"] / total if total else 0
        cls = " ok" if k == 0 else ""
        rows.append(f'<div class="brow rank" title="{esc(lab)}: {e["matched"]} of {total} columns within 1%">'
                    f'<div class="blab">{"<b>" if k == 0 else ""}{esc(lab)}{"</b>" if k == 0 else ""}</div>'
                    f'<div class="btrack"><span class="bar{cls}" style="width:{w:.2f}%"></span></div>'
                    f'<div class="bval">{e["matched"]}/{total}</div></div>')
        tv.append([str(k + 1), esc(lab), f'{e["matched"]}/{total}'])
    axes = get_path(data, fig["axes"]) if fig.get("axes") else {}
    axis_rows = [[esc(names.get(a, a)), esc(x["value"]), "—" if x["best"] is None else f'{x["best"]}/{total}']
                 for a, vals in axes.items() if a in names for x in vals]
    axis_tab = (f'<details class="tv"><summary>Best score for each setting value</summary>'
                f'{table(["Setting", "Value", "Best over the grid"], axis_rows)}</details>') if axis_rows else ""
    src = f'<a class="file" href="{esc(ctx.blob(fig["file"]))}">{esc(fig["file"].split("/")[-1])}</a>'
    return (f'<div class="bgroup"><h4>Top {len(top)} of {len(ranked)} settings <span class="src">{src}</span></h4>'
            f'{"".join(rows)}</div>{axis_tab}' + details_table(["Rank", "Settings", "Columns reproduced"], tv))


def _ticks_log(lo: float, hi: float) -> list[float]:
    out = []
    for e in range(math.floor(math.log10(lo)), math.ceil(math.log10(hi)) + 1):
        for m in (1, 2, 5):
            v = m * 10 ** e
            if lo <= v <= hi:
                out.append(v)
    if len(out) <= 7:
        return out
    return [v for v in out if abs(v / 10 ** math.floor(math.log10(v)) - 1) < 1e-9]


def fig_scaling(ctx: Context, fig: dict) -> str:
    """Small multiples of measured values against problem size: our runs (filled, joined) and the paper's printed
    values (hollow) where Table II has them. Nothing is fitted or extrapolated."""
    data = ctx.file(fig["file"])
    if data is None:
        return f'<p class="muted">No results yet ({esc(fig["file"])}).</p>'
    pts = data["series"][fig["series"]]["points"]
    panels, tv = [], []
    W, H, L, R, T, B = 470, 250, 62, 14, 14, 36
    xs = [p["n"] for p in pts]
    xlo, xhi = min(xs), max(xs)
    xlog = fig.get("xlog", False)
    def X(n):
        if xlog:
            return L + (W - L - R) * (math.log10(n) - math.log10(xlo)) / ((math.log10(xhi) - math.log10(xlo)) or 1)
        return L + (W - L - R) * (n - xlo) / ((xhi - xlo) or 1)
    for pan in fig["panels"]:
        ours = [(p["n"], get_path(p, pan["key"]), p["label"]) for p in pts]
        paper = [(p["n"], p["paper"][pan["paper"]], p["label"]) for p in pts if p.get("paper") and pan.get("paper")]
        vals = [v for _, v, _ in ours + paper if v]
        lo, hi = min(vals) / 1.3, max(vals) * 1.3
        def Y(v):
            return T + (H - T - B) * (1 - (math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)))
        grid = "".join(f'<line class="g" x1="{L}" x2="{W - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}"/>'
                       f'<text class="yt" x="{L - 6}" y="{Y(v) + 4:.1f}">{num(v)}</text>' for v in _ticks_log(lo, hi))
        xt = sorted(set(fig.get("xticks", xs)))
        xticks = "".join(f'<text class="xt" x="{X(n):.1f}" y="{H - B + 16}">{n}</text>' for n in xt if xlo <= n <= xhi)
        line = " ".join(f"{X(n):.1f},{Y(v):.1f}" for n, v, _ in ours if v)
        dots = "".join(f'<circle class="o" cx="{X(n):.1f}" cy="{Y(v):.1f}" r="4"><title>{esc(lab)}: {num(v)} {esc(pan.get("unit", ""))} (our run)</title></circle>'
                       for n, v, lab in ours if v)
        pdots = "".join(f'<rect class="p" x="{X(n) - 5:.1f}" y="{Y(v) - 5:.1f}" width="10" height="10" transform="rotate(45 {X(n):.1f} {Y(v):.1f})">'
                        f'<title>{esc(lab)}: {num(v)} {esc(pan.get("unit", ""))} (paper, Table II)</title></rect>' for n, v, lab in paper)
        panels.append(f'<figure class="pan"><figcaption>{esc(pan["label"])}{(" (" + esc(pan["unit"]) + ")") if pan.get("unit") else ""}</figcaption>'
                      f'<svg class="sc" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(pan["label"])} against {esc(fig.get("xlabel", "size"))}">'
                      f'{grid}<line class="ax" x1="{L}" x2="{W - R}" y1="{H - B}" y2="{H - B}"/>{xticks}'
                      f'<text class="xl" x="{(L + W - R) / 2:.0f}" y="{H - 4}">{esc(fig.get("xlabel", "size"))}</text>'
                      f'<polyline class="ol" points="{line}"/>{dots}{pdots}</svg></figure>')
        for (n, v, lab) in ours:
            pv = next((pvv for pn, pvv, _ in paper if pn == n), None)
            tv.append([esc(pan["label"]), esc(lab), num(v), num(pv) if pv is not None else "—",
                       f"{v / pv:.3g}" if pv and v else "—"])
    legend = ('<div class="legend"><span><svg width="14" height="14"><circle cx="7" cy="7" r="4" class="o"/></svg>our runs (each point is a run)</span>'
              '<span><svg width="14" height="14"><rect x="2" y="2" width="9" height="9" class="p" transform="rotate(45 7 7)"/></svg>paper, where Table II prints it</span>'
              '<span>log scale; no fitting or extrapolation</span></div>')
    src = f'<p class="fnote">Source: <a class="file" href="{esc(ctx.blob(fig["file"]))}">{esc(fig["file"].split("/")[-1])}</a></p>'
    return (f'{legend}<div class="scgrid">{"".join(panels)}</div>{src}'
            + details_table(["Quantity", "Instance", "Ours", "Paper", "Ours ÷ paper"], tv))


def figure(ctx: Context, fig: dict, figures: dict) -> str:
    kind = fig["type"]
    if kind == "check_matrix":
        body = fig_check_matrix(ctx, fig)
    elif kind == "ratio_strip":
        body = fig_ratio_strip(ctx, fig, figures)
    elif kind == "bars":
        body = fig_bars(ctx, fig)
    elif kind == "ranking":
        body = fig_ranking(ctx, fig)
    elif kind == "scaling":
        body = fig_scaling(ctx, fig)
    else:
        raise ReportError(f"unknown figure type {kind!r}")
    cap = f'<p class="cap">{inline(fig["caption"])}</p>' if fig.get("caption") else ""
    return (f'<figure class="fig" id="fig-{esc(fig["id"])}"><figcaption><h3>{esc(fig["title"])}</h3>{cap}'
            f'</figcaption>{body}</figure>')


# ---------------------------------------------------------------- dependency graph

def subgraph_svg(ctx: Context) -> str:
    ids = set(ctx.nodes)
    edges = [e for e in ctx.dag.edges if e.dst in ids and e.src in ids]
    parents = defaultdict(list)
    for e in edges:
        parents[e.dst].append(e.src)
    col: dict[str, int] = {}

    def depth(i):
        if i not in col:
            col[i] = 0 if not parents[i] else 1 + max(depth(p) for p in parents[i])
        return col[i]
    for i in ctx.nodes:
        depth(i)
    cols = defaultdict(list)
    for i in ctx.nodes:
        cols[col[i]].append(i)
    W, H, CW, RH = 230, 40, 290, 54
    tallest = max(len(v) for v in cols.values())
    pos = {}
    for c, members in cols.items():
        off = (tallest - len(members)) * RH / 2
        for r, i in enumerate(members):
            pos[i] = (16 + c * CW, 16 + off + r * RH)
    width = 16 * 2 + (max(cols) * CW) + W
    height = 16 * 2 + tallest * RH - (RH - H)
    paths = []
    for e in edges:
        (x1, y1), (x2, y2) = pos[e.src], pos[e.dst]
        x1, y1, x2, y2 = x1 + W, y1 + H / 2, x2, y2 + H / 2
        mx = (x1 + x2) / 2
        paths.append(f'<path class="e {esc(e.kind)}" d="M{x1:.1f},{y1:.1f} C{mx:.1f},{y1:.1f} {mx:.1f},{y2:.1f} {x2 - 4:.1f},{y2:.1f}" '
                     f'marker-end="url(#arr)"><title>{esc(e.src)} → {esc(e.dst)} ({esc(e.kind)})</title></path>')
    boxes = []
    for i in ctx.nodes:
        x, y = pos[i]
        n, s = ctx.dag.nodes[i], ctx.st[i]
        title = n.title if len(n.title) <= 34 else n.title[:33] + "…"
        boxes.append(
            f'<a href="{esc(ctx.browser(i))}"><g class="n"><title>{esc(i)}: {esc(n.title)} — {esc(s.display_truth)}</title>'
            f'<rect x="{x}" y="{y}" width="{W}" height="{H}" rx="6"/>'
            f'<rect x="{x}" y="{y}" width="5" height="{H}" rx="2" style="fill:var(--{TRUTH_VAR.get(s.display_truth, "t-conjecture")})"/>'
            f'<text x="{x + 14}" y="{y + 16}">{esc(title)}</text>'
            f'<text class="sub" x="{x + 14}" y="{y + 31}">{esc(n.kind)} · {esc(s.display_truth)}</text></g></a>')
    return (f'<div class="graphwrap"><svg class="sub" viewBox="0 0 {width:.0f} {height:.0f}" width="{width:.0f}" '
            f'height="{height:.0f}" role="img" aria-label="Dependency graph of the report nodes">'
            '<defs><marker id="arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">'
            '<path d="M0,0 L8,4 L0,8 z" class="ah"/></marker></defs>'
            f'{"".join(paths)}{"".join(boxes)}</svg></div>')


# ---------------------------------------------------------------- page

def tiles(ctx: Context) -> str:
    counts = defaultdict(int)
    stale = 0
    for _, _, ev in ctx.checks():
        counts[ev.outcome if ev else None] += 1
        stale += bool(ev and not ev.fresh)
    total = sum(counts.values())
    items = [("Nodes", len(ctx.nodes), ""), ("Checks", total, ""), ("Pass", counts["pass"], "pass"),
             ("Fail", counts["fail"], "fail"), ("Not run yet", counts["skip"] + counts[None], "skip")]
    if counts["error"]:
        items.append(("Errors", counts["error"], "error"))
    if stale:
        items.append(("Stale", stale, "error"))
    return '<div class="tiles">' + "".join(
        f'<div class="tile {c}"><div class="tn">{v}</div><div class="tl">{esc(k)}</div></div>' for k, v, c in items) + "</div>"


STATUS_LABEL = {"verifier": "in the verifier", "used": "pinned tool", "candidate": "candidate"}


def strategies_html(toolkit: dict) -> str:
    strategies = toolkit.get("strategies", []) or []
    groups = toolkit.get("groups") or {}
    order = list(groups) + sorted({s.get("group", "") for s in strategies} - set(groups))
    principle = (f'<p class="principle"><b>Principle.</b> {inline(toolkit["principle"])}</p>'
                 if toolkit.get("principle") else "")
    out, k = [principle], 0
    for g in order:
        members = [s for s in strategies if s.get("group", "") == g]
        if not members:
            continue
        cards = []
        for s in members:
            k += 1
            rows = "".join(f"<dt>{lab}</dt><dd>{inline(s[key])}</dd>" for key, lab in
                           (("why", "Why"), ("example", "Here"), ("how", "In the verifier")) if s.get(key))
            cards.append(f'<li class="step strat"><div class="sn">{k}</div><div class="sb"><h3>{esc(s["title"])}</h3>'
                         f'<p>{inline(s.get("what", ""))}</p><dl class="sd">{rows}</dl></div></li>')
        head = f'<h3 class="sub">{esc(groups.get(g, g))}</h3>' if g else ""
        out.append(f'{head}<ol class="steps strats">{"".join(cards)}</ol>')
    return "".join(out)


def tools_html(toolkit: dict, used: list | None = None) -> str:
    used = set(used or [])
    tools = toolkit.get("tools", []) or []
    cards = []
    for tl in tools:
        st = tl.get("status", "candidate")
        here = '<span class="badge here">used for this paper</span>' if tl["id"] in used else ""
        kinds = " ".join(f"<code>{esc(k)}</code>" for k in tl.get("check_kinds", []) or [])
        name = f'<a href="{esc(tl["url"])}">{esc(tl["name"])}</a>' if tl.get("url") else esc(tl["name"])
        rows = "".join(f"<dt>{lab}</dt><dd>{inline(tl[key])}</dd>" for key, lab in
                       (("checks", "Checks"), ("applies", "Applies when"), ("limits", "Limits")) if tl.get(key))
        if kinds:
            rows += f"<dt>Check kinds</dt><dd>{kinds}</dd>"
        cards.append(f'<article class="tool {esc(st)}" id="tool-{esc(tl["id"])}"><h3>{name} '
                     f'<span class="badge st-{esc(st)}">{esc(STATUS_LABEL.get(st, st))}</span>{here}</h3>'
                     f'<p class="cat">{esc(tl.get("category", ""))}</p><dl>{rows}</dl></article>')
    by_id = {tl["id"]: tl for tl in tools}
    matrix = []
    for m in toolkit.get("applicability", []) or []:
        chips = " ".join(f'<a class="tchip st-{esc(by_id[i].get("status", "candidate"))}" href="#tool-{esc(i)}">{esc(by_id[i]["name"])}</a>'
                         for i in m.get("tools", []) if i in by_id)
        matrix.append([f"<b>{esc(m['claim'])}</b><br><span class='muted'>{inline(m.get('example', ''))}</span>", chips,
                       inline(m.get("method", ""))])
    legend = ('<div class="legend">' + "".join(f'<span><span class="tchip st-{k}">{v}</span></span>' for k, v in STATUS_LABEL.items())
              + "</div>")
    return (f'<h3 class="sub">Which tool for which claim</h3>{table(["Claim in a paper", "Tools", "How the check runs"], matrix, "applic")}'
            f'{legend}<h3 class="sub">The tools</h3><div class="tools">{"".join(cards)}</div>')


def section(sid: str, title: str, body: str, lead: str = "") -> str:
    lead = f'<p class="lead">{lead}</p>' if lead else ""
    return f'<section id="{sid}"><h2>{esc(title)}</h2>{lead}{body}</section>'


def render_report(dag: Dag, spec: dict, st=None) -> str:
    ctx = Context(dag, spec, st)
    fonts, tokens = tokens_css()
    paper = spec.get("paper", {}) or {}
    meta = {**git_commit(dag.root), "generated": now_utc()}
    figures = {f["id"]: f for f in spec.get("figures", []) or []}
    steps = spec.get("steps", []) or []
    step_no = {s["id"]: k + 1 for k, s in enumerate(steps)}

    # header
    links = " · ".join(f'<a href="{esc(link["url"])}">{esc(link["label"])}</a>' for link in spec.get("links", []) or [])
    head = (f'<header class="hero"><p class="eyebrow">Verification report · <a href="index.html">all reports</a> · '
            f'<a href="../index.html">theorem DAG</a></p><h1>{esc(spec["title"])}</h1>'
            + (f'<p class="paper"><a href="{esc(paper.get("url"))}">{esc(paper.get("citation"))}</a></p>' if paper else "")
            + (f'<p class="kind"><span class="pill">{esc(spec["kind_of_claim"])}</span></p>' if spec.get("kind_of_claim") else "")
            + (f'<p class="summary">{inline(spec["summary"])}</p>' if spec.get("summary") else "")
            + (f'<p class="headline">{inline(spec["headline"])}</p>' if spec.get("headline") else "")
            + tiles(ctx) + (f'<p class="links">{links}</p>' if links else "") + "</header>")

    toolkit = load_toolkit(dag.root)
    nav_items = [("scope", "Scope"), ("pipeline", "Pipeline"), ("approach", "Approach"), ("configuration", "Configuration"),
                 ("results", "Results"), ("findings", "Findings"), ("strategies", "Strategies"), ("tools", "Tools"),
                 ("graph", "DAG"), ("checks", "Every check"), ("open", "Open items")]
    nav = '<nav class="toc" aria-label="Sections">' + "".join(f'<a href="#{a}">{t}</a>' for a, t in nav_items) + "</nav>"

    parts = []
    scope = spec.get("scope", []) or []
    parts.append(section("scope", "Scope", '<dl class="scope">' + "".join(
        f'<dt>{esc(s["label"])}</dt><dd>{inline(s["text"])}</dd>' for s in scope) + "</dl>"))

    stages = spec.get("pipeline", []) or []
    flow = '<ol class="flow">' + "".join(
        f'<li><div class="stage"><b>{esc(s["name"])}</b><span>{inline(s.get("detail", ""))}</span>'
        f'<span class="by">{" ".join(f"<a class=step-ref href=#step-{esc(x)}>{step_no.get(x, x)}</a>" for x in s.get("checked_by", []))}</span>'
        f'</div></li>' for s in stages) + "</ol>"
    parts.append(section("pipeline", "Pipeline under test", flow,
                         "The paper's construction, left to right. The numbers under each stage are the approach steps that check it."))

    cards = []
    for k, s in enumerate(steps, 1):
        obstacles = s.get("obstacles") or []
        obs = ('<div class="obs"><h4>What got in the way</h4><ul>' + "".join(f"<li>{inline(o)}</li>" for o in obstacles)
               + "</ul></div>") if obstacles else ""
        meta_rows = []
        if s.get("code"):
            meta_rows.append(f'<dt>Code</dt><dd>{file_links(ctx, s["code"])}</dd>')
        if s.get("results"):
            meta_rows.append(f'<dt>Results</dt><dd>{file_links(ctx, s["results"])}</dd>')
        if s.get("outputs"):
            meta_rows.append(f'<dt>Output</dt><dd>{"; ".join(inline(o) for o in s["outputs"])}</dd>')
        if s.get("nodes"):
            meta_rows.append(f'<dt>DAG</dt><dd>{" ".join(status_chip(ctx, i) for i in s["nodes"])}</dd>')
        cards.append(f'<li class="step" id="step-{esc(s["id"])}"><div class="sn">{k}</div><div class="sb">'
                     f'<h3>{esc(s["title"])}</h3><p>{inline(s.get("what", ""))}</p>{obs}'
                     f'<dl class="sm">{"".join(meta_rows)}</dl></div></li>')
    parts.append(section("approach", "Approach, step by step", f'<ol class="steps">{"".join(cards)}</ol>'))

    cfg = spec.get("config", []) or []
    cfg_tab = table(["Setting", "Value used", "In the paper", "Source"],
                    [[esc(a), inline(b), f'<span class="badge {esc(c.replace(" ", "-"))}">{esc(CONFIG_BADGE.get(c, c))}</span>', inline(d)]
                     for a, b, c, d in cfg])
    env = spec.get("environment", []) or []
    env_tab = table(["Component", "Version"], [[esc(a), f"<code>{esc(b)}</code>"] for a, b in env]) if env else ""
    parts.append(section("configuration", "Configuration and environment",
                         cfg_tab + (f"<h3>Pinned environment</h3>{env_tab}" if env_tab else ""),
                         "Every setting comes from the paper where it is stated. Settings it leaves out or states ambiguously are either settled by calibration (each value checked against the alternatives) or marked not stated, with their measured effect in the figures."))

    parts.append(section("results", "Results", "".join(figure(ctx, f, figures) for f in figures.values())))

    fcards = []
    for f in spec.get("findings", []) or []:
        st_cls = {"reproduced": "pass", "not reproduced": "fail", "refuted": "fail"}.get(f.get("status"), "skip")
        rows = []
        for key, lab in (("question", "Question"), ("read", "Read"), ("exact", "Exact words"),
                         ("example", "What we saw"), ("check", "Our check")):
            if f.get(key):
                val = f"“{inline(f[key])}”" if key == "exact" else inline(f[key])
                rows.append(f"<dt>{lab}</dt><dd>{val}</dd>")
        evid = []
        for i in f.get("nodes", []) or []:
            for c in ctx.dag.nodes[i].checks:
                ev = ctx.evidence[i].get(c.name)
                evid.append(f'<li>{outcome_badge(ev.outcome if ev else None, c.kind)} <code>{esc(i)} :: {esc(c.name)}</code>'
                            f'<span class="es">{esc(ev.summary if ev else "not run yet")}</span></li>')
        fcards.append(f'<article class="finding {st_cls}"><h3><span class="oc {st_cls}">{esc(f.get("status", ""))}</span> '
                      f'{esc(f["title"])}</h3><dl>{"".join(rows)}</dl>'
                      f'<details><summary>Evidence ({len(evid)} check{"s" if len(evid) != 1 else ""})</summary><ul class="evl">{"".join(evid)}</ul></details>'
                      f'<p class="chips">{" ".join(status_chip(ctx, i) for i in f.get("nodes", []))}</p></article>')
    parts.append(section("findings", "Findings", f'<div class="findings">{"".join(fcards)}</div>'))

    parts.append(section("strategies", "Strategies we can carry over to future papers", strategies_html(toolkit),
                         "How the verifier stays independent of whoever proposes a result, and what this reproduction taught us "
                         'about checking numerical claims; written to apply beyond this paper. The same list is on the '
                         '<a href="toolkit.html">toolkit page</a>.'))
    parts.append(section("tools", "Associated tools for verification checks", tools_html(toolkit, spec.get("tools_used")),
                         "The suite of tools a check can call on, depending on what kind of claim is being verified. "
                         "All of them are deterministic: “in the verifier” tools are implemented checks and gates; “pinned tool” "
                         "means an external tool at a fixed version that the verifier's own scripts run; “candidate” tools fit a "
                         "claim type we expect but are not wired in yet."))

    legend = '<div class="legend">' + "".join(
        f'<span><span class="sw" style="background:var(--{v})"></span>{esc(k)}</span>'
        for k, v in TRUTH_VAR.items() if any(ctx.st[i].display_truth == k for i in ctx.nodes)) + "</div>"
    parts.append(section("graph", "Where it sits in the DAG", subgraph_svg(ctx) + legend,
                         "The report's nodes and the edges between them; each opens in the theorem browser. Arrows run from what is used to what uses it."))

    heads = ["Check", "Kind", "Outcome", "Grants", "Summary", "Domain", "Ran (UTC)", "Fresh"]
    trs, ncheck, last = [], 0, None
    for i, c, ev in ctx.checks():
        if i != last:
            trs.append(f'<tr class="grp"><th colspan="{len(heads)}">{status_chip(ctx, i)} '
                       f'<span class="gt">{esc(ctx.dag.nodes[i].title)}</span></th></tr>')
            last = i
        ncheck += 1
        rec = ev.record if ev else {}
        prov = rec.get("provenance", {}) if rec else {}
        cells = [f"<code>{esc(c.name)}</code>", esc(c.kind), outcome_badge(ev.outcome if ev else None, c.kind),
                 esc(ev.grants if ev and ev.grants else "—"), esc(ev.summary if ev else "this check has not run"),
                 esc(ev.domain if ev and ev.domain else "—"), esc((prov.get("finished") or "—")[:16].replace("T", " ")),
                 ("yes" if ev.fresh else '<span class="stale-t">stale</span>') if ev else "—"]
        trs.append("<tr>" + "".join(f"<td>{x}</td>" for x in cells) + "</tr>")
    for i in ctx.nodes:
        if not ctx.dag.nodes[i].checks:
            trs.append(f'<tr class="grp"><th colspan="{len(heads)}">{status_chip(ctx, i)} '
                       f'<span class="gt">{esc(ctx.dag.nodes[i].title)} (no checks: a definition)</span></th></tr>')
    checks_tab = ('<div class="tablewrap"><table class="checks"><thead><tr>' + "".join(f"<th>{h}</th>" for h in heads)
                  + f'</tr></thead><tbody>{"".join(trs)}</tbody></table></div>')
    parts.append(section("checks", "Every check", checks_tab,
        f"All {ncheck} checks on the report's nodes, grouped by node, with their latest evidence from <code>dag/evidence/</code>. "
        "A check is fresh when its inputs (statement, code, results files, parents) are unchanged since it ran."))

    opens = spec.get("open", []) or []
    parts.append(section("open", "Open items", "<ul class=\"open\">" + "".join(f"<li>{inline(o)}</li>" for o in opens) + "</ul>"))

    commit = (meta.get("commit") or "")[:7]
    foot = (f'<footer><p>Generated {esc(meta["generated"])}' + (f' from commit <code>{esc(commit)}</code>' if commit else "")
            + f' by <code>dagtool report</code>. Narrative: <a href="{esc(ctx.blob("dag/reports/" + spec["id"] + ".yaml"))}">'
            f'dag/reports/{esc(spec["id"])}.yaml</a>; numbers, outcomes and statuses come from the DAG and the committed results.</p></footer>')

    title = spec.get("short_title") or spec["title"].split(":")[0]
    return PAGE.format(title=esc(title), fonts=fonts, tokens=tokens, css=CSS, head=head, nav=nav,
                       body="".join(parts), foot=foot, desc=esc(spec.get("summary", "")[:300]))


def render_index(dag: Dag, specs, st) -> str:
    fonts, tokens = tokens_css()
    cards = []
    for _, spec in specs:
        ctx = Context(dag, spec, st)
        paper = spec.get("paper", {}) or {}
        cards.append(f'<a class="rcard" href="{esc(spec["id"])}.html"><h2>{esc(spec["title"])}</h2>'
                     f'<p class="paper">{esc(paper.get("citation", ""))}</p>{tiles(ctx)}'
                     + (f'<p class="headline">{inline(spec["headline"])}</p>' if spec.get("headline") else "") + "</a>")
    head = ('<header class="hero"><p class="eyebrow"><a href="../index.html">Theorem DAG</a></p><h1>Verification reports</h1>'
            '<p class="summary">One page per paper the verifier has checked: what was checked, how, and what came out. '
            'Statuses and outcomes are read from the DAG when the page is generated.</p></header>')
    body = (f'<div class="rcards">{"".join(cards) or "<p>No reports yet.</p>"}</div>'
            '<a class="rcard" href="toolkit.html"><h2>Toolkit: strategies and verification tools</h2>'
            '<p class="summary">Strategies that carry over between papers, and the tools a check can use depending on the '
            'kind of claim.</p></a>')
    return PAGE.format(title="Verification reports", fonts=fonts, tokens=tokens, css=CSS, head=head, nav="",
                       body=body, foot=f'<footer><p>Generated {esc(now_utc())} by <code>dagtool report</code>.</p></footer>',
                       desc="Verification reports for papers checked by the MBQC theorem DAG")


def render_toolkit(dag: Dag) -> str:
    fonts, tokens = tokens_css()
    toolkit = load_toolkit(dag.root)
    head = ('<header class="hero"><p class="eyebrow"><a href="index.html">All reports</a> · <a href="../index.html">theorem DAG</a></p>'
            '<h1>Verification toolkit</h1><p class="summary">The verifier is a fixed set of deterministic checks and pinned tools. '
            'Proposers submit artifacts from outside it and receive its feedback; they cannot change the checks. This page lists '
            'the strategies that keep it that way and carry over between papers, and the tools a check can use depending on the '
            'claim.</p></header>')
    nav = '<nav class="toc" aria-label="Sections"><a href="#strategies">Strategies</a><a href="#tools">Tools</a></nav>'
    body = (section("strategies", "Strategies we can carry over to future papers", strategies_html(toolkit))
            + section("tools", "Associated tools for verification checks", tools_html(toolkit)))
    return PAGE.format(title="Verification toolkit", fonts=fonts, tokens=tokens, css=CSS, head=head, nav=nav, body=body,
                       foot=f'<footer><p>Generated {esc(now_utc())} by <code>dagtool report</code> from '
                            f'<code>dag/reports/{TOOLKIT_FILE}</code>.</p></footer>',
                       desc="Strategies and tools for verifying claims from papers")


def write_reports(dag: Dag, out: Path, only: list[str] | None = None) -> list[Path]:
    specs = report_specs(dag.root)
    if only:
        specs = [(p, s) for p, s in specs if s["id"] in only]
    st = compute(dag)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for _, spec in specs:
        path = out / f"{spec['id']}.html"
        path.write_text(render_report(dag, spec, st), encoding="utf-8")
        written.append(path)
    idx = out / "index.html"
    idx.write_text(render_index(dag, report_specs(dag.root), st), encoding="utf-8")
    written.append(idx)
    tk = out / "toolkit.html"
    tk.write_text(render_toolkit(dag), encoding="utf-8")
    written.append(tk)
    return written


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
{fonts}
<style>
{tokens}
{css}
</style>
</head>
<body>
<div class="page">
{head}
{nav}
<main>
{body}
</main>
{foot}
</div>
</body>
</html>
"""

CSS = """
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 400 var(--s-3)/1.55 var(--f-ui); }
a { color: var(--accent); text-underline-offset: 2px; }
code { font-family: var(--f-mono); font-size: 0.88em; background: var(--sunk); padding: 1px 4px; border-radius: 4px; overflow-wrap: anywhere; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.muted { color: var(--ink-2); }
.page { max-width: 1120px; margin: 0 auto; padding: 0 16px 48px; }
.hero { padding: 28px 0 18px; border-bottom: 1px solid var(--line); }
.eyebrow { margin: 0 0 6px; font-size: var(--s-1); text-transform: uppercase; letter-spacing: 0.07em; color: var(--ink-3); }
.eyebrow a { color: inherit; }
h1 { margin: 0; font: 600 clamp(22px, 3.4vw, 30px)/1.2 var(--f-ui); letter-spacing: -0.015em; text-wrap: balance; }
h2 { margin: 0 0 6px; font: 600 var(--s-5)/1.25 var(--f-ui); letter-spacing: -0.01em; }
h3 { margin: 0 0 4px; font: 600 var(--s-4)/1.3 var(--f-ui); }
h4 { margin: 0 0 6px; font: 600 var(--s-2)/1.3 var(--f-ui); color: var(--ink-2); }
.paper { margin: 8px 0 0; color: var(--ink-2); font-family: var(--f-math); font-size: 16px; }
.paper a { color: inherit; }
.kind { margin: 10px 0 0; }
.pill { display: inline-block; border: 1px solid var(--line); border-radius: 999px; padding: 1px 10px; font-size: var(--s-1); color: var(--ink-2); background: var(--panel); }
.summary { max-width: 78ch; margin: 14px 0 0; color: var(--ink-2); }
.headline { max-width: 78ch; margin: 12px 0 0; padding: 10px 14px; background: var(--panel); border: 1px solid var(--line); border-left: 3px solid var(--accent); border-radius: 6px; }
.links { margin: 14px 0 0; font-size: var(--s-2); }
.tiles { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
.tile { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 8px 14px; min-width: 96px; }
.tile .tn { font: 600 22px/1.1 var(--f-ui); font-variant-numeric: tabular-nums; }
.tile .tl { font-size: var(--s-1); color: var(--ink-2); }
.tile.pass { border-top: 3px solid var(--t-proved); } .tile.fail { border-top: 3px solid var(--t-refuted); }
.tile.skip { border-top: 3px solid var(--t-conjecture); } .tile.error { border-top: 3px solid var(--warn); }
.toc { position: sticky; top: 0; z-index: 5; display: flex; gap: 2px 4px; overflow-x: auto; padding: 8px 0; background: var(--bg); border-bottom: 1px solid var(--line); }
.toc a { flex: none; padding: 4px 10px; border-radius: 6px; color: var(--ink-2); text-decoration: none; font-size: var(--s-2); font-weight: 500; }
.toc a:hover { background: var(--panel); color: var(--ink); }
section { padding: 30px 0 6px; scroll-margin-top: 48px; }
.lead { max-width: 78ch; margin: 0 0 14px; color: var(--ink-2); }
dl.scope { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 6px 18px; margin: 10px 0 0; max-width: 90ch; }
dl.scope dt { font-weight: 600; } dl.scope dd { margin: 0; color: var(--ink-2); }
.flow { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; counter-reset: s; }
.flow li { position: relative; }
.flow li:not(:last-child)::after { content: "→"; position: absolute; right: -9px; top: 14px; color: var(--ink-3); font-weight: 600; }
.stage { height: 100%; display: grid; gap: 6px; align-content: start; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; }
.stage span { font-size: var(--s-2); color: var(--ink-2); }
.stage .by { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 2px; }
.step-ref { display: inline-grid; place-items: center; min-width: 22px; height: 22px; padding: 0 5px; border-radius: 999px; background: var(--accent-soft); color: var(--ink); font-size: var(--s-1); font-weight: 600; text-decoration: none; }
.steps { list-style: none; margin: 8px 0 0; padding: 0; display: grid; gap: 12px; }
.step { display: grid; grid-template-columns: 36px minmax(0, 1fr); gap: 12px; background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; scroll-margin-top: 56px; }
.sn { width: 32px; height: 32px; border-radius: 999px; display: grid; place-items: center; background: var(--accent); color: var(--panel); font-weight: 600; }
.sb { min-width: 0; }
.sb p { margin: 2px 0 8px; max-width: 86ch; }
.obs { background: var(--sunk); border-radius: 6px; padding: 8px 12px; margin: 6px 0 10px; }
.obs ul { margin: 0; padding-left: 18px; font-size: var(--s-2); color: var(--ink-2); }
dl.sm { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 6px 12px; margin: 6px 0 0; font-size: var(--s-2); }
dl.sm dt { color: var(--ink-3); font-weight: 600; } dl.sm dd { margin: 0; display: flex; flex-wrap: wrap; gap: 6px; min-width: 0; }
.file { font-family: var(--f-mono); font-size: 12px; padding: 1px 6px; border: 1px solid var(--line); border-radius: 5px; text-decoration: none; background: var(--bg); }
.file.missing { color: var(--ink-3); border-style: dashed; }
.chip-node { display: inline-flex; align-items: center; gap: 6px; min-width: 0; padding: 2px 8px; border: 1px solid var(--line); border-radius: 999px; text-decoration: none; color: var(--ink); background: var(--bg); font-size: 12px; max-width: 100%; }
.chip-node .nid { font-family: var(--f-mono); font-size: 11.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chip-node .st { color: var(--ink-2); white-space: nowrap; }
.sw { display: inline-block; width: 9px; height: 9px; border-radius: 2px; flex: none; }
.tablewrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); }
table { border-collapse: collapse; width: 100%; font-size: var(--s-2); }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
tbody tr:last-child td, tbody tr:last-child th { border-bottom: 0; }
thead th { font-size: var(--s-1); font-weight: 600; color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.05em; white-space: nowrap; }
.badge { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: var(--s-1); border: 1px solid var(--line); white-space: nowrap; }
.badge.stated { color: var(--t-proved); border-color: currentColor; }
.badge.ambiguous { color: var(--warn); border-color: currentColor; }
.badge.not-stated { color: var(--t-refuted); border-color: currentColor; }
.fig { margin: 14px 0 26px; }
.fig figcaption { margin-bottom: 10px; }
.cap { margin: 2px 0 0; color: var(--ink-2); max-width: 86ch; font-size: var(--s-2); }
.fnote { margin: 6px 0 0; font-size: var(--s-1); color: var(--ink-3); }
table.matrix th[scope=row] { font-weight: 500; white-space: nowrap; position: sticky; left: 0; z-index: 1; background: var(--panel); }
table.matrix thead th { text-align: center; } table.matrix thead th:first-child { text-align: left; }
td.cell { text-align: center; min-width: 116px; font-variant-numeric: tabular-nums; border-left: 1px solid var(--line); }
td.cell .mk { display: block; font-weight: 700; font-size: 15px; line-height: 1; }
td.cell .v { display: block; font-weight: 600; margin-top: 4px; }
td.cell .vs { display: block; font-size: var(--s-1); color: var(--ink-2); }
td.cell .r { display: block; font-size: var(--s-1); color: var(--ink-3); }
td.cell.pass .mk { color: var(--t-proved); } td.cell.fail .mk { color: var(--t-refuted); } td.cell.skip .mk { color: var(--ink-3); }
td.cell.pass { background: color-mix(in srgb, var(--t-proved) 9%, transparent); }
td.cell.fail { background: color-mix(in srgb, var(--t-refuted) 8%, transparent); }
td.cell.skip { background: repeating-linear-gradient(135deg, transparent 0 6px, var(--sunk) 6px 8px); }
td.cell.stale { outline: 1px dashed var(--warn); outline-offset: -3px; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; margin: 10px 0 0; font-size: var(--s-1); color: var(--ink-2); align-items: center; }
.legend > span { display: inline-flex; align-items: center; gap: 6px; }
.oc { display: inline-flex; align-items: center; gap: 4px; font-size: var(--s-1); font-weight: 600; white-space: nowrap; padding: 1px 8px; border-radius: 999px; border: 1px solid currentColor; }
.oc.pass { color: var(--t-proved); } .oc.fail { color: var(--t-refuted); } .oc.skip { color: var(--ink-3); } .oc.error { color: var(--warn); }
.strip { margin-top: 10px; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px 4px; }
.srow { display: grid; grid-template-columns: minmax(120px, 210px) 1fr; gap: 12px; align-items: center; min-height: 30px; }
.slab { font-size: var(--s-2); color: var(--ink-2); }
.track { position: relative; height: 30px; }
.gl { position: absolute; top: 0; bottom: 0; width: 1px; background: var(--line); }
.gl.one { background: var(--ink-3); }
.band { position: absolute; top: 4px; bottom: 4px; background: color-mix(in srgb, var(--t-proved) 22%, transparent); border-radius: 2px; min-width: 3px; transform: translateX(-1px); }
.bandkey { display: inline-block; width: 12px; height: 12px; border-radius: 2px; background: color-mix(in srgb, var(--t-proved) 22%, transparent); }
.pt { position: absolute; top: 50%; width: 11px; height: 11px; margin: -5.5px 0 0 -5.5px; background: var(--c); box-shadow: 0 0 0 2px var(--panel); }
.pt.static { position: static; display: inline-block; margin: 0; }
.pt.circle { border-radius: 50%; } .pt.square { border-radius: 2px; }
.pt.diamond { transform: rotate(45deg) scale(0.9); border-radius: 1px; }
.pt.triangle { clip-path: polygon(50% 0, 100% 100%, 0 100%); box-shadow: none; }
.srow.axis .track { height: 22px; }
.tk { position: absolute; top: 2px; transform: translateX(-50%); font-size: var(--s-1); color: var(--ink-3); font-variant-numeric: tabular-nums; }
.bgrid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 330px), 1fr)); gap: 12px; }
.bgroup { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px; }
.bgroup h4 { display: flex; flex-wrap: wrap; gap: 6px; justify-content: space-between; align-items: baseline; color: var(--ink); }
.bgroup .src .file { font-size: 11px; }
.brow { display: grid; grid-template-columns: minmax(90px, 40%) 1fr 76px; gap: 8px; align-items: center; min-height: 26px; }
.blab { font-size: var(--s-1); color: var(--ink-2); line-height: 1.25; }
.btrack { position: relative; height: 14px; background: var(--sunk); border-radius: 0 4px 4px 0; }
.bar { position: absolute; left: 0; top: 0; bottom: 0; background: var(--accent); border-radius: 0 4px 4px 0; min-width: 2px; }
.bar.ok { background: var(--t-proved); } .bar.bad { background: var(--t-refuted); }
.ref { position: absolute; top: -3px; bottom: -3px; width: 2px; margin-left: -1px; background: var(--ink); opacity: 0.6; }
.bval { font-size: var(--s-1); font-variant-numeric: tabular-nums; color: var(--ink); white-space: nowrap; text-align: right; }
.bval.err { color: var(--warn); }
details.tv { margin-top: 8px; font-size: var(--s-2); }
details.tv summary { cursor: pointer; color: var(--ink-2); font-size: var(--s-1); }
details.tv .tablewrap { margin-top: 6px; }
.findings { display: grid; gap: 12px; }
.finding { min-width: 0; background: var(--panel); border: 1px solid var(--line); border-left: 4px solid var(--t-conjecture); border-radius: 8px; padding: 14px 16px; }
.finding.pass { border-left-color: var(--t-proved); } .finding.fail { border-left-color: var(--t-refuted); }
.finding h3 { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.finding dl { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 4px 14px; margin: 8px 0; font-size: var(--s-2); }
.finding dt { color: var(--ink-3); font-weight: 600; } .finding dd { margin: 0; max-width: 86ch; }
.finding details summary { cursor: pointer; font-size: var(--s-1); color: var(--ink-2); }
.evl { list-style: none; padding: 0; margin: 8px 0 0; display: grid; gap: 6px; font-size: var(--s-1); }
.evl li { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 2px 8px; align-items: start; }
.evl .es { grid-column: 2; color: var(--ink-2); }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 0; min-width: 0; }
.graphwrap { overflow-x: auto; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 8px; }
svg.sub { display: block; max-width: none; }
svg.sub .n rect { fill: var(--bg); stroke: var(--line); }
svg.sub a:hover .n rect:first-of-type, svg.sub a:focus .n rect:first-of-type { stroke: var(--accent); stroke-width: 2; }
svg.sub text { fill: var(--ink); font: 500 12px var(--f-ui); }
svg.sub text.sub { fill: var(--ink-2); font: 400 11px var(--f-ui); }
svg.sub .e { fill: none; stroke: var(--ink-3); stroke-width: 1.3; opacity: 0.8; }
svg.sub .e.assumes { stroke: var(--t-assumed); stroke-dasharray: 5 3; }
svg.sub .ah { fill: var(--ink-3); }
table.checks td:nth-child(1) code { white-space: nowrap; overflow-wrap: normal; }
table.checks td:nth-child(5) { min-width: 300px; max-width: 460px; overflow-wrap: anywhere; }
table.checks td:nth-child(6) { min-width: 220px; max-width: 320px; color: var(--ink-2); }
table.checks td:nth-child(7) { white-space: nowrap; color: var(--ink-2); }
table.checks tr.grp th { background: var(--sunk); text-transform: none; letter-spacing: 0; font-size: var(--s-2); color: var(--ink); font-weight: 500; }
table.checks tr.grp .gt { margin-left: 6px; color: var(--ink-2); }
.stale-t { color: var(--warn); font-weight: 600; }
.badge.calibrated { color: var(--accent); border-color: currentColor; }
.bgroup + .tv, .bgroup + details { margin-top: 8px; }
.brow.rank .blab { font-size: 12px; }
.scgrid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 420px), 1fr)); gap: 12px; margin-top: 8px; }
.pan { margin: 0; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px 6px; }
.pan figcaption { font-weight: 600; font-size: var(--s-2); margin-bottom: 4px; }
svg.sc { display: block; width: 100%; height: auto; overflow: visible; }
svg.sc .g { stroke: var(--line); stroke-width: 1; }
svg.sc .ax { stroke: var(--ink-3); stroke-width: 1; }
svg.sc text { fill: var(--ink-2); font: 400 10.5px var(--f-ui); font-variant-numeric: tabular-nums; }
svg.sc .yt { text-anchor: end; } svg.sc .xt, svg.sc .xl { text-anchor: middle; } svg.sc .xl { fill: var(--ink-3); }
svg.sc .ol { fill: none; stroke: var(--accent); stroke-width: 2; stroke-linejoin: round; }
svg .o { fill: var(--accent); stroke: var(--panel); stroke-width: 2; }
svg .p { fill: var(--panel); stroke: var(--ink); stroke-width: 1.6; }
h3.sub { margin: 22px 0 8px; }
table.applic td:first-child { min-width: 220px; } table.applic td:nth-child(2) { min-width: 200px; }
.tchip { display: inline-block; margin: 2px 2px 2px 0; padding: 1px 8px; border-radius: 999px; font-size: 12px; text-decoration: none;
  border: 1px solid var(--line); color: var(--ink); background: var(--bg); white-space: nowrap; }
.tchip.st-verifier { border-color: var(--t-proved); } .tchip.st-used { border-color: var(--accent); }
.tchip.st-candidate { border-style: dashed; color: var(--ink-2); }
.tools { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr)); gap: 12px; }
.tool { min-width: 0; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px; scroll-margin-top: 56px; }
.tool.candidate { border-style: dashed; }
dl.sd { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 4px 12px; margin: 6px 0 0; font-size: var(--s-2); }
dl.sd dt { color: var(--ink-3); font-weight: 600; } dl.sd dd { margin: 0; max-width: 90ch; }
.tool h3 { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; font-size: var(--s-3); }
.tool .cat { margin: 0 0 6px; font-size: var(--s-1); color: var(--ink-3); text-transform: uppercase; letter-spacing: 0.05em; }
.tool dl { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 4px 10px; margin: 0; font-size: var(--s-2); }
.tool dt { color: var(--ink-3); font-weight: 600; } .tool dd { margin: 0; }
.badge.st-verifier { color: var(--t-proved); border-color: currentColor; }
.badge.st-used { color: var(--accent); border-color: currentColor; }
.badge.st-candidate { color: var(--ink-3); border-style: dashed; }
.badge.here { background: var(--accent-soft); color: var(--ink); }
.principle { max-width: 86ch; margin: 4px 0 6px; padding: 12px 16px; background: var(--panel); border: 1px solid var(--line);
  border-left: 3px solid var(--t-proved); border-radius: 6px; }
ul.open { margin: 4px 0 0; padding-left: 20px; max-width: 86ch; } ul.open li { margin: 4px 0; }
footer { margin-top: 36px; padding-top: 14px; border-top: 1px solid var(--line); font-size: var(--s-1); color: var(--ink-3); }
.rcards { display: grid; gap: 14px; padding-top: 22px; }
.rcard { display: block; background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 16px 18px; color: inherit; text-decoration: none; }
.rcard:hover { border-color: var(--accent); }
@media (max-width: 640px) {
  .step { grid-template-columns: minmax(0, 1fr); } .sn { width: 28px; height: 28px; }
  dl.scope, dl.sm, dl.sd, .finding dl, .tool dl { grid-template-columns: minmax(0, 1fr); gap: 2px; }
  .tchip { white-space: normal; }
  svg.sc text { font-size: 15px; }
  .chip-node .st { white-space: normal; } dl.scope dd, .finding dd { margin-bottom: 8px; }
  .srow { grid-template-columns: 1fr; gap: 0; } .srow.axis .slab { display: none; }
  .brow { grid-template-columns: 1fr 76px; } .brow .blab { grid-column: 1 / -1; }
  .flow li:not(:last-child)::after { content: "↓"; right: auto; left: 14px; top: auto; bottom: -15px; }
}
@media (forced-colors: active) { .bar, .pt, .sw { forced-color-adjust: none; } }
@media print { .toc { position: static; } details { display: block; } }
"""
