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


# ---------------------------------------------------------------------------
# RESEARCH mode adapters
# ---------------------------------------------------------------------------


def gde_run_source_registry(ctx: SessionContext) -> dict[str, Any]:
    """Load the source registry for this project — foundation for research engines."""
    from genesis_architect_pro.source_registry import load_registry

    project_dir = _project_dir(ctx)
    try:
        registry = load_registry(project_dir)
        sources = registry.sources or []
    except Exception as exc:
        return {"_confidence": 0.5, "_warnings": [f"source_registry load failed: {exc}"],
                "registry": None, "source_count": 0}

    return {
        "registry": registry,
        "source_count": len(sources),
        "_confidence": 1.0,
        "_warnings": [] if sources else ["no custom sources configured — using defaults"],
    }


def gde_run_field_intelligence(ctx: SessionContext) -> dict[str, Any]:
    """Run the Reddit Answers field intelligence workflow to surface developer sentiment."""
    from genesis_architect_pro.field_intelligence import run_field_workflow

    # Derive the tool name from the session instruction or project dir name
    project_dir = _project_dir(ctx)
    tool_name = ctx.instruction or project_dir.name

    try:
        report = run_field_workflow(tool=tool_name)
    except Exception as exc:
        return {"_confidence": 0.4, "_warnings": [f"field_intelligence failed: {exc}"],
                "findings": [], "verified_count": 0}

    findings = report.findings if hasattr(report, "findings") else []
    verified = [f for f in findings if getattr(f, "verified", False)]
    warnings: list[str] = []
    if not findings:
        warnings.append("no field findings returned — check network access")

    return {
        "findings": findings,
        "verified_count": len(verified),
        "queries": getattr(report, "queries", []),
        "_confidence": 0.8 if verified else (0.5 if findings else 0.3),
        "_warnings": warnings,
    }


def gde_run_evidence_pack(ctx: SessionContext) -> dict[str, Any]:
    """Build an evidence pack from research findings and source registry."""
    from genesis_architect_pro.evidence_pack import build_evidence_pack, save_evidence_pack

    project_dir = _project_dir(ctx)
    findings = _output("field_intelligence", ctx).get("findings", [])
    registry = _output("source_registry", ctx).get("registry")

    question = ctx.instruction or f"Is {project_dir.name} safe to build on?"

    try:
        items: list[dict] = []
        for f in findings[:20]:  # cap at 20 items
            items.append({
                "source_id": getattr(f, "source_id", "field"),
                "claim": getattr(f, "claim", str(f)),
                "url": getattr(f, "url", ""),
                "status": "verified" if getattr(f, "verified", False) else "unverified",
            })

        pack = build_evidence_pack(question, items,
                                   recommendation="See findings above for risks and pitfalls.")
        saved_path = save_evidence_pack(pack, "research_session", project_dir)
    except Exception as exc:
        return {"_confidence": 0.4, "_warnings": [f"evidence_pack failed: {exc}"],
                "pack_path": "", "item_count": 0}

    return {
        "pack_path": str(saved_path) if saved_path else "",
        "item_count": len(items),
        "_confidence": 1.0,
        "_warnings": [],
    }


# ---------------------------------------------------------------------------
# BUILD mode adapters
# ---------------------------------------------------------------------------


def gde_run_build_scaffold(ctx: SessionContext) -> dict[str, Any]:
    """Invoke the genesis-architect free core to scaffold a new project."""
    project_dir = _project_dir(ctx)
    instruction = ctx.instruction or ""

    # Extract vision from instruction — BUILD mode sessions carry the project description
    vision = instruction
    for prefix in ("build ", "scaffold ", "create ", "generate ", "init "):
        if instruction.lower().startswith(prefix):
            vision = instruction[len(prefix):]
            break

    if not vision:
        return {
            "_confidence": 0.2,
            "_warnings": ["BUILD mode requires a project description in the instruction"],
            "scaffold_path": "",
            "vision": "",
        }

    try:
        # The free core scaffold is available via genesis CLI — call programmatically
        # via genesis_architect package if importable, else report as advisory
        import genesis_architect  # type: ignore[import]
        scaffold_fn = getattr(genesis_architect, "scaffold", None)
        if scaffold_fn and callable(scaffold_fn):
            result = scaffold_fn(vision=vision, output_dir=project_dir)
            scaffold_path = str(result) if result else str(project_dir)
        else:
            scaffold_path = ""
            return {
                "_confidence": 0.6,
                "_warnings": ["genesis-architect core scaffold() not directly callable — "
                              "run `genesis init` in the target directory"],
                "scaffold_path": scaffold_path,
                "vision": vision,
            }
    except ImportError:
        return {
            "_confidence": 0.5,
            "_warnings": ["genesis-architect free core not installed; "
                          "run `pip install genesis-architect` then `genesis init`"],
            "scaffold_path": "",
            "vision": vision,
        }
    except Exception as exc:
        return {"_confidence": 0.4, "_warnings": [f"build_scaffold failed: {exc}"],
                "scaffold_path": "", "vision": vision}

    return {
        "scaffold_path": scaffold_path,
        "vision": vision,
        "_confidence": 1.0,
        "_warnings": [],
    }


# ---------------------------------------------------------------------------
# COMMITTEE mode adapters
# ---------------------------------------------------------------------------


def gde_run_committee_analysis(ctx: SessionContext) -> dict[str, Any]:
    """Run a multi-perspective analysis — recovery + gate + document in read-only mode.

    The Committee mode runs all three analysis lenses (health, compliance, docs)
    without committing any outputs, then surfaces the consolidated perspectives
    for human judgment. It is a meta-engine: it collects results from upstream
    engines that have already been run and synthesises a divergence report.
    """
    project_dir = _project_dir(ctx)

    perspectives: list[dict] = []
    warnings: list[str] = []
    confidence = 1.0

    # Collect results from any engines that ran upstream
    for engine_id, label in [
        ("recovery_report", "Health"),
        ("architecture_scorer", "Architecture"),
        ("antipattern_detector", "Anti-Patterns"),
        ("fragility_classifier", "Fragility"),
        ("security_templates", "Security"),
    ]:
        result = ctx.engine_results.get(engine_id)
        if result is None:
            continue
        out = result.output or {}
        perspectives.append({
            "lens": label,
            "engine": engine_id,
            "confidence": getattr(result, "confidence", 1.0),
            "summary": _summarize_output(engine_id, out),
            "warnings": getattr(result, "warnings", []),
        })

    if not perspectives:
        warnings.append("no upstream engine results to consolidate — run analysis engines first")
        confidence = 0.2

    # Check for diverging assessments
    divergent = _find_divergence(perspectives)
    if divergent:
        warnings.append(f"divergent assessments detected across: {', '.join(divergent)}")
        confidence -= 0.10

    # Write consolidated report
    report_lines = [f"# Committee Analysis — {project_dir.name}\n"]
    for p in perspectives:
        report_lines.append(f"\n## {p['lens']} Perspective\n{p['summary']}")
    if divergent:
        report_lines.append(f"\n## Divergence\nLenses disagree on: {', '.join(divergent)}")

    report_path = project_dir / ".genesis" / "committee_report.md"
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("\n".join(report_lines), encoding="utf-8")
    except Exception as exc:
        warnings.append(f"could not write committee report: {exc}")

    return {
        "perspectives": perspectives,
        "perspective_count": len(perspectives),
        "divergent_lenses": divergent,
        "report_path": str(report_path),
        "_confidence": max(0.2, confidence),
        "_warnings": warnings,
    }


def _summarize_output(engine_id: str, out: dict) -> str:
    """Produce a one-line summary for each engine's output."""
    if engine_id == "recovery_report":
        return f"Risk level: {out.get('risk_level', 'unknown')}. Recommendations: {len(out.get('recommendations', []))}"
    if engine_id == "architecture_scorer":
        return f"Score: {out.get('score', '?')}/100 ({out.get('score_label', '')})"
    if engine_id == "antipattern_detector":
        return f"Critical: {out.get('critical_count', 0)}, High: {out.get('high_count', 0)}"
    if engine_id == "fragility_classifier":
        return (f"Volatile: {out.get('volatile_count', 0)}, "
                f"Fragile: {out.get('fragile_count', 0)}, Stable: {out.get('stable_count', 0)}")
    if engine_id == "security_templates":
        paths = [p for p in [out.get("stride_path"), out.get("owasp_path")] if p]
        return f"Generated: {', '.join(paths) if paths else 'none'}"
    return str(out)[:120]


def _find_divergence(perspectives: list[dict]) -> list[str]:
    """Identify lenses with unusually low confidence vs the average."""
    if len(perspectives) < 2:
        return []
    confs = [p["confidence"] for p in perspectives]
    avg = sum(confs) / len(confs)
    return [p["lens"] for p in perspectives if p["confidence"] < avg - 0.25]
