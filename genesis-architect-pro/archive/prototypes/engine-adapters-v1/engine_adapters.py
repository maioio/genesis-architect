"""
Engine adapters for the Genesis Decision Engine (Pro).

The GDE runner (gde_runner) invokes engines through a uniform contract:

    fn(ctx: SessionContext) -> dict      # may set _confidence / _warnings

The real analysis engines (architecture scorer, recovery report, security
templates, knowledge graph, ...) each have their own natural signatures. This
module provides thin ADAPTERS that bridge them to the GDE contract, plus the
`EngineDescriptor`s that register them, and `register_builtin_engines()` to wire
them into a registry in one call.

This is the layer that turns the GDE from a skeleton orchestrator into one that
actually drives Genesis's real engines.

Design rules:
  - Adapters are thin: read inputs from the SessionContext, call the real engine,
    return its output as a dict. No business logic lives here.
  - Graceful degradation (honesty clause): if a real engine is unavailable or a
    source is empty, the adapter returns a low-confidence result with a warning
    rather than raising. The runner records DEGRADED; it never fabricates data.
  - Determinism where the underlying engine is deterministic.
  - No duplication: adapters import and call the existing engines; they never
    reimplement them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from genesis_architect_pro.gde_types import (
    EngineCategory,
    EngineDescriptor,
    GDEMode,
    SessionContext,
)


# ---------------------------------------------------------------------------
# Adapter helpers
# ---------------------------------------------------------------------------

def _project_dir(ctx: SessionContext) -> Path:
    return Path(getattr(ctx, "project_dir", ".") or ".")


def _degraded(reason: str, confidence: float = 0.2) -> dict[str, Any]:
    """Standard graceful-degradation payload: a warning + low confidence,
    never an exception. The runner turns this into a DEGRADED result."""
    return {"_confidence": confidence, "_warnings": [reason], "available": False}


# ---------------------------------------------------------------------------
# Adapters (each matches fn(ctx) -> dict)
# ---------------------------------------------------------------------------

def architecture_adapter(ctx: SessionContext) -> dict[str, Any]:
    """Wrap the architecture scorer: produce a 0-100 score + label."""
    try:
        from genesis_architect_pro.architecture_scorer import (
            score_project, score_label,
        )
    except ImportError as exc:
        return _degraded(f"architecture scorer unavailable: {exc}")

    project = _project_dir(ctx)
    try:
        score = score_project(project)
    except Exception as exc:  # underlying engine problem -> degrade, don't crash
        return _degraded(f"architecture scoring failed: {exc}")

    # score_project returns a dict with 'total' (0-100) and 'confidence'.
    if not isinstance(score, dict) or "total" not in score:
        return _degraded("architecture score has unexpected shape")
    try:
        numeric = float(score["total"])
    except (TypeError, ValueError):
        return _degraded("architecture score not numeric")

    label = ""
    try:
        label = score_label(int(round(numeric)))
    except Exception:
        label = ""
    return {"architecture_score": numeric, "architecture_label": label,
            "architecture_detail": {k: score.get(k) for k in
                                    ("modularity", "coupling", "cohesion",
                                     "layering", "module_count")},
            "_confidence": float(score.get("confidence", 0.9))}


def antipattern_adapter(ctx: SessionContext) -> dict[str, Any]:
    """Wrap the anti-pattern detector."""
    try:
        from genesis_architect_pro.antipattern_detector import detect_all
    except ImportError as exc:
        return _degraded(f"anti-pattern detector unavailable: {exc}")
    try:
        report = detect_all(_project_dir(ctx))
    except Exception as exc:
        return _degraded(f"anti-pattern detection failed: {exc}")
    # detect_all returns an AntiPatternReport with a .patterns list.
    patterns = list(getattr(report, "patterns", []) or [])
    return {"anti_patterns": patterns, "anti_pattern_count": len(patterns),
            "anti_pattern_severity": {
                "critical": getattr(report, "critical_count", 0),
                "high": getattr(report, "high_count", 0),
                "medium": getattr(report, "medium_count", 0),
                "low": getattr(report, "low_count", 0),
            },
            "_confidence": 0.85}


def recovery_adapter(ctx: SessionContext) -> dict[str, Any]:
    """Wrap the recovery report generator."""
    try:
        from genesis_architect_pro.recovery_report import (
            generate_report_for_project,
        )
    except ImportError as exc:
        return _degraded(f"recovery engine unavailable: {exc}")
    try:
        report = generate_report_for_project(_project_dir(ctx))
    except Exception as exc:
        return _degraded(f"recovery report failed: {exc}")
    if report is None:
        return _degraded("recovery report produced nothing (empty project?)")
    return {"recovery_report": report, "_confidence": 0.8}


def security_adapter(ctx: SessionContext) -> dict[str, Any]:
    """Wrap the security templates generator."""
    try:
        from genesis_architect_pro.security_templates import generate_security_docs
    except ImportError as exc:
        return _degraded(f"security engine unavailable: {exc}")
    try:
        docs = generate_security_docs(_project_dir(ctx))
    except Exception as exc:
        return _degraded(f"security generation failed: {exc}")
    return {"security_docs": docs, "_confidence": 0.8}


def knowledge_graph_adapter(ctx: SessionContext) -> dict[str, Any]:
    """Wrap the Knowledge Graph: assemble/extend the project graph from whatever
    prior engine results are present in the session, then persist + summarize.

    This adapter is the integration point that links the GDE run's outputs into
    the connective graph. It reads earlier engine_results off the context."""
    try:
        from genesis_architect_pro import knowledge_graph as kg
    except ImportError as exc:
        return _degraded(f"knowledge graph unavailable: {exc}")

    project = _project_dir(ctx)
    results = getattr(ctx, "engine_results", {}) or {}

    architecture: dict[str, Any] = {}
    security: dict[str, Any] = {}

    ap = results.get("antipattern")
    if ap is not None and getattr(ap, "output", None):
        aps = ap.output.get("anti_patterns") or []
        # normalize to the dicts the kg build pass expects
        norm = []
        for item in aps:
            if isinstance(item, dict):
                norm.append(item)
            else:  # AntiPattern dataclass -> name + first affected module
                modules = getattr(item, "affected_modules", None) or []
                norm.append({
                    "name": getattr(item, "type", "anti_pattern"),
                    "module": modules[0] if modules else "",
                    "confidence": getattr(item, "confidence", 0.7),
                })
        architecture["anti_patterns"] = norm

    try:
        graph = kg.build_from_project(project, architecture=architecture or None,
                                      security=security or None, persist=True)
    except Exception as exc:
        return _degraded(f"knowledge graph build failed: {exc}")

    return {"knowledge_graph_stats": graph.stats(), "_confidence": 0.7}


# ---------------------------------------------------------------------------
# Descriptors
# ---------------------------------------------------------------------------

# Each adapter lives in THIS module; entry_point is the function name.
_ADAPTER_MODULE = "genesis_architect_pro.engine_adapters"

BUILTIN_DESCRIPTORS: list[EngineDescriptor] = [
    EngineDescriptor(
        id="architecture",
        name="Architecture Scorer",
        module=_ADAPTER_MODULE,
        entry_point="architecture_adapter",
        category=EngineCategory.ANALYSIS,
        input_keys=[],
        output_keys=["architecture_score", "architecture_label"],
        modes=[GDEMode.RECOVERY, GDEMode.REFACTOR, GDEMode.BUILD],
    ),
    EngineDescriptor(
        id="antipattern",
        name="Anti-Pattern Detector",
        module=_ADAPTER_MODULE,
        entry_point="antipattern_adapter",
        category=EngineCategory.ANALYSIS,
        input_keys=[],
        output_keys=["anti_patterns", "anti_pattern_count"],
        modes=[GDEMode.RECOVERY, GDEMode.REFACTOR],
    ),
    EngineDescriptor(
        id="recovery",
        name="Recovery Report",
        module=_ADAPTER_MODULE,
        entry_point="recovery_adapter",
        category=EngineCategory.REPORT,
        input_keys=["architecture_score"],
        output_keys=["recovery_report"],
        requires=["architecture"],
        is_optional=True,
        modes=[GDEMode.RECOVERY],
    ),
    EngineDescriptor(
        id="security",
        name="Security Templates",
        module=_ADAPTER_MODULE,
        entry_point="security_adapter",
        category=EngineCategory.REPORT,
        input_keys=[],
        output_keys=["security_docs"],
        is_optional=True,
        modes=[GDEMode.RECOVERY, GDEMode.BUILD],
    ),
    EngineDescriptor(
        id="knowledge_graph",
        name="Knowledge Graph",
        module=_ADAPTER_MODULE,
        entry_point="knowledge_graph_adapter",
        category=EngineCategory.PERSISTENCE,
        input_keys=["anti_patterns"],
        output_keys=["knowledge_graph_stats"],
        requires=["antipattern"],
        is_optional=True,
        write_operations=["write:.genesis/knowledge/graph.json"],
        modes=[GDEMode.RECOVERY, GDEMode.REFACTOR],
    ),
]

# Map of id -> callable, for direct lookup/testing.
ADAPTERS: dict[str, Callable[[SessionContext], dict[str, Any]]] = {
    "architecture": architecture_adapter,
    "antipattern": antipattern_adapter,
    "recovery": recovery_adapter,
    "security": security_adapter,
    "knowledge_graph": knowledge_graph_adapter,
}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_builtin_engines(registry, *, replace: bool = False) -> list[str]:
    """Register all built-in engine adapters into the given registry.

    Returns the list of engine ids registered. Idempotent when replace=True.
    Skips (without error) any descriptor whose id is already present when
    replace=False, so calling twice does not raise."""
    registered: list[str] = []
    for desc in BUILTIN_DESCRIPTORS:
        if desc.id in registry:
            if replace:
                registry.replace(desc)
                registered.append(desc.id)
            continue
        registry.register(desc)
        registered.append(desc.id)
    return registered
