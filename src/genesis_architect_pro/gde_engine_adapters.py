"""Genesis Decision Engine — engine adapter functions.

Each function wraps one production engine's native API into the GDE contract:
  - Accepts a SessionContext
  - Reads project_dir and any dependency outputs from ctx.engine_results
  - Returns a dict; may include _confidence (float) and _warnings (list[str])

The runner calls these via importlib using the module/entry_point from each
EngineDescriptor. No adapter knows about any other adapter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from genesis_architect_pro.gde_types import SessionContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _output(engine_id: str, ctx: SessionContext) -> dict[str, Any]:
    """Retrieve the output dict from a completed upstream engine."""
    result = ctx.engine_results.get(engine_id)
    if result is None:
        return {}
    return result.output


def _project_dir(ctx: SessionContext) -> Path:
    return ctx.project_dir


# ---------------------------------------------------------------------------
# Adapter functions
# ---------------------------------------------------------------------------


def gde_run_import_graph(ctx: SessionContext) -> dict[str, Any]:
    from genesis_architect_pro.import_graph import load_or_build

    project_dir = _project_dir(ctx)
    try:
        graph = load_or_build(project_dir)
    except Exception as exc:
        return {"_confidence": 0.5, "_warnings": [f"import_graph partial: {exc}"]}

    cycles = [
        list(cycle) for cycle in (graph.cycles if hasattr(graph, "cycles") else [])
    ]
    dark = list(graph.dark_modules) if hasattr(graph, "dark_modules") else []

    confidence = 1.0
    warnings: list[str] = []
    if cycles:
        warnings.append(f"{len(cycles)} circular dependenc{'y' if len(cycles)==1 else 'ies'} detected")
        confidence -= min(0.30, 0.05 * len(cycles))

    return {
        "graph": graph,
        "cycles": cycles,
        "dark_modules": dark,
        "layer_map": getattr(graph, "layer_map", {}),
        "_confidence": max(0.5, confidence),
        "_warnings": warnings,
    }


def gde_run_architecture_scorer(ctx: SessionContext) -> dict[str, Any]:
    from genesis_architect_pro.architecture_scorer import score_project

    project_dir = _project_dir(ctx)
    graph = _output("import_graph", ctx).get("graph")

    try:
        result = score_project(project_dir)
    except Exception as exc:
        return {"_confidence": 0.4, "_warnings": [f"architecture_scorer failed: {exc}"]}

    score = getattr(result, "score", None) or (result if isinstance(result, (int, float)) else 0)
    label = getattr(result, "label", "")
    dimensions = getattr(result, "dimensions", {})
    if hasattr(dimensions, "__dict__"):
        dimensions = dimensions.__dict__

    warnings: list[str] = []
    if isinstance(score, (int, float)) and score < 40:
        warnings.append(f"Architecture score critical: {score}/100")

    return {
        "score": score,
        "score_label": str(label),
        "dimensions": dimensions,
        "history": [],
        "_confidence": 1.0,
        "_warnings": warnings,
    }


def gde_run_antipattern_detector(ctx: SessionContext) -> dict[str, Any]:
    from genesis_architect_pro.antipattern_detector import detect_all

    project_dir = _project_dir(ctx)

    try:
        report = detect_all(project_dir)
    except Exception as exc:
        return {"_confidence": 0.4, "_warnings": [f"antipattern_detector failed: {exc}"]}

    patterns = getattr(report, "patterns", []) or []
    critical = [p for p in patterns if getattr(p, "severity", "") in ("CRITICAL",)]
    high = [p for p in patterns if getattr(p, "severity", "") == "HIGH"]

    warnings: list[str] = []
    if critical:
        warnings.append(f"{len(critical)} CRITICAL anti-pattern(s) found")

    return {
        "patterns": patterns,
        "critical_count": len(critical),
        "high_count": len(high),
        "_confidence": 1.0,
        "_warnings": warnings,
    }


def gde_run_fragility_classifier(ctx: SessionContext) -> dict[str, Any]:
    from genesis_architect_pro.fragility_classifier import classify_all

    project_dir = _project_dir(ctx)

    try:
        report = classify_all(project_dir)
    except Exception as exc:
        return {"_confidence": 0.4, "_warnings": [f"fragility_classifier failed: {exc}"]}

    classifications = getattr(report, "classifications", []) or []
    volatile = [c for c in classifications if getattr(c, "status", "") == "VOLATILE"]
    fragile = [c for c in classifications if getattr(c, "status", "") == "FRAGILE"]
    stable = [c for c in classifications if getattr(c, "status", "") == "STABLE"]

    warnings: list[str] = []
    if volatile:
        warnings.append(f"{len(volatile)} VOLATILE module(s) detected")

    return {
        "fragility_map": classifications,
        "volatile_count": len(volatile),
        "fragile_count": len(fragile),
        "stable_count": len(stable),
        "_confidence": 1.0,
        "_warnings": warnings,
    }


def gde_run_recovery_report(ctx: SessionContext) -> dict[str, Any]:
    from genesis_architect_pro.recovery_report import generate_report_for_project

    project_dir = _project_dir(ctx)

    try:
        report = generate_report_for_project(project_dir)
    except Exception as exc:
        return {"_confidence": 0.4, "_warnings": [f"recovery_report failed: {exc}"]}

    risk = getattr(report, "metadata", None)
    risk_level = getattr(risk, "risk_level", "unknown") if risk else "unknown"
    recs = getattr(report, "recommendations", []) or []

    # Update SessionContext risk level
    ctx.project_risk_level = str(risk_level)

    return {
        "report_path": str(project_dir / "PROJECT_RECOVERY_REPORT.md"),
        "risk_level": str(risk_level),
        "recommendations": [str(r) for r in recs[:10]],
        "_confidence": 1.0,
        "_warnings": [],
    }


def gde_run_refactoring_planner(ctx: SessionContext) -> dict[str, Any]:
    from genesis_architect_pro.refactoring_planner import generate_plan

    project_dir = _project_dir(ctx)

    try:
        plan = generate_plan(project_dir)
    except Exception as exc:
        return {"_confidence": 0.4, "_warnings": [f"refactoring_planner failed: {exc}"]}

    steps = getattr(plan, "steps", []) or []
    tier1 = [s for s in steps if getattr(s, "tier", 0) == 1]
    tier2 = [s for s in steps if getattr(s, "tier", 0) == 2]

    return {
        "plan_path": str(project_dir / "REFACTORING_PLAN.md"),
        "tier1_count": len(tier1),
        "tier2_count": len(tier2),
        "_confidence": 1.0,
        "_warnings": [],
    }


def gde_run_c4_generator(ctx: SessionContext) -> dict[str, Any]:
    from genesis_architect_pro.c4_generator import generate_c4_doc

    project_dir = _project_dir(ctx)
    output_path = project_dir / "docs" / "architecture" / "C4_ARCHITECTURE.md"

    try:
        generate_c4_doc(project_dir, output_path=output_path)
    except Exception as exc:
        return {"_confidence": 0.4, "_warnings": [f"c4_generator failed: {exc}"]}

    return {
        "doc_path": str(output_path),
        "_confidence": 1.0,
        "_warnings": [],
    }


def gde_run_security_templates(ctx: SessionContext) -> dict[str, Any]:
    from genesis_architect_pro.security_templates import generate_security_docs

    project_dir = _project_dir(ctx)

    try:
        result = generate_security_docs(project_dir)
    except Exception as exc:
        return {"_confidence": 0.4, "_warnings": [f"security_templates failed: {exc}"]}

    stride_path = result.get("stride_path", "") if isinstance(result, dict) else ""
    owasp_path = result.get("owasp_path", "") if isinstance(result, dict) else ""

    return {
        "stride_path": str(stride_path),
        "owasp_path": str(owasp_path),
        "_confidence": 1.0,
        "_warnings": [],
    }
