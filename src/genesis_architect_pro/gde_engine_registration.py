"""Genesis Decision Engine — engine registration.

Registers all 8 production engines as EngineDescriptors in the default
GDE registry. Import this module once at startup to make the engines
available to GenesisDecisionEngine.run().

Each adapter function (gde_run_*) wraps the engine's native API into
the GDE contract: accepts SessionContext, returns dict with optional
_confidence and _warnings keys.

Usage::

    import genesis_architect_pro.gde_engine_registration  # registers all engines
    from genesis_architect_pro import GenesisDecisionEngine

    gde = GenesisDecisionEngine(project_dir=Path("."))
    report = gde.run("diagnose the project and identify drift")
"""

from __future__ import annotations

from genesis_architect_pro.gde_types import EngineCategory, EngineDescriptor, GDEMode

# ---------------------------------------------------------------------------
# Adapter module — all adapter functions live in gde_engine_adapters.py
# (imported by the runner via descriptor.module / descriptor.entry_point)
# ---------------------------------------------------------------------------

_ADAPTER_MODULE = "genesis_architect_pro.gde_engine_adapters"

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
        output_keys=["stride_path", "owasp_path"],
        requires=[],
        is_optional=True,
        write_operations=["stride_md", "owasp_md"],
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
        is_optional=True,
        write_operations=[],
        timeout_seconds=10,
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
        requires=["source_registry"],
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
        is_optional=True,
        write_operations=["committee_report_md"],
        timeout_seconds=30,
        modes=[GDEMode.COMMITTEE],
    ),
]

# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def _register_all() -> None:
    from genesis_architect_pro.engine_registry import get_default_registry
    reg = get_default_registry()
    for desc in _DESCRIPTORS:
        if desc.id not in reg:
            reg.register(desc)

    # Register the knowledge graph engine additively (kept in its own module
    # so it doesn't pollute the core 8-engine set for legacy callers).
    try:
        from genesis_architect_pro.gde_knowledge_graph_adapter import register_knowledge_graph
        register_knowledge_graph()
    except Exception:
        pass  # graceful degradation: knowledge graph is optional


_register_all()
