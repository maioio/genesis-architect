"""
Knowledge Graph Engine for Genesis Architect (Pro).

The other engines produce islands of knowledge: a CVE here, a Reddit pain point
there, a decision, a god class. The Knowledge Graph links them into one queryable
graph so Genesis can answer connective questions:

  - "Which do-not-touch zones have an open CVE?"
  - "Which decisions does new drift contradict?"
  - "Did a community warning predict this drift?"

Design (planning doc engines/05): a directed, attributed graph.

  KnowledgeGraph
    nodes: { id -> { type, label, metadata } }
    edges: [ { src, rel, dst, evidence_ref?, confidence } ]

Principles:
  - Additive & deterministic: each engine appends its nodes/edges; the graph is
    the union. Adding the same node/edge twice is idempotent (last metadata wins
    for nodes; identical edges de-duplicate).
  - Honesty clause: every edge carries a `confidence` in [0,1]. A link with no
    basis is low-confidence, and an optional `evidence_ref` points at the source.
  - Pro-only (Constitution 11). Free does not build the knowledge graph.

Persistence: `.genesis/knowledge/graph.json`.
This module is pure data + graph algorithms (stdlib only). `build_from_project`
assembles nodes/edges from whatever engine outputs are present, degrading
gracefully when an engine produced nothing (never fabricates links).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Recognized node types (mirrors the planning doc). Free-form types are allowed
# but these are the ones the build pipeline produces.
NODE_TYPES = (
    "module", "symbol", "responsibility", "decision", "evidence",
    "issue", "pr", "commit", "cve", "package", "field_finding",
    "risk", "test", "anti_pattern", "drift", "pattern", "library",
)

# Recognized relationship types.
REL_TYPES = (
    "implements", "affects", "supports", "used_by", "reported",
    "touched", "warns_about", "located_in", "covers", "detected_in",
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Node:
    id: str
    type: str
    label: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"type": self.type, "label": self.label, "metadata": self.metadata}


@dataclass
class Edge:
    src: str
    rel: str
    dst: str
    confidence: float = 0.5
    evidence_ref: str | None = None

    def key(self) -> tuple:
        return (self.src, self.rel, self.dst)

    def to_dict(self) -> dict:
        d = {"src": self.src, "rel": self.rel, "dst": self.dst,
             "confidence": self.confidence}
        if self.evidence_ref:
            d["evidence_ref"] = self.evidence_ref
        return d


class KnowledgeGraph:
    """A directed, attributed graph of everything Genesis knows about a project."""

    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        self._edges: dict[tuple, Edge] = {}

    # -- mutation -----------------------------------------------------------

    def add_node(self, node_id: str, node_type: str, label: str = "",
                 metadata: dict | None = None) -> Node:
        """Add or update a node. Idempotent: re-adding merges metadata so engines
        can enrich a node another engine already created."""
        node_id = str(node_id)
        existing = self._nodes.get(node_id)
        if existing is None:
            node = Node(id=node_id, type=node_type, label=label or node_id,
                        metadata=dict(metadata or {}))
            self._nodes[node_id] = node
            return node
        # merge: a real type upgrades a placeholder "unknown" (edges may have
        # auto-created the node untyped before a pass typed it); otherwise keep
        # the first real type. Update label if provided, merge metadata.
        if existing.type == "unknown" and node_type != "unknown":
            existing.type = node_type
        if label:
            existing.label = label
        if metadata:
            existing.metadata.update(metadata)
        return existing

    def add_edge(self, src: str, rel: str, dst: str, *,
                 confidence: float = 0.5,
                 evidence_ref: str | None = None) -> Edge:
        """Add a directed edge. Endpoints are auto-created as untyped nodes if
        missing (so order of engine passes doesn't matter). De-duplicates on
        (src, rel, dst); the higher-confidence version wins."""
        src, dst = str(src), str(dst)
        if src not in self._nodes:
            self.add_node(src, "unknown")
        if dst not in self._nodes:
            self.add_node(dst, "unknown")
        confidence = max(0.0, min(1.0, float(confidence)))
        edge = Edge(src=src, rel=rel, dst=dst, confidence=confidence,
                    evidence_ref=evidence_ref)
        prev = self._edges.get(edge.key())
        if prev is None or confidence > prev.confidence:
            self._edges[edge.key()] = edge
        return self._edges[edge.key()]

    # -- access -------------------------------------------------------------

    @property
    def nodes(self) -> dict[str, Node]:
        return self._nodes

    @property
    def edges(self) -> list[Edge]:
        return list(self._edges.values())

    def get_node(self, node_id: str) -> Node | None:
        return self._nodes.get(node_id)

    def neighbors(self, node_id: str, rel: str | None = None,
                  direction: str = "out") -> list[Node]:
        """Adjacent nodes. direction: 'out' (src->), 'in' (->dst), or 'both'."""
        out: list[Node] = []
        seen: set[str] = set()
        for e in self._edges.values():
            if rel is not None and e.rel != rel:
                continue
            target = None
            if direction in ("out", "both") and e.src == node_id:
                target = e.dst
            elif direction in ("in", "both") and e.dst == node_id:
                target = e.src
            if target and target not in seen and target in self._nodes:
                seen.add(target)
                out.append(self._nodes[target])
        return out

    def query(self, pattern: list[str]) -> list[list[str]]:
        """Find directed paths matching a relationship pattern.

        `pattern` is a list of node-type / rel tokens, alternating type and rel,
        e.g. ["cve", "affects", "package", "used_by", "module"]. Returns the list
        of matching paths (each a list of node ids). A type token of "*" matches
        any type. Bounded DFS over the (typically small) project graph.
        """
        if not pattern or len(pattern) % 2 == 0:
            return []  # must be type (rel type)*  -> odd length

        types = pattern[0::2]
        rels = pattern[1::2]

        def type_ok(node: Node, want: str) -> bool:
            return want == "*" or node.type == want

        results: list[list[str]] = []
        starts = [n for n in self._nodes.values() if type_ok(n, types[0])]

        def dfs(node_id: str, depth: int, path: list[str]) -> None:
            if depth == len(rels):
                results.append(list(path))
                return
            rel = rels[depth]
            want_type = types[depth + 1]
            for e in self._edges.values():
                if e.src == node_id and e.rel == rel:
                    nxt = self._nodes.get(e.dst)
                    if nxt and type_ok(nxt, want_type):
                        path.append(e.dst)
                        dfs(e.dst, depth + 1, path)
                        path.pop()

        for s in starts:
            dfs(s.id, 0, [s.id])
        return results

    # -- persistence --------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "nodes": {nid: n.to_dict() for nid, n in self._nodes.items()},
            "edges": [e.to_dict() for e in self._edges.values()],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "KnowledgeGraph":
        g = cls()
        for nid, nd in (d.get("nodes") or {}).items():
            g.add_node(nid, nd.get("type", "unknown"),
                       nd.get("label", ""), nd.get("metadata") or {})
        for ed in (d.get("edges") or []):
            try:
                g.add_edge(ed["src"], ed["rel"], ed["dst"],
                           confidence=ed.get("confidence", 0.5),
                           evidence_ref=ed.get("evidence_ref"))
            except (KeyError, TypeError):
                continue  # skip a malformed edge, keep the rest
        return g

    def stats(self) -> dict:
        by_type: dict[str, int] = {}
        for n in self._nodes.values():
            by_type[n.type] = by_type.get(n.type, 0) + 1
        return {"nodes": len(self._nodes), "edges": len(self._edges),
                "by_type": by_type}


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def _graph_path(project_root: Path) -> Path:
    return Path(project_root) / ".genesis" / "knowledge" / "graph.json"


def load_graph(project_root: Path | str = ".") -> KnowledgeGraph:
    p = _graph_path(Path(project_root))
    if not p.exists():
        return KnowledgeGraph()
    try:
        return KnowledgeGraph.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return KnowledgeGraph()  # corrupt -> start fresh, never crash


def save_graph(graph: KnowledgeGraph, project_root: Path | str = ".") -> Path | None:
    p = _graph_path(Path(project_root))
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(graph.to_dict(), indent=2), encoding="utf-8")
        return p
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Build pipeline: assemble from engine outputs (graceful, additive)
# ---------------------------------------------------------------------------

def add_architecture(graph: KnowledgeGraph, *, modules: list[str] | None = None,
                     anti_patterns: list[dict] | None = None,
                     drift_modules: list[str] | None = None) -> KnowledgeGraph:
    """Architecture pass: module nodes, anti-pattern nodes, drift markers.
    Each arg is optional; absent input contributes nothing (no fabrication)."""
    for m in (modules or []):
        graph.add_node(f"module:{m}", "module", label=m)
    for ap in (anti_patterns or []):
        name = ap.get("name") or ap.get("type") or "anti_pattern"
        mod = ap.get("module") or ap.get("location")
        ap_id = f"anti_pattern:{name}:{mod}" if mod else f"anti_pattern:{name}"
        graph.add_node(ap_id, "anti_pattern", label=name, metadata=ap)
        if mod:
            graph.add_edge(ap_id, "detected_in", f"module:{mod}",
                           confidence=float(ap.get("confidence", 0.7)))
    for m in (drift_modules or []):
        did = f"drift:{m}"
        graph.add_node(did, "drift", label=f"drift in {m}")
        graph.add_edge(did, "detected_in", f"module:{m}", confidence=0.8)
    return graph


def add_security(graph: KnowledgeGraph, *,
                 cves: list[dict] | None = None) -> KnowledgeGraph:
    """Security pass: CVE -> package -> module chains. Each cve dict may carry
    id, package, and affected modules."""
    for c in (cves or []):
        cid = f"cve:{c.get('id', 'unknown')}"
        graph.add_node(cid, "cve", label=c.get("id", "CVE"), metadata=c)
        pkg = c.get("package")
        if pkg:
            pid = f"package:{pkg}"
            graph.add_node(pid, "package", label=pkg)
            graph.add_edge(cid, "affects", pid,
                           confidence=float(c.get("confidence", 0.9)))
            for mod in (c.get("modules") or []):
                graph.add_node(f"module:{mod}", "module", label=mod)
                graph.add_edge(pid, "used_by", f"module:{mod}", confidence=0.7)
    return graph


def add_risks(graph: KnowledgeGraph, *,
              risks: list[dict] | None = None) -> KnowledgeGraph:
    """Recovery pass: risk nodes (incl. do-not-touch) located in modules."""
    for r in (risks or []):
        rid = f"risk:{r.get('id') or r.get('label', 'risk')}"
        graph.add_node(rid, "risk", label=r.get("label", "risk"), metadata=r)
        mod = r.get("module")
        if mod:
            graph.add_edge(rid, "located_in", f"module:{mod}",
                           confidence=float(r.get("confidence", 0.8)))
    return graph


def add_decisions(graph: KnowledgeGraph, *,
                  decisions: list[dict] | None = None) -> KnowledgeGraph:
    """Decision pass: decision nodes, supported by evidence, affecting modules."""
    for d in (decisions or []):
        did = f"decision:{d.get('id') or d.get('label', 'decision')}"
        graph.add_node(did, "decision", label=d.get("label", "decision"),
                       metadata={k: v for k, v in d.items()
                                 if k not in ("evidence", "modules")})
        for ev in (d.get("evidence") or []):
            eid = f"evidence:{ev}"
            graph.add_node(eid, "evidence", label=str(ev))
            graph.add_edge(eid, "supports", did, confidence=0.7, evidence_ref=str(ev))
        for mod in (d.get("modules") or []):
            graph.add_node(f"module:{mod}", "module", label=mod)
            graph.add_edge(did, "affects", f"module:{mod}", confidence=0.6)
    return graph


def add_field_findings(graph: KnowledgeGraph, *,
                       findings: list[dict] | None = None) -> KnowledgeGraph:
    """Field Intelligence pass: Reddit/YouTube findings warning about patterns."""
    for f in (findings or []):
        fid = f"field_finding:{f.get('id') or f.get('label', 'finding')}"
        graph.add_node(fid, "field_finding", label=f.get("label", "finding"),
                       metadata=f)
        pat = f.get("pattern") or f.get("library")
        if pat:
            pid = f"pattern:{pat}"
            graph.add_node(pid, "pattern", label=pat)
            graph.add_edge(fid, "warns_about", pid,
                           confidence=float(f.get("confidence", 0.5)),
                           evidence_ref=f.get("source"))
    return graph


def build_from_project(project_root: Path | str = ".", *,
                       architecture: dict | None = None,
                       security: dict | None = None,
                       risks: dict | None = None,
                       decisions: dict | None = None,
                       field_intel: dict | None = None,
                       persist: bool = True) -> KnowledgeGraph:
    """Assemble (or extend) the project knowledge graph from engine outputs.

    Starts from any existing `graph.json` (additive), runs each pass for the
    inputs provided, and optionally persists. Passing nothing returns the
    existing graph unchanged - it never invents nodes or edges.
    """
    graph = load_graph(project_root)
    if architecture:
        add_architecture(graph, **architecture)
    if security:
        add_security(graph, **security)
    if risks:
        add_risks(graph, **risks)
    if decisions:
        add_decisions(graph, **decisions)
    if field_intel:
        add_field_findings(graph, **field_intel)
    if persist:
        save_graph(graph, project_root)
    return graph
