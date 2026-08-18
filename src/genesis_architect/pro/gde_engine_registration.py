"""Genesis Decision Engine — engine registration.

Registers all 8 production engines as EngineDescriptors in the default
GDE registry. Import this module once at startup to make the engines
available to GenesisDecisionEngine.run().

Each adapter function (gde_run_*) wraps the engine's native API into
the GDE contract: accepts SessionContext, returns dict with optional
_confidence and _warnings keys.

Usage::

    import genesis_architect.pro.gde_engine_registration  # registers all engines
    from genesis_architect.pro import GenesisDecisionEngine

    gde = GenesisDecisionEngine(project_dir=Path("."))
    report = gde.run("diagnose the project and identify drift")
"""

from __future__ import annotations

from genesis_architect.pro.gde_types import EngineCategory, EngineDescriptor, GDEMode

# ---------------------------------------------------------------------------
# Adapter module — all adapter functions live in gde_engine_adapters.py
# (imported by the runner via descriptor.module / descriptor.entry_point)
# ---------------------------------------------------------------------------

_ADAPTER_MODULE = "genesis_architect.pro.gde_engine_adapters"

# ---------------------------------------------------------------------------
# Descriptor definitions
# ---------------------------------------------------------------------------

_DESCRIPTORS: list[EngineDescriptor] = [
    # 1. Import Graph — foundation; everything else depends on it
    EngineDescriptor(
        id="import_graph",
        name="Import Graph",
        module=_ADAPTER_MODULE,
        entry_point="gde_run_import_graph",
        category=EngineCategory.ANALYSIS,
        input_keys=["project_dir"],
        output_keys=["graph", "cycles", "dark_modules", "layer_map"],
        requires=[],
        handoffs=["architecture_scorer", "antipattern_detector"],
        failure_modes=[
            "A language the parser does not cover yields an empty graph that "
            "looks like a clean, dependency-free project rather than an "
            "unparsed one.",
            "Dynamic imports are invisible, so a real edge can be missing "
            "without any indication that it was missed.",
        ],
        is_optional=False,
        write_operations=[],
        timeout_seconds=60,
        modes=[GDEMode.RECOVERY, GDEMode.REFACTOR, GDEMode.GATE, GDEMode.DOCUMENT, GDEMode.COMMITTEE],
    ),

    # 2. Architecture Scorer — requires import graph
    EngineDescriptor(
        id="architecture_scorer",
        name="Architecture Scorer",
        module=_ADAPTER_MODULE,
        entry_point="gde_run_architecture_scorer",
        category=EngineCategory.ANALYSIS,
        input_keys=["project_dir", "graph"],
        output_keys=["score", "score_label", "dimensions", "history"],
        requires=["import_graph"],
        handoffs=["antipattern_detector", "refactoring_planner"],
        failure_modes=[
            "Scoring a near-empty graph produces a high score, because few "
            "modules means few violations — absence of findings is not health.",
            "The adaptive profile is inferred; a mis-detected profile scores "
            "the project against the wrong expectations without saying so.",
        ],
        is_optional=True,
        write_operations=["score_history"],
        timeout_seconds=30,
        modes=[GDEMode.RECOVERY, GDEMode.REFACTOR, GDEMode.GATE, GDEMode.COMMITTEE],
    ),

    # 3. Anti-Pattern Detector — requires import graph
    EngineDescriptor(
        id="antipattern_detector",
        name="Anti-Pattern Detector",
        module=_ADAPTER_MODULE,
        entry_point="gde_run_antipattern_detector",
        category=EngineCategory.ANALYSIS,
        input_keys=["project_dir", "graph"],
        output_keys=["patterns", "critical_count", "high_count"],
        requires=["import_graph"],
        handoffs=["fragility_classifier", "refactoring_planner"],
        failure_modes=[
            "Thresholds are structural, not contextual: a deliberate facade or "
            "a generated file can be reported as a god class or hub file.",
            "Zero detections on an unparsed graph reads identically to zero "
            "detections on a genuinely clean one.",
        ],
        is_optional=True,
        write_operations=[],
        timeout_seconds=30,
        modes=[GDEMode.RECOVERY, GDEMode.REFACTOR, GDEMode.GATE, GDEMode.COMMITTEE],
    ),

    # 4. Fragility Classifier — requires both scorer and antipattern
    EngineDescriptor(
        id="fragility_classifier",
        name="Fragility Classifier",
        module=_ADAPTER_MODULE,
        entry_point="gde_run_fragility_classifier",
        category=EngineCategory.ANALYSIS,
        input_keys=["project_dir", "patterns", "score"],
        output_keys=["fragility_map", "volatile_count", "fragile_count", "stable_count"],
        requires=["antipattern_detector", "architecture_scorer"],
        handoffs=["recovery_report", "refactoring_planner"],
        is_optional=True,
        write_operations=["fragility_map_md"],
        timeout_seconds=45,
        modes=[GDEMode.RECOVERY, GDEMode.REFACTOR, GDEMode.GATE, GDEMode.COMMITTEE],
    ),

    # 5. Recovery Report — final RECOVERY output; requires all analysis
    EngineDescriptor(
        id="recovery_report",
        name="Recovery Report",
        module=_ADAPTER_MODULE,
        entry_point="gde_run_recovery_report",
        category=EngineCategory.REPORT,
        input_keys=["project_dir", "score", "fragility_map", "patterns"],
        output_keys=["report_path", "risk_level", "recommendations"],
        requires=["fragility_classifier"],
        # Diagnosis hands off to the plan that acts on it. That plan hands back
        # here to re-measure — a legitimate loop, and exactly why handoffs are
        # exempt from cycle detection.
        handoffs=["refactoring_planner", "committee_analysis"],
        is_optional=True,
        write_operations=["recovery_report_md"],
        timeout_seconds=30,
        modes=[GDEMode.RECOVERY],
    ),

    # 6. Refactoring Planner — REFACTOR mode output
    EngineDescriptor(
        id="refactoring_planner",
        name="Refactoring Planner",
        module=_ADAPTER_MODULE,
        entry_point="gde_run_refactoring_planner",
        category=EngineCategory.REPORT,
        input_keys=["project_dir", "patterns", "score"],
        output_keys=["plan_path", "tier1_count", "tier2_count"],
        requires=["antipattern_detector", "architecture_scorer"],
        handoffs=["rules_engine", "recovery_report"],
        is_optional=True,
        write_operations=["refactoring_plan_md"],
        timeout_seconds=30,
        modes=[GDEMode.REFACTOR],
    ),

    # 7. C4 Generator — DOCUMENT mode
    EngineDescriptor(
        id="c4_generator",
        name="C4 Architecture Generator",
        module=_ADAPTER_MODULE,
        entry_point="gde_run_c4_generator",
        category=EngineCategory.REPORT,
        input_keys=["project_dir"],
        output_keys=["doc_path"],
        requires=["import_graph"],
        handoffs=["security_templates"],
        is_optional=True,
        write_operations=["c4_architecture_md"],
        timeout_seconds=30,
        modes=[GDEMode.DOCUMENT],
    ),

    # 8. Security Templates — GATE / DOCUMENT mode
    EngineDescriptor(
        id="security_templates",
        name="Security Templates",
        module=_ADAPTER_MODULE,
        entry_point="gde_run_security_templates",
        category=EngineCategory.REPORT,
        input_keys=["project_dir"],
        output_keys=["stride_path", "owasp_path", "secrets_path"],
        requires=[],
        handoffs=["rules_engine"],
        is_optional=True,
        write_operations=["stride_md", "owasp_md", "secrets_scan_md"],
        timeout_seconds=30,
        modes=[GDEMode.GATE, GDEMode.DOCUMENT],
    ),

    # --- RESEARCH mode ---

    # 9. Source Registry — load research source catalog
    EngineDescriptor(
        id="source_registry",
        name="Source Registry",
        module=_ADAPTER_MODULE,
        entry_point="gde_run_source_registry",
        category=EngineCategory.ANALYSIS,
        input_keys=["project_dir"],
        output_keys=["registry", "source_count"],
        requires=[],
        handoffs=["field_intelligence"],
        is_optional=True,
        write_operations=[],
        timeout_seconds=10,
        modes=[GDEMode.RESEARCH],
    ),

    # 19. Research Outline — items x fields grid, if one has been confirmed
    EngineDescriptor(
        id="research_outline",
        name="Research Outline",
        module=_ADAPTER_MODULE,
        entry_point="gde_run_research_outline",
        category=EngineCategory.ANALYSIS,
        input_keys=["project_dir"],
        output_keys=["topic", "items", "fields"],
        requires=[],
        handoffs=["field_intelligence"],
        is_optional=True,
        write_operations=[],
        timeout_seconds=5,
        modes=[GDEMode.RESEARCH],
    ),

    # 10. Field Intelligence — Reddit Answers developer sentiment
    EngineDescriptor(
        id="field_intelligence",
        name="Field Intelligence",
        module=_ADAPTER_MODULE,
        entry_point="gde_run_field_intelligence",
        category=EngineCategory.ANALYSIS,
        input_keys=["project_dir", "instruction"],
        output_keys=["findings", "verified_count", "queries"],
        requires=["source_registry", "research_outline"],
        handoffs=["evidence_pack"],
        failure_modes=[
            "Offline or with a dead API key it returns nothing, which is not "
            "the same as having found no community signal.",
            "Community sentiment is self-selected toward complaint; volume of "
            "pain is not proportional to prevalence of pain.",
        ],
        is_optional=True,
        write_operations=[],
        timeout_seconds=60,
        modes=[GDEMode.RESEARCH],
    ),

    # 11. Evidence Pack — consolidate findings into a structured evidence pack
    EngineDescriptor(
        id="evidence_pack",
        name="Evidence Pack",
        module=_ADAPTER_MODULE,
        entry_point="gde_run_evidence_pack",
        category=EngineCategory.REPORT,
        input_keys=["project_dir", "findings", "registry"],
        output_keys=["pack_path", "item_count"],
        requires=["field_intelligence"],
        handoffs=["committee_analysis"],
        is_optional=True,
        write_operations=["evidence_pack_json"],
        timeout_seconds=15,
        modes=[GDEMode.RESEARCH],
    ),

    # --- BUILD mode ---

    # 12. Build Scaffold — invoke genesis-architect free core scaffolder
    EngineDescriptor(
        id="build_scaffold",
        name="Build Scaffold",
        module=_ADAPTER_MODULE,
        entry_point="gde_run_build_scaffold",
        category=EngineCategory.REPORT,
        input_keys=["project_dir", "instruction"],
        output_keys=["scaffold_path", "vision"],
        requires=[],
        # Freshly scaffolded code is worth analysing — a cross-mode handoff
        # (BUILD suggests RECOVERY's entry engine).
        handoffs=["import_graph"],
        is_optional=False,
        write_operations=["project_scaffold"],
        timeout_seconds=120,
        modes=[GDEMode.BUILD],
    ),

    # --- GATE mode (additional engines) ---

    # 14. Rules Engine — architecture regression gate against .genesis/rules.json
    EngineDescriptor(
        id="rules_engine",
        name="Rules Engine",
        module=_ADAPTER_MODULE,
        entry_point="gde_run_rules_engine",
        category=EngineCategory.ANALYSIS,
        input_keys=["project_dir"],
        output_keys=["rules_passed", "rules_file", "rule_count", "failed_rules"],
        requires=["architecture_scorer", "antipattern_detector"],
        handoffs=["recovery_report"],
        failure_modes=[
            "With no rules file present it passes trivially — a green gate can "
            "mean 'nothing was checked', not 'everything held'.",
        ],
        is_optional=True,
        write_operations=[],
        timeout_seconds=30,
        modes=[GDEMode.GATE],
    ),

    # 15. Git Churn Analyzer — per-module churn, fix-ratio, bus factor from git history
    EngineDescriptor(
        id="git_analyzer",
        name="Git Churn Analyzer",
        module=_ADAPTER_MODULE,
        entry_point="gde_run_git_analyzer",
        category=EngineCategory.ANALYSIS,
        input_keys=["project_dir"],
        output_keys=["churn_map", "high_churn_count", "stale_count", "bus_factor_1_count"],
        requires=["import_graph"],
        handoffs=["fragility_classifier"],
        failure_modes=[
            "A shallow clone or a freshly-imported repository has almost no "
            "history, so everything looks stable and low-churn.",
            "Bulk reformatting or a migration commit inflates churn for files "
            "nobody actually changed in substance.",
        ],
        is_optional=True,
        write_operations=[],
        timeout_seconds=60,
        modes=[GDEMode.RECOVERY, GDEMode.REFACTOR, GDEMode.GATE],
    ),

    # 16. Import Audit — declared (model) vs actual (code) import edges
    EngineDescriptor(
        id="import_audit",
        name="Import Audit",
        module=_ADAPTER_MODULE,
        entry_point="gde_run_import_audit",
        category=EngineCategory.ANALYSIS,
        input_keys=["project_dir"],
        output_keys=["audit_consistent", "declared_links", "actual_edges",
                     "missing_count", "undeclared_count"],
        requires=["import_graph"],
        # An audit that found the diagram lying hands off to regenerating it.
        handoffs=["c4_generator"],
        is_optional=True,
        write_operations=[],
        timeout_seconds=30,
        modes=[GDEMode.GATE],
    ),

    # --- COMMITTEE mode ---

    # 17. Committee Analysis — multi-perspective synthesis (runs after analysis engines)
    EngineDescriptor(
        id="committee_analysis",
        name="Committee Analysis",
        module=_ADAPTER_MODULE,
        entry_point="gde_run_committee_analysis",
        category=EngineCategory.REPORT,
        input_keys=["project_dir"],
        output_keys=["perspectives", "perspective_count", "divergent_lenses", "report_path"],
        requires=["fragility_classifier"],
        handoffs=["recovery_report"],
        is_optional=True,
        write_operations=["committee_report_md"],
        timeout_seconds=30,
        modes=[GDEMode.COMMITTEE],
    ),

    # 18. Red-Team Self-Critique — attacks the session's own plan before approval.
    # `requires` spans every mode's write-producing engine(s) on purpose: a
    # dependency ID not present in a given mode's engine subset is silently
    # ignored for that mode's ordering (EngineRegistry.parallel_groups_for_mode),
    # so this single descriptor safely runs last in every mode it's registered
    # for without needing a separate descriptor per mode.
    EngineDescriptor(
        id="red_team_critic",
        name="Red-Team Self-Critique",
        module=_ADAPTER_MODULE,
        entry_point="gde_run_red_team_critic",
        category=EngineCategory.GATE,
        input_keys=["pending_write_operations", "engine_results", "overall_confidence"],
        output_keys=["findings", "critical_findings", "finding_count"],
        requires=[
            "recovery_report", "refactoring_planner", "evidence_pack",
            "build_scaffold", "c4_generator", "committee_analysis",
            "fragility_classifier", "security_templates",
        ],
        # Deliberately terminal. The red-team critique is the last thing to run
        # before APPROVE; suggesting a "next engine" from here would invite
        # continuing past the very gate that just fired.
        handoffs=[],
        is_optional=True,
        write_operations=[],
        timeout_seconds=45,
        modes=[GDEMode.RECOVERY, GDEMode.RESEARCH, GDEMode.REFACTOR, GDEMode.GATE,
               GDEMode.BUILD, GDEMode.DOCUMENT, GDEMode.COMMITTEE],
    ),
]

# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def _register_all() -> None:
    from genesis_architect.pro.engine_registry import get_default_registry
    reg = get_default_registry()
    for desc in _DESCRIPTORS:
        if desc.id not in reg:
            reg.register(desc)

    # Register the knowledge graph engine additively (kept in its own module
    # so it doesn't pollute the core 8-engine set for legacy callers).
    try:
        from genesis_architect.pro.gde_knowledge_graph_adapter import register_knowledge_graph
        register_knowledge_graph()
    except Exception:
        pass  # graceful degradation: knowledge graph is optional


_register_all()
