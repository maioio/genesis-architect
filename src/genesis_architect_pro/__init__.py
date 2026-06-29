"""Genesis Architect Pro - the intelligence layer.

Multi-source research orchestration, pitfall ranking, video-to-pitfall
extraction, cross-session memory, package-registry validation,
recovery diagnosis, and deep codebase analysis.

Requires a valid license and the free genesis-architect core package.
"""

__version__ = "6.4.0"

from genesis_architect_pro.decision_engine import GenesisDecisionEngine, run_session
from genesis_architect_pro.intent_classifier import classify
from genesis_architect_pro.gde_types import (
    GDEMode, LifecycleStage, EngineCategory, EngineStatus,
    GateAction, GateOutcome, ApprovalChoice,
    EngineDescriptor, EngineResult, WriteOperation,
    GateResult, GateReport, ApprovalRequest, ApprovalDecision,
    CommitResult, DecisionEntry, Intent, ExecutionPlan,
    SessionContext, SessionReport,
)
from genesis_architect_pro.engine_registry import EngineRegistry, RegistryError, get_default_registry, register
from genesis_architect_pro.gde_session import save_session, load_session, delete_session, append_decision_log, read_decision_log, session_file_exists
from genesis_architect_pro.gde_planner import build_plan
from genesis_architect_pro.gde_runner import run_plan
from genesis_architect_pro.gde_gate_engine import evaluate_gates

from genesis_architect_pro.license import require_license, LicenseError
from genesis_architect_pro.import_graph import build_graph, load_or_build
from genesis_architect_pro.architecture_scorer import score_project, score_label
from genesis_architect_pro.antipattern_detector import detect_all
from genesis_architect_pro.fragility_classifier import classify_all
from genesis_architect_pro.refactoring_planner import generate_plan
from genesis_architect_pro.c4_generator import generate_c4_doc
from genesis_architect_pro.security_templates import generate_security_docs
from genesis_architect_pro.dependency_index import (
    DependencyIndex, AffectedScope,
    build_dependency_index, compute_affected_scope,
)
from genesis_architect_pro.model_store import (
    ModelStore, ArchModel, ModelNode, ModelLink, ModelGroup, ModelResponsibility,
    ModelDiff, NodeChange, ResponsibilityChange, LinkChange,
)
from genesis_architect_pro.drift_detector import (
    DriftFlags, VagrantCandidate, StaleCandidate,
    detect_drift, compute_drift_flags,
)
from genesis_architect_pro.drift_scorer import (
    DriftScorerConfig, NodeDriftScore, DriftScore,
    score_drift, compute_drift_score,
)
from genesis_architect_pro.recovery_report import (
    RecoveryReport, ArchitectureHealth, DriftSummary,
    Recommendation, ReportMetadata,
    generate_report, generate_report_for_project,
)
from genesis_architect_pro.source_anchor import (
    AnchorEntry, AnchorResult, AnchorReport, PersistResult,
    anchor_responsibilities, anchor_from_store, persist_anchors,
)
from genesis_architect_pro.product_intelligence import (
    TelemetryConfig, CONSENT_PROMPT,
    set_consent, revoke_consent, is_enabled, needs_consent_prompt,
    record_event, read_events, describe_payload, clear_events,
)
from genesis_architect_pro.learning_engine import (
    Outcome, ProfileStat, Recommendation as LearningRecommendation, KNOWN_PROFILES,
    record_outcome, read_outcomes, rank_profiles, recommend_profile,
    summarize_lessons, write_lessons,
)
from genesis_architect_pro.knowledge_graph import (
    KnowledgeGraph, Node, Edge, NODE_TYPES, REL_TYPES,
    load_graph, save_graph, build_from_project,
)
from genesis_architect_pro.gde_knowledge_graph_adapter import (
    gde_run_knowledge_graph, register_knowledge_graph,
    KNOWLEDGE_GRAPH_DESCRIPTOR,
)
from genesis_architect_pro.source_registry import (
    Source, SourceRegistry, load_registry, add_project_source,
)
from genesis_architect_pro.field_intelligence import (
    FieldFinding, FieldReport, REDDIT_ANSWERS_TEMPLATES,
    build_reddit_answers_queries, verify_finding, run_field_workflow,
)
from genesis_architect_pro.evidence_pack import (
    EvidenceItem, EvidencePack, build_evidence_pack, save_evidence_pack,
)
from genesis_architect_pro.memory_engine import (
    MEMORY_FILES, DecisionJournalEntry, init_memory, record_decision,
    record_research, record_risk, record_adr, record_lesson,
    set_project_memory, read_memory, memory_status,
)
from genesis_architect_pro.first_run import (
    Readiness, Check, CUSTOMER_FLOW,
    check_readiness, doctor_report, offline_capability_report,
    ensure_optional_dep,
)
from genesis_architect_pro.ui_workspace import (
    WorkspaceState, collect_state, render_workspace, write_workspace,
)

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
    "require_license", "LicenseError", "__version__",
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
]
