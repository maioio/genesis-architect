"""Genesis Architect - the intelligence layer.

Multi-source research orchestration, pitfall ranking, video-to-pitfall
extraction, cross-session memory, package-registry validation,
recovery diagnosis, and deep codebase analysis.

These engines were formerly the paid "Pro" tier. They are now free and open
source (AGPL-3.0) and ship in the box - there is no license key and nothing
is gated.
"""

__version__ = "9.0.0"

# ---------------------------------------------------------------------------
# Lazy public API (PEP 562)
# ---------------------------------------------------------------------------
#
# This package used to re-export its public API by importing all 43 modules at
# package-import time. Two costs came with that. Importing anything from
# `genesis_architect.pro` pulled in the entire subpackage - every engine,
# scanner and adapter - however little of it the caller wanted. And it gave
# this facade an edge to everything in the dependency graph, which is how it
# ended up inside import cycles that had nothing to do with it.
#
# Names now resolve on first attribute access. The public API is unchanged:
# `from genesis_architect.pro import GenesisDecisionEngine` returns the same
# object, and now imports decision_engine and nothing else.
#
# Deliberately NOT guarded behind `if TYPE_CHECKING:` with the old eager
# imports, which was tried first. A type-checking branch preserves static
# resolution but the import graph still counts every line in it, so the facade
# stays a 43-edge node and the change buys nothing structurally. A `.pyi` stub
# was measured too and is counted the same way. Neither costs anything to skip
# here: this distribution ships no `py.typed` marker, so under PEP 561 type
# checkers already treat this package as untyped and resolve none of these
# names today. Making it a typed distribution is a separate decision, and the
# right place for it is a py.typed marker rather than an import block kept
# alive to fool a dependency scanner.
#
# Both tables are generated from the import block they replaced, so they are
# exhaustive by construction rather than by maintenance - and a test asserts
# every name in __all__ actually resolves.

_LAZY_EXPORTS: dict[str, str] = {
    # antipattern_detector
    "detect_all": "genesis_architect.pro.antipattern_detector",
    # architecture_scorer
    "score_label": "genesis_architect.pro.architecture_scorer",
    "score_project": "genesis_architect.pro.architecture_scorer",
    # c4_generator
    "generate_c4_doc": "genesis_architect.pro.c4_generator",
    # companion_ui
    "COMPANION_UI_PORT": "genesis_architect.pro.companion_ui",
    "render_companion_html": "genesis_architect.pro.companion_ui",
    "write_companion_html": "genesis_architect.pro.companion_ui",
    # cross_session_memory
    "list_analyzed_videos": "genesis_architect.pro.cross_session_memory",
    "restore_session": "genesis_architect.pro.cross_session_memory",
    "save_phase2": "genesis_architect.pro.cross_session_memory",
    "save_phase4": "genesis_architect.pro.cross_session_memory",
    "save_phase6": "genesis_architect.pro.cross_session_memory",
    "save_video_pitfalls": "genesis_architect.pro.cross_session_memory",
    # decay_regressor
    "DecayForecast": "genesis_architect.pro.decay_regressor",
    "DecayRegressor": "genesis_architect.pro.decay_regressor",
    "DecayRegressorConfig": "genesis_architect.pro.decay_regressor",
    "RegressionResult": "genesis_architect.pro.decay_regressor",
    "ScoreDataPoint": "genesis_architect.pro.decay_regressor",
    "ScorePrediction": "genesis_architect.pro.decay_regressor",
    "forecast_from_history": "genesis_architect.pro.decay_regressor",
    # decision_engine
    "GenesisDecisionEngine": "genesis_architect.pro.decision_engine",
    "run_session": "genesis_architect.pro.decision_engine",
    # dependency_index
    "AffectedScope": "genesis_architect.pro.dependency_index",
    "DependencyIndex": "genesis_architect.pro.dependency_index",
    "build_dependency_index": "genesis_architect.pro.dependency_index",
    "compute_affected_scope": "genesis_architect.pro.dependency_index",
    # drift_detector
    "DriftFlags": "genesis_architect.pro.drift_detector",
    "StaleCandidate": "genesis_architect.pro.drift_detector",
    "VagrantCandidate": "genesis_architect.pro.drift_detector",
    "compute_drift_flags": "genesis_architect.pro.drift_detector",
    "detect_drift": "genesis_architect.pro.drift_detector",
    # drift_scorer
    "DriftScore": "genesis_architect.pro.drift_scorer",
    "DriftScorerConfig": "genesis_architect.pro.drift_scorer",
    "NodeDriftScore": "genesis_architect.pro.drift_scorer",
    "compute_drift_score": "genesis_architect.pro.drift_scorer",
    "score_drift": "genesis_architect.pro.drift_scorer",
    # engine_registry
    "EngineRegistry": "genesis_architect.pro.engine_registry",
    "RegistryError": "genesis_architect.pro.engine_registry",
    "get_default_registry": "genesis_architect.pro.engine_registry",
    "register": "genesis_architect.pro.engine_registry",
    # ephemeral_purge
    "ProtectedItem": "genesis_architect.pro.ephemeral_purge",
    "PurgeCandidate": "genesis_architect.pro.ephemeral_purge",
    "PurgeReport": "genesis_architect.pro.ephemeral_purge",
    "hygiene_notice": "genesis_architect.pro.ephemeral_purge",
    "mark_ephemeral": "genesis_architect.pro.ephemeral_purge",
    "purge": "genesis_architect.pro.ephemeral_purge",
    # evidence_pack
    "EvidenceItem": "genesis_architect.pro.evidence_pack",
    "EvidencePack": "genesis_architect.pro.evidence_pack",
    "build_evidence_pack": "genesis_architect.pro.evidence_pack",
    "save_evidence_pack": "genesis_architect.pro.evidence_pack",
    # field_intelligence
    "FieldFinding": "genesis_architect.pro.field_intelligence",
    "FieldReport": "genesis_architect.pro.field_intelligence",
    "REDDIT_ANSWERS_TEMPLATES": "genesis_architect.pro.field_intelligence",
    "build_reddit_answers_queries": "genesis_architect.pro.field_intelligence",
    "run_field_workflow": "genesis_architect.pro.field_intelligence",
    "verify_finding": "genesis_architect.pro.field_intelligence",
    # first_run
    "CUSTOMER_FLOW": "genesis_architect.pro.first_run",
    "Check": "genesis_architect.pro.first_run",
    "Readiness": "genesis_architect.pro.first_run",
    "check_readiness": "genesis_architect.pro.first_run",
    "doctor_report": "genesis_architect.pro.first_run",
    "ensure_optional_dep": "genesis_architect.pro.first_run",
    "offline_capability_report": "genesis_architect.pro.first_run",
    # fragility_classifier
    "classify_all": "genesis_architect.pro.fragility_classifier",
    # gde_companion
    "CompanionInstrumentation": "genesis_architect.pro.gde_companion",
    "GateMissStats": "genesis_architect.pro.gde_companion",
    "GateNotifier": "genesis_architect.pro.gde_companion",
    "HealthPageServer": "genesis_architect.pro.gde_companion",
    # gde_gate_engine
    "evaluate_gates": "genesis_architect.pro.gde_gate_engine",
    # gde_knowledge_graph_adapter
    "KNOWLEDGE_GRAPH_DESCRIPTOR": "genesis_architect.pro.gde_knowledge_graph_adapter",
    "gde_run_knowledge_graph": "genesis_architect.pro.gde_knowledge_graph_adapter",
    "register_knowledge_graph": "genesis_architect.pro.gde_knowledge_graph_adapter",
    # gde_planner
    "build_plan": "genesis_architect.pro.gde_planner",
    # gde_runner
    "run_plan": "genesis_architect.pro.gde_runner",
    # gde_session
    "append_decision_log": "genesis_architect.pro.gde_session",
    "delete_session": "genesis_architect.pro.gde_session",
    "load_session": "genesis_architect.pro.gde_session",
    "read_decision_log": "genesis_architect.pro.gde_session",
    "save_session": "genesis_architect.pro.gde_session",
    "session_file_exists": "genesis_architect.pro.gde_session",
    # gde_types
    "ApprovalChoice": "genesis_architect.pro.gde_types",
    "ApprovalDecision": "genesis_architect.pro.gde_types",
    "ApprovalRequest": "genesis_architect.pro.gde_types",
    "CommitResult": "genesis_architect.pro.gde_types",
    "DecisionEntry": "genesis_architect.pro.gde_types",
    "EngineCategory": "genesis_architect.pro.gde_types",
    "EngineDescriptor": "genesis_architect.pro.gde_types",
    "EngineResult": "genesis_architect.pro.gde_types",
    "EngineStatus": "genesis_architect.pro.gde_types",
    "ExecutionPlan": "genesis_architect.pro.gde_types",
    "GDEMode": "genesis_architect.pro.gde_types",
    "GateAction": "genesis_architect.pro.gde_types",
    "GateOutcome": "genesis_architect.pro.gde_types",
    "GateReport": "genesis_architect.pro.gde_types",
    "GateResult": "genesis_architect.pro.gde_types",
    "Intent": "genesis_architect.pro.gde_types",
    "LifecycleStage": "genesis_architect.pro.gde_types",
    "SessionContext": "genesis_architect.pro.gde_types",
    "SessionReport": "genesis_architect.pro.gde_types",
    "WriteOperation": "genesis_architect.pro.gde_types",
    # git_analyzer
    "WeeklySnapshot": "genesis_architect.pro.git_analyzer",
    "build_timeline": "genesis_architect.pro.git_analyzer",
    "per_module_churn": "genesis_architect.pro.git_analyzer",
    "render_sparkline": "genesis_architect.pro.git_analyzer",
    # import_audit
    "AuditFinding": "genesis_architect.pro.import_audit",
    "ImportAuditReport": "genesis_architect.pro.import_audit",
    "audit_imports": "genesis_architect.pro.import_audit",
    "format_audit_report": "genesis_architect.pro.import_audit",
    # import_graph
    "build_graph": "genesis_architect.pro.import_graph",
    "load_or_build": "genesis_architect.pro.import_graph",
    # intent_classifier
    "classify": "genesis_architect.pro.intent_classifier",
    # knowledge_graph
    "Edge": "genesis_architect.pro.knowledge_graph",
    "KnowledgeGraph": "genesis_architect.pro.knowledge_graph",
    "NODE_TYPES": "genesis_architect.pro.knowledge_graph",
    "Node": "genesis_architect.pro.knowledge_graph",
    "REL_TYPES": "genesis_architect.pro.knowledge_graph",
    "build_from_project": "genesis_architect.pro.knowledge_graph",
    "load_graph": "genesis_architect.pro.knowledge_graph",
    "save_graph": "genesis_architect.pro.knowledge_graph",
    # learning_engine
    "KNOWN_PROFILES": "genesis_architect.pro.learning_engine",
    "LearningRecommendation": "genesis_architect.pro.learning_engine",
    "Outcome": "genesis_architect.pro.learning_engine",
    "ProfileStat": "genesis_architect.pro.learning_engine",
    "rank_profiles": "genesis_architect.pro.learning_engine",
    "read_outcomes": "genesis_architect.pro.learning_engine",
    "recommend_profile": "genesis_architect.pro.learning_engine",
    "record_outcome": "genesis_architect.pro.learning_engine",
    "summarize_lessons": "genesis_architect.pro.learning_engine",
    "write_lessons": "genesis_architect.pro.learning_engine",
    # mcp_advisor
    "AdvisorReport": "genesis_architect.pro.mcp_advisor",
    "CATALOG": "genesis_architect.pro.mcp_advisor",
    "ProjectSignals": "genesis_architect.pro.mcp_advisor",
    "ToolRecommendation": "genesis_architect.pro.mcp_advisor",
    "ToolSpec": "genesis_architect.pro.mcp_advisor",
    "advise": "genesis_architect.pro.mcp_advisor",
    "advise_global": "genesis_architect.pro.mcp_advisor",
    "advise_local": "genesis_architect.pro.mcp_advisor",
    "detect_signals": "genesis_architect.pro.mcp_advisor",
    # memory_engine
    "DecisionJournalEntry": "genesis_architect.pro.memory_engine",
    "MEMORY_FILES": "genesis_architect.pro.memory_engine",
    "init_memory": "genesis_architect.pro.memory_engine",
    "memory_status": "genesis_architect.pro.memory_engine",
    "read_memory": "genesis_architect.pro.memory_engine",
    "record_adr": "genesis_architect.pro.memory_engine",
    "record_decision": "genesis_architect.pro.memory_engine",
    "record_lesson": "genesis_architect.pro.memory_engine",
    "record_research": "genesis_architect.pro.memory_engine",
    "record_risk": "genesis_architect.pro.memory_engine",
    "set_project_memory": "genesis_architect.pro.memory_engine",
    # model_store
    "ArchModel": "genesis_architect.pro.model_store",
    "LinkChange": "genesis_architect.pro.model_store",
    "ModelDiff": "genesis_architect.pro.model_store",
    "ModelGroup": "genesis_architect.pro.model_store",
    "ModelLink": "genesis_architect.pro.model_store",
    "ModelNode": "genesis_architect.pro.model_store",
    "ModelResponsibility": "genesis_architect.pro.model_store",
    "ModelStore": "genesis_architect.pro.model_store",
    "NodeChange": "genesis_architect.pro.model_store",
    "ResponsibilityChange": "genesis_architect.pro.model_store",
    # product_intelligence
    "CONSENT_PROMPT": "genesis_architect.pro.product_intelligence",
    "TelemetryConfig": "genesis_architect.pro.product_intelligence",
    "clear_events": "genesis_architect.pro.product_intelligence",
    "describe_payload": "genesis_architect.pro.product_intelligence",
    "is_enabled": "genesis_architect.pro.product_intelligence",
    "needs_consent_prompt": "genesis_architect.pro.product_intelligence",
    "read_events": "genesis_architect.pro.product_intelligence",
    "record_event": "genesis_architect.pro.product_intelligence",
    "revoke_consent": "genesis_architect.pro.product_intelligence",
    "set_consent": "genesis_architect.pro.product_intelligence",
    # progress_report
    "PhaseReport": "genesis_architect.pro.progress_report",
    "ReportItem": "genesis_architect.pro.progress_report",
    "render_report": "genesis_architect.pro.progress_report",
    "write_report": "genesis_architect.pro.progress_report",
    # recovery_report
    "ArchitectureHealth": "genesis_architect.pro.recovery_report",
    "DriftSummary": "genesis_architect.pro.recovery_report",
    "Recommendation": "genesis_architect.pro.recovery_report",
    "RecoveryReport": "genesis_architect.pro.recovery_report",
    "ReportMetadata": "genesis_architect.pro.recovery_report",
    "generate_report": "genesis_architect.pro.recovery_report",
    "generate_report_for_project": "genesis_architect.pro.recovery_report",
    # red_team_critic
    "RedTeamFinding": "genesis_architect.pro.red_team_critic",
    "critique_session": "genesis_architect.pro.red_team_critic",
    "critique_with_llm": "genesis_architect.pro.red_team_critic",
    "run_red_team": "genesis_architect.pro.red_team_critic",
    # refactoring_planner
    "generate_plan": "genesis_architect.pro.refactoring_planner",
    # rules_engine
    "CheckReport": "genesis_architect.pro.rules_engine",
    "RuleResult": "genesis_architect.pro.rules_engine",
    "evaluate": "genesis_architect.pro.rules_engine",
    "format_rules_report": "genesis_architect.pro.rules_engine",
    "gather_facts": "genesis_architect.pro.rules_engine",
    "load_rules": "genesis_architect.pro.rules_engine",
    "run_check": "genesis_architect.pro.rules_engine",
    # security_templates
    "generate_security_docs": "genesis_architect.pro.security_templates",
    # skill_fetcher
    "FetchRefused": "genesis_architect.pro.skill_fetcher",
    "FetchResult": "genesis_architect.pro.skill_fetcher",
    "REGISTRY": "genesis_architect.pro.skill_fetcher",
    "SkillDefinition": "genesis_architect.pro.skill_fetcher",
    "TrustedSource": "genesis_architect.pro.skill_fetcher",
    "discard": "genesis_architect.pro.skill_fetcher",
    "fetch": "genesis_architect.pro.skill_fetcher",
    "list_sources": "genesis_architect.pro.skill_fetcher",
    "read_skills": "genesis_architect.pro.skill_fetcher",
    "sandbox_for": "genesis_architect.pro.skill_fetcher",
    "validate_source": "genesis_architect.pro.skill_fetcher",
    # source_anchor
    "AnchorEntry": "genesis_architect.pro.source_anchor",
    "AnchorReport": "genesis_architect.pro.source_anchor",
    "AnchorResult": "genesis_architect.pro.source_anchor",
    "PersistResult": "genesis_architect.pro.source_anchor",
    "anchor_from_store": "genesis_architect.pro.source_anchor",
    "anchor_responsibilities": "genesis_architect.pro.source_anchor",
    "persist_anchors": "genesis_architect.pro.source_anchor",
    # source_registry
    "Source": "genesis_architect.pro.source_registry",
    "SourceRegistry": "genesis_architect.pro.source_registry",
    "add_project_source": "genesis_architect.pro.source_registry",
    "load_registry": "genesis_architect.pro.source_registry",
    # ui_workspace
    "WorkspaceState": "genesis_architect.pro.ui_workspace",
    "collect_state": "genesis_architect.pro.ui_workspace",
    "render_workspace": "genesis_architect.pro.ui_workspace",
    "write_workspace": "genesis_architect.pro.ui_workspace",
}

#: Exported under a different name than the module defines it. Kept as an
#: explicit table rather than folded into the one above, because a rename
#: at the package boundary is a decision worth being able to see.
_LAZY_ALIASES: dict[str, str] = {
    "COMPANION_UI_PORT": "DEFAULT_PORT",
    "LearningRecommendation": "Recommendation",
    "audit_imports": "audit",
    "format_audit_report": "format_report",
    "format_rules_report": "format_report",
}


# importlib.reload() re-executes this body in the *existing* module __dict__,
# so any name cached by a previous life would survive and shadow __getattr__
# permanently - a reloaded package would keep handing back stale objects the
# eager version would have rebound. Clearing them here makes reload behave as
# it did before the conversion.
def _clear_lazy_cache() -> None:
    """Drop any export already cached in module globals."""
    for name in [n for n in globals() if n in _LAZY_EXPORTS]:
        del globals()[name]


_clear_lazy_cache()


def __getattr__(name: str):
    """Resolve a public name on first access (PEP 562).

    The resolved object is cached in module globals, so this runs once per
    name and every later access is an ordinary attribute lookup.
    """
    module_path = _LAZY_EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    import importlib

    # Five names are re-exported under a different name than their module
    # defines. Looking up the exported name on the module would fail for those.
    attribute = _LAZY_ALIASES.get(name, name)
    value = getattr(importlib.import_module(module_path), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Include the lazy names, so dir() and tab-completion still see the API."""
    return sorted(set(globals()) | set(_LAZY_EXPORTS))



__all__ = [
    # GDE — central brain
    "GenesisDecisionEngine", "run_session",
    "classify",
    "GDEMode", "LifecycleStage", "EngineCategory", "EngineStatus",
    "GateAction", "GateOutcome", "ApprovalChoice",
    "EngineDescriptor", "EngineResult", "WriteOperation",
    "GateResult", "GateReport", "ApprovalRequest", "ApprovalDecision",
    "CommitResult", "DecisionEntry", "Intent", "ExecutionPlan",
    "SessionContext", "SessionReport",
    "EngineRegistry", "RegistryError", "get_default_registry", "register",
    "save_session", "load_session", "delete_session",
    "append_decision_log", "read_decision_log", "session_file_exists",
    "build_plan", "run_plan", "evaluate_gates",
    # Existing exports
    "__version__",
    "RedTeamFinding", "critique_session", "critique_with_llm", "run_red_team",
    "PurgeCandidate", "ProtectedItem", "PurgeReport",
    "hygiene_notice", "mark_ephemeral", "purge",
    "AdvisorReport", "ProjectSignals", "ToolRecommendation", "ToolSpec", "CATALOG",
    "advise", "advise_global", "advise_local", "detect_signals",
    "REGISTRY", "FetchRefused", "FetchResult", "SkillDefinition", "TrustedSource",
    "discard", "fetch", "list_sources", "read_skills", "sandbox_for", "validate_source",
    "build_graph", "load_or_build",
    "score_project", "score_label",
    "detect_all",
    "classify_all",
    "generate_plan",
    "generate_c4_doc",
    "generate_security_docs",
    "DependencyIndex", "AffectedScope",
    "build_dependency_index", "compute_affected_scope",
    "ModelStore", "ArchModel", "ModelNode", "ModelLink",
    "ModelGroup", "ModelResponsibility",
    "ModelDiff", "NodeChange", "ResponsibilityChange", "LinkChange",
    "DriftFlags", "VagrantCandidate", "StaleCandidate",
    "detect_drift", "compute_drift_flags",
    "DriftScorerConfig", "NodeDriftScore", "DriftScore",
    "score_drift", "compute_drift_score",
    "RecoveryReport", "ArchitectureHealth", "DriftSummary",
    "Recommendation", "ReportMetadata",
    "generate_report", "generate_report_for_project",
    "AnchorEntry", "AnchorResult", "AnchorReport", "PersistResult",
    "anchor_responsibilities", "anchor_from_store", "persist_anchors",
    "TelemetryConfig", "CONSENT_PROMPT",
    "set_consent", "revoke_consent", "is_enabled", "needs_consent_prompt",
    "record_event", "read_events", "describe_payload", "clear_events",
    "Outcome", "ProfileStat", "LearningRecommendation", "KNOWN_PROFILES",
    "record_outcome", "read_outcomes", "rank_profiles", "recommend_profile",
    "summarize_lessons", "write_lessons",
    "KnowledgeGraph", "Node", "Edge", "NODE_TYPES", "REL_TYPES",
    "load_graph", "save_graph", "build_from_project",
    "gde_run_knowledge_graph", "register_knowledge_graph",
    "KNOWLEDGE_GRAPH_DESCRIPTOR",
    "Source", "SourceRegistry", "load_registry", "add_project_source",
    "FieldFinding", "FieldReport", "REDDIT_ANSWERS_TEMPLATES",
    "build_reddit_answers_queries", "verify_finding", "run_field_workflow",
    "EvidenceItem", "EvidencePack", "build_evidence_pack", "save_evidence_pack",
    "MEMORY_FILES", "DecisionJournalEntry", "init_memory", "record_decision",
    "record_research", "record_risk", "record_adr", "record_lesson",
    "set_project_memory", "read_memory", "memory_status",
    "Readiness", "Check", "CUSTOMER_FLOW",
    "check_readiness", "doctor_report", "offline_capability_report",
    "ensure_optional_dep",
    "WorkspaceState", "collect_state", "render_workspace", "write_workspace",
    "render_companion_html", "write_companion_html", "COMPANION_UI_PORT",
    "PhaseReport", "ReportItem", "render_report", "write_report",
    # Rules Engine
    "RuleResult", "CheckReport",
    "load_rules", "gather_facts", "evaluate", "run_check", "format_rules_report",
    # Git Churn Analyzer
    "WeeklySnapshot",
    "per_module_churn", "build_timeline", "render_sparkline",
    # Import Audit
    "AuditFinding", "ImportAuditReport",
    "audit_imports", "format_audit_report",
    # Decay Regressor
    "DecayRegressorConfig", "ScoreDataPoint", "RegressionResult",
    "ScorePrediction", "DecayForecast", "DecayRegressor",
    "forecast_from_history",
    # Cross-session memory
    "restore_session", "save_phase2", "save_phase4", "save_phase6",
    "save_video_pitfalls", "list_analyzed_videos",
    # Companion — Phase 0 instrumentation + Phase 1 health page
    "CompanionInstrumentation", "GateMissStats",
    "GateNotifier", "HealthPageServer",
]
