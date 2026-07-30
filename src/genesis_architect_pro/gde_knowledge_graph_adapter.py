"""Genesis Decision Engine — Knowledge Graph adapter (additive).

Wires the Knowledge Graph Engine into the GDE as a production engine, in the
same shape as gde_engine_adapters / gde_engine_registration. Kept in its own
module so it registers additively without modifying the core 8-engine wiring.

The adapter consumes prior analysis outputs already in the SessionContext
(anti-patterns, drift) and builds/extends the connective graph at
`.genesis/knowledge/graph.json`. It runs after the analysis engines and is the
step that links code + findings into one queryable graph.

GDE contract: accepts SessionContext, returns a dict that may include
_confidence (float) and _warnings (list[str]). Never raises.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from genesis_architect_pro.engine_registry import get_default_registry
from genesis_architect_pro.gde_types import (
    EngineCategory,
    EngineDescriptor,
    GDEMode,
    SessionContext,
)


def _project_dir(ctx: SessionContext) -> Path:
    return ctx.project_dir


def _anti_patterns_from_ctx(ctx: SessionContext) -> list[dict]:
    """Normalize the antipattern_detector output (if present) into the dicts the
    knowledge-graph build pass expects. Returns [] when nothing is available -
    the graph then simply isn't enriched with anti-patterns (no fabrication)."""
    result = ctx.engine_results.get("antipattern_detector")
    if result is None or not getattr(result, "output", None):
        return []
    patterns = result.output.get("patterns") or []
    norm: list[dict] = []
    for item in patterns:
        if isinstance(item, dict):
            norm.append(item)
            continue
        # AntiPattern.file is the module the pattern was detected in.
        # affected_modules is a *different* thing (the related imports/importers
        # that made it a pattern, e.g. a hub-file's callers) - using it here
        # attributed every anti-pattern to some other, unrelated module instead
        # of the one it was actually found in, and left it edge-less whenever
        # that list happened to be empty.
        norm.append({
            "name": getattr(item, "type", "anti_pattern"),
            "module": getattr(item, "file", "") or "",
            "confidence": getattr(item, "confidence", 0.7),
        })
    return norm


def _modules_from_ctx(ctx: SessionContext) -> list[str]:
    """List of known module paths from the import_graph engine, if it ran."""
    result = ctx.engine_results.get("import_graph")
    if result is None or not getattr(result, "output", None):
        return []
    graph = result.output.get("graph") or {}
    return list(graph.get("modules", {}).keys())


def gde_run_knowledge_graph(ctx: SessionContext) -> dict[str, Any]:
    """Build/extend the project knowledge graph from session analysis outputs."""
    try:
        from genesis_architect_pro import knowledge_graph as kg
    except ImportError as exc:
        return {"_confidence": 0.2, "_warnings": [f"knowledge_graph unavailable: {exc}"]}

    project_dir = _project_dir(ctx)
    anti_patterns = _anti_patterns_from_ctx(ctx)
    modules = _modules_from_ctx(ctx)
    architecture = (
        {"anti_patterns": anti_patterns, "modules": modules}
        if (anti_patterns or modules) else None
    )

    try:
        graph = kg.build_from_project(project_dir, architecture=architecture,
                                      persist=True)
    except Exception as exc:
        return {"_confidence": 0.3, "_warnings": [f"knowledge_graph build failed: {exc}"]}

    stats = graph.stats()
    warnings: list[str] = []
    if stats["nodes"] == 0:
        warnings.append("knowledge graph is empty (no analysis inputs yet)")
    return {
        "knowledge_graph_stats": stats,
        "graph_path": str(project_dir / ".genesis" / "knowledge" / "graph.json"),
        "_confidence": 0.8 if stats["nodes"] else 0.4,
        "_warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Descriptor + additive registration
# ---------------------------------------------------------------------------

KNOWLEDGE_GRAPH_DESCRIPTOR = EngineDescriptor(
    id="knowledge_graph",
    name="Knowledge Graph",
    module="genesis_architect_pro.gde_knowledge_graph_adapter",
    entry_point="gde_run_knowledge_graph",
    category=EngineCategory.PERSISTENCE,
    input_keys=["project_dir", "patterns"],
    output_keys=["knowledge_graph_stats", "graph_path"],
    requires=["antipattern_detector"],
    is_optional=True,
    write_operations=["knowledge_graph_json"],
    timeout_seconds=30,
    modes=[GDEMode.RECOVERY, GDEMode.REFACTOR],
)


def register_knowledge_graph() -> bool:
    """Register the knowledge-graph engine in the default registry if the engine
    it depends on (antipattern_detector) is present. Returns True if registered.

    Idempotent: skips if already registered. Safe to import-and-register after
    gde_engine_registration has run."""
    reg = get_default_registry()
    if "knowledge_graph" in reg:
        return False
    # Ensure the core engines (incl. antipattern_detector) are registered first,
    # so our dependency exists and the registry stays valid regardless of import
    # order.
    if "antipattern_detector" not in reg:
        try:
            import genesis_architect_pro.gde_engine_registration  # noqa: F401
        except Exception:
            return False
    if "antipattern_detector" not in reg:
        return False
    reg.register(KNOWLEDGE_GRAPH_DESCRIPTOR)
    return True


# NOTE: intentionally NOT auto-registered on import. The knowledge graph is an
# opt-in connective layer; callers that want it in a GDE run call
# register_knowledge_graph() explicitly. This keeps the default registry's core
# engine set stable for callers/tests that assert on it.
