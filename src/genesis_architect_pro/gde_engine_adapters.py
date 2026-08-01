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


def _instruction(ctx: SessionContext) -> str:
    """The user's free-text instruction for this session.

    SessionContext has no `instruction` attribute of its own — the raw text
    lives on ctx.intent (set at INTAKE). Engines that need it (field
    intelligence, evidence pack, build scaffold) must go through here.
    """
    return ctx.intent.raw_text if ctx.intent is not None else ""


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

    # build_graph returns a dict: {"modules": {...}, "cycles": [...], ...}
    if isinstance(graph, dict):
        raw_cycles = graph.get("cycles", [])
        dark = list(graph.get("dark_modules", []))
        layer_map = {mod: data.get("layer", "unknown")
                     for mod, data in graph.get("modules", {}).items()}
    else:  # tolerate an object-shaped graph from older/newer cores
        raw_cycles = graph.cycles if hasattr(graph, "cycles") else []
        dark = list(graph.dark_modules) if hasattr(graph, "dark_modules") else []
        layer_map = getattr(graph, "layer_map", {})
    cycles = [list(cycle) for cycle in raw_cycles]

    confidence = 1.0
    warnings: list[str] = []
    if cycles:
        warnings.append(f"{len(cycles)} circular dependenc{'y' if len(cycles)==1 else 'ies'} detected")
        confidence -= min(0.30, 0.05 * len(cycles))

    return {
        "graph": graph,
        "cycles": cycles,
        "dark_modules": dark,
        "layer_map": layer_map,
        "_confidence": max(0.5, confidence),
        "_warnings": warnings,
    }


def gde_run_architecture_scorer(ctx: SessionContext) -> dict[str, Any]:
    from genesis_architect_pro.architecture_scorer import append_score_history, score_project

    project_dir = _project_dir(ctx)

    try:
        result = score_project(project_dir)
    except Exception as exc:
        return {"_confidence": 0.4, "_warnings": [f"architecture_scorer failed: {exc}"]}

    # score_project returns a dict: {"total": int, "modularity": float, ...}
    if isinstance(result, dict):
        score = result.get("total", 0)
        label = result.get("profile", "")
        dimensions = {k: result.get(k) for k in ("modularity", "coupling", "cohesion", "layering")}
        # GREEN-zone auto-write (score_history), same category as the import_graph
        # and knowledge_graph caches - an internal trend index, not a user-facing
        # deliverable, so no approval gate. This call was simply missing: the
        # decay/trend forecast a few lines down reads this same file but nothing
        # ever appended to it, so real history could never accumulate.
        try:
            append_score_history(project_dir, result)
        except Exception:
            pass  # history append is advisory; never block the scorer
    else:  # tolerate an object-shaped result from older/newer cores
        score = getattr(result, "score", None) or (result if isinstance(result, (int, float)) else 0)
        label = getattr(result, "label", "")
        dimensions = getattr(result, "dimensions", {})
        if hasattr(dimensions, "__dict__"):
            dimensions = dimensions.__dict__

    warnings: list[str] = []
    if isinstance(score, (int, float)) and score < 40:
        warnings.append(f"Architecture score critical: {score}/100")

    # Load score history for decay forecast
    history: list[dict] = []
    score_history_path = project_dir / ".genesis" / "score_history.jsonl"
    if score_history_path.exists():
        import json as _json
        for line in score_history_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    history.append(_json.loads(line))
                except Exception:
                    pass

    # Run decay forecast if enough history exists
    decay_forecast: dict[str, Any] = {}
    if len(history) >= 3:
        try:
            from genesis_architect_pro.decay_regressor import forecast_from_history
            forecast = forecast_from_history(history)
            if forecast is not None:
                decay_forecast = {
                    "weekly_delta": forecast.weekly_delta,
                    "predicted_score_12w": forecast.predicted_score,
                    "weeks_to_critical": (
                        None if forecast.weeks_to_threshold == float("inf")
                        else round(forecast.weeks_to_threshold, 1)
                    ),
                    "forecast_confidence": forecast.confidence,
                    "summary": forecast.summary,
                }
                if forecast.weekly_delta < -0.5:
                    warnings.append(
                        f"Score declining {forecast.weekly_delta:+.2f} pts/week — "
                        f"projected {forecast.predicted_score:.0f}/100 in 12 weeks"
                    )
        except Exception:
            pass  # decay forecast is advisory; never block the scorer

    return {
        "score": score,
        "score_label": str(label),
        "dimensions": dimensions,
        "history": history,
        "decay_forecast": decay_forecast,
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
    from genesis_architect_pro.fragility_classifier import classify_all, write_fragility_map

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

    map_path = project_dir / "FRAGILITY_MAP.md"
    # GREEN-zone auto-write, per genesis_sync's own zone policy ("fragility map
    # refresh" is documented as an auto-applied action) - write_fragility_map()
    # already existed but was only ever reachable from this module's own CLI
    # main(), never from the GDE, so the map file this classifier is named for
    # was never actually produced by a genesis decide/sync session.
    try:
        write_fragility_map(report, map_path)
    except Exception:
        pass  # map write is advisory; never block the classifier

    return {
        "fragility_map": classifications,
        "fragility_map_path": str(map_path),
        "volatile_count": len(volatile),
        "fragile_count": len(fragile),
        "stable_count": len(stable),
        "_confidence": 1.0,
        "_warnings": warnings,
    }


def gde_run_recovery_report(ctx: SessionContext) -> dict[str, Any]:
    from genesis_architect_pro.recovery_report import generate_report_for_project

    project_dir = _project_dir(ctx)
    rel_path = "PROJECT_RECOVERY_REPORT.md"

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
        "report_path": rel_path,
        "risk_level": str(risk_level),
        "recommendations": [str(r) for r in recs[:10]],
        "_pending_writes": [{
            "operation_id": "recovery_report:doc",
            "description": "Write project recovery report to PROJECT_RECOVERY_REPORT.md",
            "target_path": rel_path,
            "payload": report.to_markdown(),
        }],
        "_confidence": 1.0,
        "_warnings": [],
    }


def gde_run_refactoring_planner(ctx: SessionContext) -> dict[str, Any]:
    from genesis_architect_pro.refactoring_planner import generate_plan, render_refactoring_plan_md

    project_dir = _project_dir(ctx)
    rel_path = "REFACTORING_PLAN.md"

    try:
        plan = generate_plan(project_dir)
    except Exception as exc:
        return {"_confidence": 0.4, "_warnings": [f"refactoring_planner failed: {exc}"]}

    steps = getattr(plan, "steps", []) or []
    tier1 = [s for s in steps if getattr(s, "tier", 0) == 1]
    tier2 = [s for s in steps if getattr(s, "tier", 0) == 2]

    return {
        "plan_path": rel_path,
        "tier1_count": len(tier1),
        "tier2_count": len(tier2),
        "_pending_writes": [{
            "operation_id": "refactoring_planner:doc",
            "description": "Write refactoring plan to REFACTORING_PLAN.md",
            "target_path": rel_path,
            "payload": render_refactoring_plan_md(plan),
        }],
        "_confidence": 1.0,
        "_warnings": [],
    }


def gde_run_c4_generator(ctx: SessionContext) -> dict[str, Any]:
    from genesis_architect_pro.c4_generator import generate_c4_doc

    project_dir = _project_dir(ctx)
    rel_path = str(Path("docs") / "architecture" / "C4_ARCHITECTURE.md")

    try:
        # No output_path -> generate_c4_doc returns content without writing;
        # the actual write is deferred to commit() after user approval.
        content = generate_c4_doc(project_dir)
    except Exception as exc:
        return {"_confidence": 0.4, "_warnings": [f"c4_generator failed: {exc}"]}

    return {
        "doc_path": rel_path,
        "_pending_writes": [{
            "operation_id": "c4_generator:doc",
            "description": "Write C4 architecture diagram to docs/architecture/C4_ARCHITECTURE.md",
            "target_path": rel_path,
            "payload": content,
        }],
        "_confidence": 1.0,
        "_warnings": [],
    }


def gde_run_security_templates(ctx: SessionContext) -> dict[str, Any]:
    from genesis_architect_pro.security_templates import generate_security_docs

    project_dir = _project_dir(ctx)
    sec_dir = Path("docs") / "security"

    try:
        docs = generate_security_docs(project_dir, write=False)
    except Exception as exc:
        return {"_confidence": 0.4, "_warnings": [f"security_templates failed: {exc}"]}

    pending_writes = []
    stride_path = ""
    owasp_path = ""
    secrets_path = ""

    if "STRIDE_ANALYSIS.md" in docs:
        stride_path = str(sec_dir / "STRIDE_ANALYSIS.md")
        pending_writes.append({
            "operation_id": "security_templates:stride",
            "description": "Write STRIDE threat model to docs/security/STRIDE_ANALYSIS.md",
            "target_path": stride_path,
            "payload": docs["STRIDE_ANALYSIS.md"],
        })

    if "OWASP_CHECKLIST.md" in docs:
        owasp_path = str(sec_dir / "OWASP_CHECKLIST.md")
        pending_writes.append({
            "operation_id": "security_templates:owasp",
            "description": "Write OWASP Top 10 checklist to docs/security/OWASP_CHECKLIST.md",
            "target_path": owasp_path,
            "payload": docs["OWASP_CHECKLIST.md"],
        })

    if "SECRETS_SCAN.md" in docs:
        secrets_path = str(sec_dir / "SECRETS_SCAN.md")
        pending_writes.append({
            "operation_id": "security_templates:secrets",
            "description": "Write secrets scan to docs/security/SECRETS_SCAN.md",
            "target_path": secrets_path,
            "payload": docs["SECRETS_SCAN.md"],
        })

    return {
        "stride_path": stride_path,
        "owasp_path": owasp_path,
        "secrets_path": secrets_path,
        "_pending_writes": pending_writes,
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
    tool_name = _instruction(ctx) or project_dir.name

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
    import json as _json

    from genesis_architect_pro.evidence_pack import build_evidence_pack

    project_dir = _project_dir(ctx)
    findings = _output("field_intelligence", ctx).get("findings", [])
    _output("source_registry", ctx).get("registry")

    question = _instruction(ctx) or f"Is {project_dir.name} safe to build on?"
    rel_path = str(Path(".genesis") / "evidence_packs" / "research_session.json")

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
    except Exception as exc:
        return {"_confidence": 0.4, "_warnings": [f"evidence_pack failed: {exc}"],
                "pack_path": "", "item_count": 0}

    return {
        "pack_path": rel_path,
        "item_count": len(items),
        "_pending_writes": [{
            "operation_id": "evidence_pack:research_session",
            "description": f"Write evidence pack to {rel_path}",
            "target_path": rel_path,
            "payload": _json.dumps(pack.to_dict(), indent=2),
        }],
        "_confidence": 1.0,
        "_warnings": [],
    }


# ---------------------------------------------------------------------------
# BUILD mode adapters
# ---------------------------------------------------------------------------


def gde_run_build_scaffold(ctx: SessionContext) -> dict[str, Any]:
    """Invoke the genesis-architect free core to scaffold a new project."""
    project_dir = _project_dir(ctx)
    instruction = _instruction(ctx)

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
    """Run the 5-advisor Committee engine on the codebase analysis context.

    Builds a structured question from upstream engine results, then delegates
    to the Committee engine (5 advisors, anti-sycophancy, transparency profiles).
    Falls back to the legacy perspective aggregation if the Committee engine is
    unavailable or ANTHROPIC_API_KEY is not set.
    """
    import os
    project_dir = _project_dir(ctx)
    warnings: list[str] = []

    # --- Collect upstream engine context ---
    perspectives: list[dict] = []
    for engine_id, label in [
        ("architecture_scorer", "Architecture"),
        ("antipattern_detector", "Anti-Patterns"),
        ("fragility_classifier", "Fragility"),
        ("recovery_report", "Health"),
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

    divergent = _find_divergence(perspectives)

    # --- Try Committee engine (requires ANTHROPIC_API_KEY) ---
    if os.environ.get("ANTHROPIC_API_KEY") and perspectives:
        try:
            from genesis_architect_pro.engines.committee import (
                CommitteeContext,
                CommitteeMode,
                CommitteeRequest,
                TransparencyProfile,
                Urgency,
                run_committee,
            )
            from genesis_architect_pro.engines.committee.journal import append_journal_entry

            engine_summaries = {p["lens"]: p["summary"] for p in perspectives}
            question = (
                f"The codebase '{project_dir.name}' has been analyzed. "
                f"Based on the engine results, what are the most critical issues "
                f"to address, and in what order should they be tackled?"
            )
            if divergent:
                question += (
                    f" Note: the following lenses show divergent signals: {', '.join(divergent)}."
                )

            # Detect license tier from ctx session memory
            license_tier = ctx.session_memory.get("license_tier", "free")
            profile = (
                TransparencyProfile.PRO
                if license_tier == "pro"
                else TransparencyProfile.FREE
            )

            request = CommitteeRequest(
                question=question,
                context=CommitteeContext(
                    engine_outputs=engine_summaries,
                    project_path=str(project_dir),
                ),
                mode=CommitteeMode.ARCHITECTURE,
                urgency=Urgency.NORMAL,
                transparency=profile,
                max_rounds=2,
            )

            committee_result = run_committee(request)

            # Journal entry: this is the Decision Journal, not a disk write
            # gated by approval — it's a permanent record of what the
            # Committee said, independent of whether the user later
            # approves any pending writes.
            try:
                append_journal_entry(
                    request=request,
                    result=committee_result,
                    session_id=ctx.session_id,
                    project_dir=project_dir,
                )
            except Exception:
                pass  # journal failure must never crash the engine

            rel_path = str(Path(".genesis") / "committee_report.md")

            return {
                "perspectives": perspectives,
                "perspective_count": len(perspectives),
                "divergent_lenses": divergent,
                "report_path": rel_path,
                "committee_verdict": committee_result.verdict,
                "committee_confidence": committee_result.confidence,
                "committee_consensus": committee_result.consensus_type.value,
                "_pending_writes": [{
                    "operation_id": "committee_analysis:report",
                    "description": "Write Committee analysis report to .genesis/committee_report.md",
                    "target_path": rel_path,
                    "payload": _render_committee_report(committee_result, perspectives, project_dir.name),
                }],
                "_confidence": committee_result.confidence,
                "_warnings": warnings,
            }

        except Exception as exc:
            warnings.append(f"Committee engine unavailable, falling back: {exc}")

    # --- Legacy fallback: perspective aggregation only ---
    if not perspectives:
        warnings.append("no upstream engine results to consolidate — run analysis engines first")

    report_lines = [f"# Committee Analysis — {project_dir.name}\n"]
    for p in perspectives:
        report_lines.append(f"\n## {p['lens']} Perspective\n{p['summary']}")
    if divergent:
        report_lines.append(f"\n## Divergence\nLenses disagree on: {', '.join(divergent)}")

    rel_path = str(Path(".genesis") / "committee_report.md")

    fallback_confidence = max(0.2, 1.0 - (0.10 * len(divergent)))
    return {
        "perspectives": perspectives,
        "perspective_count": len(perspectives),
        "report_path": rel_path,
        "_pending_writes": [{
            "operation_id": "committee_analysis:report",
            "description": "Write Committee analysis report to .genesis/committee_report.md",
            "target_path": rel_path,
            "payload": "\n".join(report_lines),
        }],
        "divergent_lenses": divergent,
        "_confidence": fallback_confidence,
        "_warnings": warnings,
    }


def _render_committee_report(
    result: Any,
    perspectives: list[dict],
    project_name: str,
) -> str:
    lines = [f"# Committee Analysis — {project_name}\n"]
    lines.append(f"**Verdict:** {result.verdict}\n")
    lines.append(f"**Confidence:** {result.confidence:.0%} | **Consensus:** {result.consensus_type.value.upper()}\n")

    if result.minority_view:
        lines.append(f"\n> **Minority view:** {result.minority_view}\n")

    lines.append("\n## Engine Inputs\n")
    for p in perspectives:
        lines.append(f"- **{p['lens']}:** {p['summary']}")

    if result.advisor_positions:
        lines.append("\n## Advisor Positions\n")
        for pos in result.advisor_positions:
            lines.append(f"### {pos.advisor} (confidence: {pos.confidence:.2f})")
            lines.append(f"{pos.stance}\n")

    if result.manufactured_warning:
        lines.append(f"\n> ⚠️ {result.manufactured_warning}\n")

    return "\n".join(lines)


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


# ---------------------------------------------------------------------------
# GATE mode — rules_engine adapter
# ---------------------------------------------------------------------------


def gde_run_rules_engine(ctx: SessionContext) -> dict[str, Any]:
    """Run the architecture regression gate against .genesis/rules.json.

    Reads the rules file, gathers facts from already-produced engine outputs
    (score, anti-patterns, recovery risk) and evaluates every defined rule.
    Returns PASS or FAIL with per-rule details.  Read-only — never mutates
    project state.
    """
    from genesis_architect_pro.rules_engine import run_check, format_report

    project_dir = _project_dir(ctx)
    warnings: list[str] = []

    try:
        report = run_check(project_dir)
    except Exception as exc:
        return {
            "_confidence": 0.3,
            "_warnings": [f"rules_engine failed: {exc}"],
            "rules_passed": False,
            "rules_file": "",
            "rule_count": 0,
            "failed_rules": [],
            "rules_report": "",
        }

    if not report.rules_file:
        warnings.append("no .genesis/rules.json found — gate is open (no rules to enforce)")

    failed = [r for r in report.results if not r.passed]
    if failed:
        warnings.extend([f"FAIL [{r.rule}]: {r.message}" for r in failed])

    return {
        "rules_passed": report.passed,
        "rules_file": report.rules_file,
        "rule_count": len(report.results),
        "failed_rules": [r.rule for r in failed],
        "rules_report": format_report(report),
        "_confidence": 1.0,
        "_warnings": warnings,
    }


# ---------------------------------------------------------------------------
# GATE / RECOVERY mode — git_analyzer adapter
# ---------------------------------------------------------------------------


def gde_run_git_analyzer(ctx: SessionContext) -> dict[str, Any]:
    """Analyze git history to classify module churn and bus factor.

    Enriches fragility data with commit frequency, fix-ratio, and staleness.
    Gracefully degrades when the project has no git history.
    """
    from genesis_architect_pro.git_analyzer import per_module_churn

    project_dir = _project_dir(ctx)
    warnings: list[str] = []

    try:
        churn = per_module_churn(project_dir, days=90)
    except Exception as exc:
        return {
            "_confidence": 0.3,
            "_warnings": [f"git_analyzer failed: {exc}"],
            "churn_map": {},
            "high_churn_count": 0,
            "stale_count": 0,
            "bus_factor_1_count": 0,
        }

    if not churn:
        warnings.append("no git history found — churn data unavailable")
        return {
            "churn_map": {},
            "high_churn_count": 0,
            "stale_count": 0,
            "bus_factor_1_count": 0,
            "_confidence": 0.5,
            "_warnings": warnings,
        }

    high = [f for f, d in churn.items() if d.get("churn_level") == "HIGH"]
    stale = [f for f, d in churn.items() if d.get("churn_level") == "STALE"]
    bus1 = [f for f, d in churn.items() if d.get("bus_factor", 2) <= 1]

    if high:
        warnings.append(f"{len(high)} high-churn module(s) — elevated regression risk")
    if bus1:
        warnings.append(f"{len(bus1)} module(s) with bus factor 1 — single point of knowledge")

    return {
        "churn_map": churn,
        "high_churn_count": len(high),
        "stale_count": len(stale),
        "bus_factor_1_count": len(bus1),
        "_confidence": 1.0,
        "_warnings": warnings,
    }


# ---------------------------------------------------------------------------
# GATE mode — import_audit adapter
# ---------------------------------------------------------------------------


def gde_run_import_audit(ctx: SessionContext) -> dict[str, Any]:
    """Audit declared (model) vs actual (code) import edges — catches 'the diagram lies'.

    Reads the committed model from .genesis/ and compares its declared links
    against the real import graph.  Returns CONSISTENT or INCONSISTENT with
    per-finding details.  Read-only — never mutates project state.
    """
    from genesis_architect_pro.import_audit import audit, format_report

    project_dir = _project_dir(ctx)
    warnings: list[str] = []

    try:
        report = audit(project_dir)
    except Exception as exc:
        return {
            "_confidence": 0.3,
            "_warnings": [f"import_audit failed: {exc}"],
            "audit_consistent": None,
            "declared_links": 0,
            "actual_edges": 0,
            "missing_count": 0,
            "undeclared_count": 0,
            "audit_notes": [],
        }

    if report.notes:
        warnings.extend(report.notes)

    if not report.consistent:
        warnings.append(
            f"import audit INCONSISTENT: "
            f"{len(report.missing_imports)} missing, "
            f"{len(report.undeclared_imports)} undeclared"
        )

    return {
        "audit_consistent": report.consistent,
        "declared_links": report.declared_links,
        "actual_edges": report.actual_edges,
        "missing_count": len(report.missing_imports),
        "undeclared_count": len(report.undeclared_imports),
        "audit_report": format_report(report),
        "audit_notes": report.notes,
        "_confidence": 1.0 if report.declared_links > 0 else 0.6,
        "_warnings": warnings,
    }
