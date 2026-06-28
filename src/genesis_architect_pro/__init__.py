"""Genesis Architect Pro - the intelligence layer.

Multi-source research orchestration, pitfall ranking, video-to-pitfall
extraction, cross-session memory, package-registry validation,
recovery diagnosis, and deep codebase analysis.

Requires a valid license and the free genesis-architect core package.
"""

__version__ = "6.0.0"

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

__all__ = [
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
]
