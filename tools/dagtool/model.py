"""
model.py — loading and validating the theorem DAG.

Sources of truth (all hand-written, all committed):
    dag/nodes/**/<id>.yaml     one node per file
    dag/reviews/<id>.yaml      human statement-review records
Checks write dag/evidence/<id>/<check>.json; this module only reads those.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from mbqc_verify.conventions import CONVERTERS, Conventions

KINDS = ("definition", "core", "assumption", "transfer", "lemma", "theorem")
EDGE_KINDS = ("uses", "assumes", "instantiates", "variant_of")
PROPAGATING_EDGES = ("uses", "assumes", "instantiates")   # variant_of carries no trust

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Edge:
    src: str            # the node that is used (parent)
    dst: str            # the node that uses it (child)
    kind: str
    convert: tuple[str, ...] = ()
    declared: bool = True   # False = extracted from a Lean proof


@dataclass
class CheckSpec:
    kind: str
    params: dict = field(default_factory=dict)
    name: str = ""       # evidence file stem; defaults to kind (kind-2, kind-3 when repeated)


@dataclass
class Node:
    id: str
    kind: str
    title: str
    statement: str
    path: Path
    area: str = ""
    layer: str | None = None
    statement_tex: str | None = None
    description: str = ""
    lean_decl: str | None = None          # the main declaration (first entry)
    lean_names: list[str] = field(default_factory=list)   # all names / namespaces of this node
    code: list[str] = field(default_factory=list)
    conventions: Conventions = field(default_factory=Conventions)
    depends_on: list[dict] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    checks: list[CheckSpec] = field(default_factory=list)
    source: dict | None = None
    tags: list[str] = field(default_factory=list)
    acknowledged: dict[str, str] = field(default_factory=dict)   # flag code -> reason
    notes: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def needs_human_review(self) -> bool:
        return self.kind in ("definition", "core", "assumption", "transfer")


class DagError(ValueError):
    pass


def _schema() -> dict:
    return json.loads((REPO_ROOT / "dag" / "schema" / "node.schema.json").read_text(encoding="utf-8"))


def load_node(path: Path, schema: dict | None = None) -> Node:
    import jsonschema

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if schema is not None:
        try:
            jsonschema.validate(raw, schema)
        except jsonschema.ValidationError as e:
            loc = "/".join(str(p) for p in e.absolute_path) or "(root)"
            raise DagError(f"{path}: {loc}: {e.message}") from None
    if path.stem != raw["id"]:
        raise DagError(f"{path}: file name must equal the node id ({raw['id']}.yaml)")
    specs, seen = [], {}
    for c in raw.get("checks", []):
        seen[c["kind"]] = seen.get(c["kind"], 0) + 1
        name = c.get("name") or (c["kind"] if seen[c["kind"]] == 1 else f"{c['kind']}-{seen[c['kind']]}")
        specs.append(CheckSpec(kind=c["kind"], params=c.get("params", {}), name=name))
    nodes_dir = path.parents[0]
    while nodes_dir.name != "nodes" and nodes_dir != nodes_dir.parent:
        nodes_dir = nodes_dir.parent
    area = path.parent.relative_to(nodes_dir).as_posix() if nodes_dir.name == "nodes" else ""
    try:
        conv = Conventions.parse(raw.get("conventions"))
    except ValueError as e:
        raise DagError(f"{path}: {e}") from None
    return Node(
        id=raw["id"], kind=raw["kind"], title=raw["title"], statement=raw["statement"], path=path,
        area=area, layer=raw.get("layer"), statement_tex=raw.get("statement_tex"),
        description=raw.get("description", ""), lean_decl=_lean_names(raw)[0] if _lean_names(raw) else None,
        lean_names=_lean_names(raw),
        code=list(raw.get("code", [])), conventions=conv,
        depends_on=list(raw.get("depends_on", [])), assumptions=list(raw.get("assumptions", [])),
        checks=specs, source=raw.get("source"), tags=list(raw.get("tags", [])),
        acknowledged={a["code"]: a["reason"] for a in raw.get("acknowledged", [])},
        notes=raw.get("notes", ""), raw=raw,
    )


def _lean_names(raw: dict) -> list[str]:
    v = raw.get("lean_decl")
    return [] if v is None else [v] if isinstance(v, str) else list(v)


@dataclass
class Dag:
    root: Path
    nodes: dict[str, Node]
    edges: list[Edge]

    # ---- structure -------------------------------------------------------
    def parents(self, node_id: str, kinds=PROPAGATING_EDGES) -> list[Edge]:
        return [e for e in self.edges if e.dst == node_id and e.kind in kinds]

    def children(self, node_id: str, kinds=PROPAGATING_EDGES) -> list[Edge]:
        return [e for e in self.edges if e.src == node_id and e.kind in kinds]

    def ancestors(self, node_id: str) -> set[str]:
        out, stack = set(), [node_id]
        while stack:
            for e in self.parents(stack.pop()):
                if e.src not in out:
                    out.add(e.src)
                    stack.append(e.src)
        return out

    def descendants(self, node_id: str) -> set[str]:
        out, stack = set(), [node_id]
        while stack:
            for e in self.children(stack.pop()):
                if e.dst not in out:
                    out.add(e.dst)
                    stack.append(e.dst)
        return out

    def topo_order(self) -> list[str]:
        """Parents before children (propagating edges only). Raises on a cycle."""
        indeg = {i: 0 for i in self.nodes}
        for e in self.edges:
            if e.kind in PROPAGATING_EDGES:
                indeg[e.dst] += 1
        ready = sorted(i for i, d in indeg.items() if d == 0)
        order = []
        while ready:
            i = ready.pop(0)
            order.append(i)
            for e in self.children(i):
                indeg[e.dst] -= 1
                if indeg[e.dst] == 0:
                    ready.append(e.dst)
            ready.sort()
        if len(order) != len(self.nodes):
            stuck = sorted(set(self.nodes) - set(order))
            raise DagError(f"cycle among: {stuck}")
        return order

    # ---- paths -----------------------------------------------------------
    @property
    def evidence_dir(self) -> Path:
        return self.root / "dag" / "evidence"

    @property
    def reviews_dir(self) -> Path:
        return self.root / "dag" / "reviews"


def load_dag(root: Path | None = None, validate_schema: bool = True) -> Dag:
    """Load every node, build declared edges, and check the graph is well formed."""
    root = Path(root or REPO_ROOT)
    schema = _schema() if validate_schema else None
    nodes: dict[str, Node] = {}
    for path in sorted((root / "dag" / "nodes").rglob("*.yaml")):
        node = load_node(path, schema)
        if node.id in nodes:
            raise DagError(f"duplicate id {node.id}: {nodes[node.id].path} and {path}")
        nodes[node.id] = node

    edges: list[Edge] = []
    problems: list[str] = []
    for node in nodes.values():
        for dep in node.depends_on:
            if dep["node"] not in nodes:
                problems.append(f"{node.id}: depends_on unknown node {dep['node']!r}")
                continue
            bad = [c for c in dep.get("convert", []) if c not in CONVERTERS]
            if bad:
                problems.append(f"{node.id}: unknown converter(s) {bad} on edge from {dep['node']}")
            edges.append(Edge(src=dep["node"], dst=node.id, kind=dep.get("kind", "uses"),
                              convert=tuple(dep.get("convert", []))))
        for a in node.assumptions:
            if a not in nodes:
                problems.append(f"{node.id}: assumption {a!r} is not a node")
            elif a not in {d["node"] for d in node.depends_on} and a not in _all_ancestor_ids(nodes, node.id):
                problems.append(f"{node.id}: assumption {a!r} is not an ancestor; add a depends_on edge")
    if problems:
        raise DagError("\n".join(problems))
    dag = Dag(root=root, nodes=nodes, edges=edges)
    dag.topo_order()   # raises on cycles
    return dag


def _all_ancestor_ids(nodes: dict[str, Node], node_id: str) -> set[str]:
    out, stack = set(), [node_id]
    while stack:
        for dep in nodes[stack.pop()].depends_on:
            if dep["node"] in nodes and dep["node"] not in out and dep.get("kind", "uses") in PROPAGATING_EDGES:
                out.add(dep["node"])
                stack.append(dep["node"])
    return out
