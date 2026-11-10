"""Per-paper verification reports: narrative from dag/reports/*.yaml, numbers and outcomes from the live DAG."""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest
import yaml

from dagtool.model import load_dag
from dagtool.render import _slug
from dagtool.report import ReportError, inline, load_toolkit, render_report, render_toolkit, report_specs, write_reports
from dagtool.status import compute

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def dag():
    return load_dag(REPO)


@pytest.fixture(scope="module")
def spec():
    return yaml.safe_load((REPO / "dag" / "reports" / "saadatmand2024.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def page(dag, spec):
    return render_report(dag, spec, compute(dag))


def test_specs_are_found_and_toolkit_is_not_a_report(dag):
    ids = [s["id"] for _, s in report_specs(REPO)]
    assert "saadatmand2024" in ids and "toolkit" not in ids


def test_every_check_of_every_report_node_is_listed(dag, page):
    nodes = [i for i, n in dag.nodes.items() if "reproductions/saadatmand2024" in n.path.as_posix()]
    assert len(nodes) >= 10
    for i in nodes:
        assert f"#{_slug(i)}" in page, i
        for c in dag.nodes[i].checks:
            assert f"<code>{c.name}</code>" in page, (i, c.name)
    assert "def.fermi_hubbard_square" in page          # referenced from the narrative, outside the folder


def test_sections_and_no_scripts(page):
    for sid in ("scope", "pipeline", "approach", "configuration", "results", "findings", "strategies", "tools", "graph",
                "checks", "open"):
        assert f'id="{sid}"' in page
    assert "<script" not in page.lower()
    assert "@media (prefers-color-scheme: dark)" in page   # tokens copied from the browser


def test_matrix_has_one_cell_per_quantity_and_lattice(spec, page):
    fig = next(f for f in spec["figures"] if f["type"] == "check_matrix")
    m = re.search(r'<table class="matrix">.*?</table>', page, flags=re.S).group(0)
    assert m.count('<td class="cell') == len(fig["rows"]) * len(fig["columns"])
    assert 'class="cell skip' in m                           # 8x8 and larger are not run
    assert 'class="cell pass' in m and 'class="cell fail' in m


def test_every_step_is_numbered_and_linked_from_the_pipeline(spec, page):
    for s in spec["steps"]:
        assert f'id="step-{s["id"]}"' in page
    for stage in spec["pipeline"]:
        for ref in stage["checked_by"]:
            assert f"#step-{ref}" in page


def test_unknown_node_is_an_error(dag, spec):
    bad = copy.deepcopy(spec)
    bad["findings"][0]["nodes"] = ["no.such.node"]
    with pytest.raises(ReportError, match="no.such.node"):
        render_report(dag, bad)


def test_missing_results_file_renders_as_not_yet(dag, spec):
    s = copy.deepcopy(spec)
    s["figures"] = [{"type": "bars", "id": "x", "title": "x", "groups": [
        {"label": "later", "file": "experiments/rre/results/fh_8x8_not_there.json", "items": [{"label": "a", "path": "rre.N"}]}]}]
    assert "No results yet" in render_report(dag, s)


def test_inline_markup_escapes_html():
    assert inline("<b>x</b> `y` **z** [a](https://e.org)") == (
        '&lt;b&gt;x&lt;/b&gt; <code>y</code> <b>z</b> <a href="https://e.org">a</a>')


def test_write_reports_writes_pages_and_index(dag, tmp_path):
    written = write_reports(dag, tmp_path)
    names = {p.name for p in written}
    assert {"saadatmand2024.html", "index.html"} <= names
    assert 'href="saadatmand2024.html"' in (tmp_path / "index.html").read_text(encoding="utf-8")


def test_toolkit_is_consistent(spec):
    tk = load_toolkit(REPO)
    ids = {tl["id"] for tl in tk["tools"]}
    assert len(ids) == len(tk["tools"])
    assert set(spec["tools_used"]) <= ids
    for m in tk["applicability"]:
        assert set(m["tools"]) <= ids, m["claim"]
    from checks._kinds import CHECK_KINDS
    for tl in tk["tools"]:
        assert tl["status"] in ("verifier", "used", "candidate")
        assert set(tl.get("check_kinds", [])) <= set(CHECK_KINDS), tl["id"]
        if tl["status"] == "verifier" and tl.get("category") != "Repository controls":
            assert tl.get("check_kinds"), tl["id"]      # a verifier tool backs an implemented check kind
    from checks._framework import discover
    implemented = {t.type for t in discover().values()}
    for tl in tk["tools"]:
        if tl["status"] == "verifier":                  # and every kind it names is implemented, not only declared
            assert set(tl.get("check_kinds", [])) <= implemented, (tl["id"], set(tl["check_kinds"]) - implemented)


def test_toolkit_page_and_report_sections(dag, page):
    tk = load_toolkit(REPO)
    html = render_toolkit(dag)
    for s in tk["strategies"]:
        assert s["title"].replace("'", "&#x27;") in html
    for tl in tk["tools"]:
        assert f'id="tool-{tl["id"]}"' in html and f'id="tool-{tl["id"]}"' in page
    assert page.count("used for this paper") >= len(yaml.safe_load(
        (REPO / "dag" / "reports" / "saadatmand2024.yaml").read_text(encoding="utf-8"))["tools_used"])


def test_scaling_figures_plot_only_runs(spec, page):
    import json
    for fig in (f for f in spec["figures"] if f["type"] == "scaling"):
        pts = json.loads((REPO / fig["file"]).read_text(encoding="utf-8"))["series"][fig["series"]]["points"]
        block = re.search(rf'<figure class="fig" id="fig-{fig["id"]}">.*?</figure>\s*(?=<figure class="fig"|</section>)',
                          page, flags=re.S).group(0)
        assert block.count('<circle class="o"') == len(pts) * len(fig["panels"])      # one dot per run, per panel
        printed = sum(1 for p in pts if p.get("paper")) * sum(1 for pan in fig["panels"] if pan.get("paper"))
        assert block.count('<rect class="p"') == printed                               # paper only where printed


def test_calibration_ranking_shows_the_unique_best_point(page):
    block = re.search(r'id="fig-calibration".*?</figure>', page, flags=re.S).group(0)
    assert "26/27" in block and "<b>budget 0.05" in block


def test_strategies_are_grouped_and_the_principle_is_shown(dag):
    tk = load_toolkit(REPO)
    assert tk["principle"] and set(tk["groups"]) >= {s["group"] for s in tk["strategies"]}
    html = render_toolkit(dag)
    assert 'class="principle"' in html
    for title in tk["groups"].values():
        assert title in html
    # the list is numbered continuously across groups
    assert f'<div class="sn">{len(tk["strategies"])}</div>' in html


def test_inline_markup_leaves_code_spans_alone():
    assert inline("`experiments/*/paper_*.yaml` and *x*") == "<code>experiments/*/paper_*.yaml</code> and <i>x</i>"
