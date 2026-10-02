"""
import_audit.py - Genesis Architect PRO

Declared-vs-actual import audit. Compares the architecture model's DECLARED
relationships (ModelLink src->dst) against the ACTUAL import edges parsed from
the code (import_graph). Catches "the diagram lies": declared links with no real
import, and real imports the model never declared.

Design:
- READ-ONLY. Reads the committed model + builds the import graph. Mutates nothing.
- Deterministic, no LLM, no network.
- Dependency-light (stdlib + existing Genesis modules only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AuditFinding:
    kind: str          # "missing_import" | "undeclared_import"
    src: str
    dst: str
    detail: str


@dataclass
class ImportAuditReport:
    declared_links: int = 0
    actual_edges: int = 0
    matched: int = 0
    missing_imports: list[AuditFinding] = field(default_factory=list)   # declared, no real import
    undeclared_imports: list[AuditFinding] = field(default_factory=list)  # real, not declared
    notes: list[str] = field(default_factory=list)

    @property
    def consistent(self) -> bool:
        return not self.missing_imports and not self.undeclared_imports


def _node_file_map(model) -> dict[str, str]:
    """Map node id -> a file/module hint, using technology/name/anchors.

    Best-effort: nodes that map to a module path enable edge comparison. Nodes
    with no file mapping are skipped from the actual-edge comparison (noted).
    """
    mapping: dict[str, str] = {}
    for node in getattr(model, "nodes", []):
        # Prefer an explicit source anchor / technology path if present.
        hint = getattr(node, "technology", None) or node.name
        if hint:
            mapping[node.id] = str(hint)
    return mapping


def _actual_edges(project_path: Path) -> set[tuple[str, str]]:
    """Build the set of actual (src_module, dst_module) import edges."""
    from genesis_architect.core.import_graph import build_graph, detect_language
    lang = detect_language(project_path)
    graph = build_graph(project_path, language=lang)
    edges: set[tuple[str, str]] = set()
    for mod, data in graph.get("modules", {}).items():
        for imp in data.get("imports", []):
            edges.add((mod, imp))
    return edges


def _norm(name: str) -> set[str]:
    """Normalize a module/node identifier into its path segments + basename
    stem, for token-level (not substring) comparison.

    "src/foo/bar.py" -> {"src", "foo", "bar"};  "bar" -> {"bar"}
    """
    raw = str(name).replace("\\", "/")
    segs = [s for s in raw.replace(".py", "").split("/") if s]
    if not segs:
        segs = [raw]
    return set(segs) | {segs[-1]}


def _endpoint_matches(a: str, b: str) -> bool:
    """Two endpoints match if their final segment (the module/component name)
    is identical. Token-level - avoids the false positives of substring matching
    on short names (e.g. 'c' matching every path)."""
    return bool(_norm(a) and _norm(b) and (
        list(_norm(a))[-1:] == list(_norm(b))[-1:] or
        _last_seg(a) == _last_seg(b)
    ))


def _last_seg(name: str) -> str:
    raw = str(name).replace("\\", "/").replace(".py", "")
    segs = [s for s in raw.split("/") if s]
    return segs[-1] if segs else raw


def _edge_matches(declared: tuple[str, str], actual: set[tuple[str, str]]) -> bool:
    """A declared (src,dst) matches an actual edge when BOTH endpoints match by
    final module segment (not loose substring)."""
    d_src, d_dst = declared
    for a_src, a_dst in actual:
        if _last_seg(d_src) == _last_seg(a_src) and _last_seg(d_dst) == _last_seg(a_dst):
            return True
    return False


def audit(project_path: str | Path, model=None) -> ImportAuditReport:
    """Run the declared-vs-actual import audit. Read-only.

    model: an ArchModel; if None, loads the committed model from .genesis/.
    """
    root = Path(project_path).resolve()
    report = ImportAuditReport()

    if model is None:
        try:
            from genesis_architect_pro.model_store import ModelStore
            model = ModelStore(root).load_committed()
        except Exception as exc:  # noqa: BLE001
            report.notes.append(f"No committed model to audit: {exc}")
            return report

    links = list(getattr(model, "links", []))
    report.declared_links = len(links)

    actual = _actual_edges(root)
    report.actual_edges = len(actual)

    node_file = _node_file_map(model)
    if not links:
        report.notes.append("Model declares no links; checking for undeclared imports only.")
        # No declared links to verify, but real imports between modeled nodes
        # are still worth flagging as undeclared - fall through to section 2.

    # 1. Declared links with no matching actual import.
    declared_pairs: set[tuple[str, str]] = set()
    for link in links:
        src = node_file.get(link.src, link.src)
        dst = node_file.get(link.dst, link.dst)
        declared_pairs.add((src, dst))
        if _edge_matches((src, dst), actual):
            report.matched += 1
        else:
            report.missing_imports.append(AuditFinding(
                kind="missing_import", src=src, dst=dst,
                detail=f"Model declares {src} -> {dst}, but no matching import exists.",
            ))

    # 2. Actual imports between modeled nodes that the model never declared.
    modeled_segs = {_last_seg(v) for v in node_file.values()}
    for a_src, a_dst in actual:
        if _last_seg(a_src) in modeled_segs and _last_seg(a_dst) in modeled_segs:
            if not _edge_matches((a_src, a_dst), declared_pairs):
                report.undeclared_imports.append(AuditFinding(
                    kind="undeclared_import", src=a_src, dst=a_dst,
                    detail=f"Code imports {a_src} -> {a_dst}, but the model declares no such link.",
                ))

    return report


def format_report(report: ImportAuditReport) -> str:
    lines = ["Import Audit (declared vs actual)"]
    lines.append(f"  declared links: {report.declared_links} | actual edges: "
                 f"{report.actual_edges} | matched: {report.matched}")
    if report.notes:
        for n in report.notes:
            lines.append(f"  note: {n}")
    if report.missing_imports:
        lines.append(f"  MISSING ({len(report.missing_imports)}) - declared but no import:")
        for f in report.missing_imports[:20]:
            lines.append(f"    - {f.src} -> {f.dst}")
    if report.undeclared_imports:
        lines.append(f"  UNDECLARED ({len(report.undeclared_imports)}) - imported but not modeled:")
        for f in report.undeclared_imports[:20]:
            lines.append(f"    - {f.src} -> {f.dst}")
    lines.append("")
    lines.append("RESULT: " + ("CONSISTENT" if report.consistent
                               else "INCONSISTENT - model and code diverge"))
    return "\n".join(lines)
